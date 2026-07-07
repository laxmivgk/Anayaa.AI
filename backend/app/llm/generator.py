"""LLM response generation via Ollama — no template fallback."""
from __future__ import annotations

import logging
import re
import time
from html import unescape
from typing import Any

import httpx

from app.agents.pipeline_errors import PipelineError, ServiceUnavailableError, SynthesisRejectedError
from app.config import get_settings
from app.llm.router import select_model
from app.security.harm_normalizer import normalize_harmful_framing_text

logger = logging.getLogger(__name__)

DHARMA_FRAME_RE = re.compile(
    r"^I am asking a dharma dilemma about this user-provided situation:\s*(?P<situation>.*?)"
    r"\.\s*Without inventing missing facts, what is the wisest, kindest, most truthful, "
    r"and least harmful way to understand or act\?\s*$",
    re.I,
)
IDENTITY_FRAME_RE = re.compile(
    r"^I am asking a dharma dilemma about (?P<situation>who I am beyond roles and labels):\s*"
    r"how should I understand (?P<terms>.*?)\?\s*$",
    re.I,
)
ANSWER_LABEL_RE = re.compile(
    r"^(?:one[- ]line summary|summary|reflection|judg(?:e)?ment|next step|action|scripture grounding|grounding)\s*:",
    re.I,
)
BARE_ANSWER_LABELS = {
    "reflection": "Reflection",
    "judgement": "Judgement",
    "judgment": "Judgement",
    "next step": "Next step",
    "action": "Next step",
    "scripture grounding": "Scripture grounding",
    "grounding": "Scripture grounding",
}
BARE_ANSWER_LABEL_RE = re.compile(
    r"^(reflection|judg(?:e)?ment|next step|action|scripture grounding|grounding)\s*$",
    re.I,
)
SUMMARY_LABEL_RE = re.compile(r"^(?:one[- ]line summary|summary)\s*:", re.I)
DETAIL_LABEL_RE = re.compile(
    r"^(reflection|judg(?:e)?ment|next step|action|scripture grounding|grounding)\s*:\s*(.*)$",
    re.I,
)
PROMPT_ECHO_LINE_RE = re.compile(
    r"^(?:"
    r"Dilemma:|"
    r"Must stay focused on these user-topic words:|"
    r"Tone mode:|"
    r"Retrieved scriptures:|"
    r"Citation anchors:|"
    r"\d+\.\s*\[[^\]]+\]\s+.+|"
    r"\d+\.\s*.+\s+anchors:\s*.+|"
    r"Write exactly these \d+ labeled sections\b|"
    r"Use simple everyday words\b|"
    r"Each title must be visible\b|"
    r"Only make claims supported by\b|"
    r"If a detail is not given\b|"
    r"For one-word, fragmentary, or broad questions\b|"
    r"For this business-integrity question\b|"
    r"Do not (?:include markdown|assume the user|name specific commercial|invent facts|use markdown)\b|"
    r"The Summary must clearly address\b|"
    r"Avoid abstract filler\b|"
    r"One-line summary:\s*answer the dilemma directly\b|"
    r"Summary:\s*answer the dilemma directly\b|"
    r"Reflection:\s*explain the feeling\b|"
    r"Judgement:\s*say what choice\b|"
    r"Judgment:\s*say what choice\b|"
    r"Next step:\s*give one concrete\b|"
    r"Scripture grounding:\s*write 2 plain sentences\b"
    r")",
    re.I,
)
PROMPT_LIKE_RESPONSE_RE = re.compile(
    r"\b(?:"
    r"answer the dilemma directly|"
    r"business-integrity question|"
    r"dharma question about|"
    r"retrieved scriptures point toward|"
    r"use the citations as a boundary|"
    r"write 2 plain sentences"
    r")\b",
    re.I,
)
FOCUS_TERM_ALIASES = {
    "disciplined": ["discipline", "self-control"],
    "discipline": ["disciplined", "self-control"],
    "scamming": ["scam"],
    "scam": ["scamming"],
}
RELATIONSHIP_ROLE_GROUPS = {
    "friend": {"friend", "friends"},
    "parent": {"parent", "parents", "mom", "mother", "dad", "father"},
    "spouse": {"spouse", "partner", "husband", "wife"},
    "manager": {"manager", "boss", "supervisor"},
    "coworker": {"coworker", "colleague"},
    "sibling": {"brother", "sister", "sibling"},
    "child": {"son", "daughter", "child", "kid", "kids"},
}
RELATIONSHIP_ROLE_DISPLAY = {
    "friend": "friend",
    "parent": "parent/mom/mother/father",
    "spouse": "spouse/partner",
    "manager": "manager/boss",
    "coworker": "coworker/colleague",
    "sibling": "brother/sister",
    "child": "child/kid",
}
RELATIONSHIP_DRIFT_PATTERNS = {
    "parent": re.compile(r"\b(?:your|my|their|the user's)\s+(?:mom|mother|father|dad|parent|parents)\b", re.I),
    "spouse": re.compile(r"\b(?:your|my|their|the user's)\s+(?:spouse|partner|husband|wife)\b", re.I),
    "manager": re.compile(r"\b(?:your|my|their|the user's)\s+(?:manager|boss|supervisor)\b", re.I),
    "coworker": re.compile(r"\b(?:your|my|their|the user's)\s+(?:coworker|colleague)\b", re.I),
    "sibling": re.compile(r"\b(?:your|my|their|the user's)\s+(?:brother|sister|sibling)\b", re.I),
    "child": re.compile(r"\b(?:your|my|their|the user's)\s+(?:son|daughter|child|kid)\b", re.I),
}


def _active_ollama_warmup_models() -> list[str]:
    """Warm only the active local models so first-query latency is less surprising."""
    models: list[str] = []
    for task in ["planner", "synthesizer", "judge"]:
        model = select_model(task)
        if model == "gemini-flash" or model in models:
            continue
        models.append(model)
    return models


async def prewarm_ollama_models() -> None:
    """Load the selected local Ollama models before the first user query."""
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=60.0) as client:
        for model in _active_ollama_warmup_models():
            try:
                response = await client.post(
                    "/api/generate",
                    json={
                        "model": model,
                        "prompt": "ready",
                        "stream": False,
                        # Keep warmed models resident for the common demo path;
                        # this reduces the first visible query latency after serve.
                        "keep_alive": "30m",
                        "options": {"temperature": 0.0, "num_predict": 1, "num_ctx": 512},
                    },
                )
                response.raise_for_status()
            except Exception as exc:
                logger.warning("Ollama model warmup skipped for %s: %s", model, exc)


async def prewarm_synthesizer() -> None:
    """Backward-compatible wrapper for startup warmup."""
    await prewarm_ollama_models()


async def generate_moral_pathway(
    dilemma: str,
    citations: list[dict[str, Any]],
    tone_msg: str = "",
) -> tuple[str, dict[str, Any]]:
    """Generate a moral pathway using a local LLM."""
    if not citations:
        # Final guidance must be citation-backed. If retrieval did not produce
        # evidence, the workflow returns an explicit failure state instead.
        raise ServiceUnavailableError(
            "LLM synthesis",
            "no scripture citations were retrieved to ground the response",
        )

    settings = get_settings()
    model = select_model("synthesizer")
    visible_dilemma = _visible_dilemma_text(dilemma)
    safe_dilemma = normalize_harmful_framing_text(visible_dilemma)
    prompt = _build_synthesis_prompt(safe_dilemma, citations, tone_msg)
    started = time.perf_counter()
    system_message = (
        "You are Anayaa, a calm and practical moral guide. "
        "Give a clear answer for the user's real situation before offering reflection. "
        "Stay human, specific, and useful; avoid sounding academic, mystical, or sermon-like. "
        "Use only the user's dilemma and the retrieved scripture text as evidence. "
        "Do not invent facts, motives, outcomes, citations, verse meanings, or personal details. "
        "If the dilemma is short or vague, say only what can be safely inferred and keep the guidance general. "
        "Do not use markdown, bullet points, or numbered lists."
    )
    synthesis_options = {"temperature": 0.0, "num_predict": 520, "num_ctx": 2048}

    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=120.0) as client:
            response = await client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_message,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "keep_alive": "30m",
                    "options": synthesis_options,
                },
            )
            response.raise_for_status()
            data = response.json()
            pathway = _clean_synthesis_output((data.get("message") or {}).get("content", ""))
            if not pathway:
                raise ValueError("Empty LLM response")

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            rejection_reason = _synthesis_rejection_reason(safe_dilemma, citations, pathway)
            if rejection_reason:
                retry_reason = rejection_reason
                if _should_retry_synthesis_rejection(rejection_reason):
                    retry_prompt = (
                        f"{prompt}\n\n"
                        "Your previous draft was incomplete or not visibly grounded. Regenerate the full answer now. "
                        "You must include all 5 labels exactly once, and the final label must be "
                        "Scripture grounding: with two named retrieved sources and their anchor keywords. "
                        "Do not attach a quote, chapter, or verse reference from one scripture to a different scripture source."
                    )
                    retry_response = await client.post(
                        "/api/chat",
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": retry_prompt},
                            ],
                            "stream": False,
                            "think": False,
                            "keep_alive": "30m",
                            "options": synthesis_options,
                        },
                    )
                    retry_response.raise_for_status()
                    retry_data = retry_response.json()
                    retry_pathway = _clean_synthesis_output((retry_data.get("message") or {}).get("content", ""))
                    retry_reason = _synthesis_rejection_reason(safe_dilemma, citations, retry_pathway)
                    if retry_pathway and not retry_reason:
                        data = retry_data
                        pathway = retry_pathway
                        rejection_reason = ""

                if not rejection_reason:
                    metrics = {
                        "engine": "Ollama LLM",
                        "modelName": model,
                        "ttftMs": elapsed_ms,
                        "totalTokens": data.get("eval_count") or len(pathway) // 4,
                        "tokPerSec": round((data.get("eval_count") or 1) / max(elapsed_ms / 1000, 0.01), 1),
                        "kvCacheHit": False,
                        "staticPromptCache": "Inactive",
                        "memoryUsageMb": None,
                        "synthesisRetry": True,
                    }
                    return pathway, metrics

                # Do not replace a rejected LLM answer with a canned template; a
                # visible failure is safer than unsupported moral guidance.
                logger.warning("LLM synthesis rejected (%s); no fallback answer will be shown", retry_reason)
                raise SynthesisRejectedError(retry_reason)

            metrics = {
                "engine": "Ollama LLM",
                "modelName": model,
                "ttftMs": elapsed_ms,
                "totalTokens": data.get("eval_count") or len(pathway) // 4,
                "tokPerSec": round((data.get("eval_count") or 1) / max(elapsed_ms / 1000, 0.01), 1),
                "kvCacheHit": False,
                "staticPromptCache": "Inactive",
                "memoryUsageMb": None,
            }
            return pathway, metrics
    except PipelineError:
        raise
    except Exception as exc:
        logger.error("LLM synthesis failed: %s", exc)
        raise ServiceUnavailableError("Ollama LLM", str(exc)) from exc


def _build_synthesis_prompt(
    dilemma: str,
    citations: list[dict[str, Any]],
    tone_msg: str,
) -> str:
    """Constrain synthesis to the dilemma and retrieved citations so guidance stays grounded."""
    dilemma = _visible_dilemma_text(dilemma)
    citation_lines = []
    anchor_lines = []
    for idx, citation in enumerate(citations[:3], start=1):
        # Anchor keywords give the synthesizer concrete terms it must reuse when
        # explaining how scripture supports the practical advice.
        keywords = [
            str(keyword).strip().lower()
            for keyword in citation.get("keywords", [])[:4]
            if str(keyword).strip()
        ]
        citation_lines.append(
            f"{idx}. [{citation.get('faith')}] {citation.get('source')} "
            f"{citation.get('chapter')}:{citation.get('verse')} — "
            f"\"{citation.get('translation')}\""
        )
        anchor_lines.append(
            f"{idx}. {citation.get('source')} {citation.get('chapter')}:{citation.get('verse')} "
            f"anchors: {', '.join(keywords) if keywords else citation.get('source')}"
        )
    citations_block = "\n".join(citation_lines)
    anchors_block = "\n".join(anchor_lines)
    tone = tone_msg or "Balanced guidance mode"
    focus_terms = _query_focus_terms(dilemma)
    focus_block = ", ".join(focus_terms) if focus_terms else "the user's exact dilemma"
    relationship_instruction = _relationship_role_instruction(dilemma)
    caregiver_burnout_instruction = ""
    if _is_caregiver_burnout_dilemma(dilemma):
        caregiver_burnout_instruction = (
            "For this caregiver-burnout question, treat exhaustion, hopelessness, and 'giving up' as the urgent center. "
            "The Next step must not start with business finances, debt tracking, saving money, or productivity. "
            "The Next step should tell the user to contact one real person today, say they are burned out and cannot carry this alone, "
            "and ask for one concrete relief action such as parent-care coverage, a meal, a ride, or help calling a doctor, social worker, or respite resource. "
            "If the user may harm themselves or cannot stay safe, tell them to contact local emergency or crisis support now. "
            "Keep business decisions secondary until the user has immediate support and rest.\n"
        )
    betrayal_revenge_instruction = ""
    if _is_betrayal_revenge_dilemma(dilemma):
        betrayal_revenge_instruction = (
            "For this betrayal, lies, anger, or revenge question, make the Next step calm and proportionate. "
            "The One-line summary should say not to seek revenge, to protect yourself with truth and boundaries, "
            "and that forgiveness can be a later process; do not frame protection as the opposite of forgiveness. "
            "Do not say the user should choose lawful protection rather than trying to forgive. "
            "Do not use the phrase lawful protection for ordinary lies or betrayal; say truth and calm boundaries instead. "
            "Tell the user not to retaliate today, to write down what was said, when it happened, who heard it, "
            "and what evidence exists, and to limit contact if it prevents further harm. "
            "Do not make law enforcement or authority escalation the default first step. Mention a trusted person or appropriate authority "
            "only if the lies affect safety, work, school, housing, or reputation; mention emergency support only for threats, stalking, or immediate danger. "
            "Do not mention legal action unless the user describes a concrete legal threat, safety threat, stalking, workplace/school action, or serious reputation harm.\n"
        )
    business_integrity_instruction = ""
    if _is_dropshipping_scam_dilemma(dilemma):
        business_integrity_instruction = (
            "For this business-integrity question, answer directly whether the business model is automatically wrong: "
            "say it is not automatically scamming, but it becomes unethical if it hides risk, misleads customers, "
            "uses unreliable fulfillment, conceals delays, refuses fair refunds, or avoids accountability. "
            "Do not assume the user has invested money, suffered losses, or already started the business. "
            "Do not name specific commercial platforms, tools, or companies unless the user named them.\n"
        )
    elif _is_business_integrity_dilemma(dilemma):
        business_integrity_instruction = (
            "For this business-integrity question, answer the user's exact wealth-versus-integrity conflict directly: "
            "say that pursuing wealth is not wrong by itself, but pursuing wealth at the cost of honesty, fairness, "
            "lawful conduct, or integrity is not wise. Do not turn the question into dropshipping, scamming, or a specific "
            "business model unless the user named one. Keep the practical step focused on identifying the exact corner "
            "the user feels tempted to cut and choosing an ethical alternative.\n"
        )
    return (
        f"Dilemma:\n{dilemma}\n\n"
        f"Must stay focused on these user-topic words:\n{focus_block}\n\n"
        f"Tone mode: {tone}\n\n"
        f"Retrieved scriptures:\n{citations_block}\n\n"
        f"Citation anchors:\n{anchors_block}\n\n"
        "Write exactly these 5 labeled sections, 180 words or fewer total.\n"
        "Use simple everyday words. Each title must be visible at the start of its own line:\n"
        "One-line summary: answer the dilemma directly in one compact sentence.\n"
        "Reflection: explain the feeling or conflict in simple words, without blaming the user.\n"
        "Judgement: say what choice seems wisest and kindest.\n"
        "Next step: give one concrete, stable action the user can take today; include both a fact-recording step and a practical protection step when the dilemma involves business or money.\n"
        "Scripture grounding: write 2 plain sentences explaining how at least two retrieved scriptures support the advice; name two exact sources from Citation anchors and reuse at least one anchor keyword from each.\n"
        "In Scripture grounding, never mix sources: if a sentence quotes or references Romans, the sentence subject must be Romans or Holy Bible, not Bhagavad Gita, Dhammapada, Quran, or another scripture.\n"
        "Only make claims supported by the dilemma or retrieved scriptures. If a detail is not given, keep the wording general.\n"
        f"{relationship_instruction}\n"
        "If a private name was redacted, never print [NAME_REDACTED] in final guidance.\n"
        "For one-word, fragmentary, or broad questions, do not invent a scenario; answer the dharma meaning of the words the user provided.\n"
        f"{caregiver_burnout_instruction}"
        f"{betrayal_revenge_instruction}"
        f"{business_integrity_instruction}"
        "The Summary must clearly address the user's actual dilemma and should reuse at least one user-topic word naturally.\n"
        "Do not include markdown, bullets, numbered steps, or generic openers like 'As you navigate'.\n"
        "Avoid abstract filler and ornate phrases such as 'cultivating self-awareness', 'delicate situation', "
        "'right intention', 'moral pathway', and 'may this guidance inspire you'."
    )


def _clean_synthesis_output(pathway: str) -> str:
    """Remove prompt-instruction echoes before the pathway reaches the UI."""
    lines = [
        re.sub(r"\s+", " ", line.replace("**", "").lstrip("#").strip()).strip("` ")
        for line in str(pathway or "").splitlines()
    ]
    lines = [line for line in lines if line]
    has_answer_label = any(ANSWER_LABEL_RE.match(line) for line in lines)
    cleaned: list[str] = []
    reached_answer = not has_answer_label

    for line in lines:
        if PROMPT_ECHO_LINE_RE.match(line):
            continue
        if not reached_answer:
            # Drop preamble until the first real answer section appears.
            if ANSWER_LABEL_RE.match(line):
                reached_answer = True
            else:
                continue
        cleaned.append(line)

    return _normalize_answer_section_labels(cleaned).strip()


def _normalize_answer_section_labels(lines: list[str]) -> str:
    """Normalize minor label drift from local models into the UI guidance contract."""
    normalized: list[str] = []
    pre_detail_lines: list[str] = []
    saw_summary = False

    def flush_summary() -> None:
        nonlocal saw_summary
        if not pre_detail_lines:
            return
        summary_lines = pre_detail_lines
        if len(summary_lines) > 1 and _looks_like_short_title(summary_lines[0]):
            summary_lines = summary_lines[1:]
        summary_text = " ".join(summary_lines).strip()
        if summary_text:
            normalized.append(f"Summary: {summary_text}")
            saw_summary = True
        pre_detail_lines.clear()

    for line in lines:
        if SUMMARY_LABEL_RE.match(line):
            flush_summary()
            summary_text = SUMMARY_LABEL_RE.sub("", line, count=1).strip()
            normalized.append(f"Summary: {summary_text}" if summary_text else "Summary:")
            saw_summary = True
            continue

        detail_match = DETAIL_LABEL_RE.match(line)
        if detail_match:
            if not saw_summary:
                flush_summary()
            label = BARE_ANSWER_LABELS[detail_match.group(1).lower()]
            detail_text = detail_match.group(2).strip()
            normalized.append(f"{label}: {detail_text}" if detail_text else f"{label}:")
            continue

        bare_match = BARE_ANSWER_LABEL_RE.match(line)
        if bare_match:
            if not saw_summary:
                flush_summary()
            normalized.append(f"{BARE_ANSWER_LABELS[bare_match.group(1).lower()]}:")
            continue

        if normalized and normalized[-1].endswith(":"):
            normalized[-1] = f"{normalized[-1]} {line}".strip()
            continue

        if not saw_summary and not normalized:
            pre_detail_lines.append(line)
            continue

        normalized.append(line)

    flush_summary()
    return "\n".join(_merge_duplicate_answer_sections(normalized))


def _merge_duplicate_answer_sections(lines: list[str]) -> list[str]:
    """Merge repeated labeled sections from local model drift into one display block per label."""
    merged: list[str] = []
    label_index: dict[str, int] = {}
    for line in lines:
        summary_match = SUMMARY_LABEL_RE.match(line)
        match = DETAIL_LABEL_RE.match(line)
        if summary_match:
            label = "Summary"
            text = SUMMARY_LABEL_RE.sub("", line, count=1).strip()
            rendered = f"{label}: {text}" if text else f"{label}:"
            if label not in label_index:
                label_index[label] = len(merged)
                merged.append(rendered)
                continue
            if text:
                index = label_index[label]
                merged[index] = f"{merged[index].rstrip()} {text}".strip()
            continue

        if not match:
            merged.append(line)
            continue
        raw_label = match.group(1).lower()
        label = BARE_ANSWER_LABELS.get(raw_label, "Summary")
        text = match.group(2).strip()
        rendered = f"{label}: {text}" if text else f"{label}:"
        if label not in label_index:
            label_index[label] = len(merged)
            merged.append(rendered)
            continue
        if text:
            index = label_index[label]
            merged[index] = f"{merged[index].rstrip()} {text}".strip()
    return merged


def _looks_like_short_title(value: str) -> bool:
    words = re.findall(r"\b\w+\b", value)
    return 0 < len(words) <= 3 and not re.search(r"[.!?;:,]", value)


def _visible_dilemma_text(dilemma: str) -> str:
    """Return the user-facing dilemma, not Anayaa's internal retrieval frame."""
    text = re.sub(r"\s+", " ", unescape(str(dilemma or ""))).strip()
    match = DHARMA_FRAME_RE.match(text)
    if match:
        return match.group("situation").strip(" .?!")
    match = IDENTITY_FRAME_RE.match(text)
    if match:
        return f"{match.group('situation')}; {match.group('terms')}".strip(" .?!")
    return text


def _query_focus_terms(dilemma: str) -> list[str]:
    dilemma = _visible_dilemma_text(dilemma)
    stopwords = {
        "about",
        "after",
        "again",
        "asking",
        "because",
        "could",
        "dharma",
        "dilemma",
        "facts",
        "harmful",
        "inventing",
        "kindest",
        "least",
        "missing",
        "most",
        "provided",
        "situation",
        "their",
        "there",
        "these",
        "this",
        "those",
        "through",
        "under",
        "understand",
        "user",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
        "wisest",
        "should",
        "need",
        "want",
        "feel",
        "help",
    }
    terms = []
    for term in re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", dilemma.lower()):
        if term not in stopwords and term not in terms:
            terms.append(term)
    return terms[:6]


def _relationship_role_groups(dilemma: str) -> set[str]:
    text = _visible_dilemma_text(dilemma).lower()
    groups: set[str] = set()
    for group, terms in RELATIONSHIP_ROLE_GROUPS.items():
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms):
            groups.add(group)
    return groups


def _relationship_role_instruction(dilemma: str) -> str:
    groups = _relationship_role_groups(dilemma)
    if not groups:
        return (
            "No specific relationship role is confirmed. If a private name was redacted, "
            "use neutral wording like the other person or them; do not invent mom, parent, spouse, manager, or friend."
        )

    allowed = ", ".join(RELATIONSHIP_ROLE_DISPLAY[group] for group in sorted(groups))
    return (
        f"Known relationship roles from the dilemma: {allowed}. "
        "If a private name was redacted, use only these confirmed roles or neutral wording like the other person/them. "
        "Do not change one relationship into another; for example, do not change a friend into a mom, parent, spouse, manager, or coworker."
    )


def _is_summary_relevant(dilemma: str, citations: list[dict[str, Any]], pathway: str) -> bool:
    pathway_lower = pathway.lower()
    focus_terms = _query_focus_terms(dilemma)
    if focus_terms:
        matches = [term for term in focus_terms if _focus_term_in_text(term, pathway_lower)]
        required_matches = 1 if len(focus_terms) <= 2 else 2
        if len(matches) < required_matches and not (
            _is_betrayal_revenge_dilemma(dilemma) and _is_betrayal_revenge_pathway_relevant(pathway)
        ):
            return False

    citation_terms: list[str] = []
    for citation in citations:
        for raw_term in [
            *(citation.get("keywords") or []),
            citation.get("source", ""),
            citation.get("faith", ""),
        ]:
            term = str(raw_term).strip().lower()
            if len(term) >= 4 and term not in citation_terms:
                citation_terms.append(term)

    if not citation_terms or any(term in pathway_lower for term in citation_terms[:8]):
        return True
    return _is_betrayal_revenge_dilemma(dilemma) and _betrayal_revenge_citation_grounded(citations, pathway)


def _is_betrayal_revenge_pathway_relevant(pathway: str) -> bool:
    lower = pathway.lower()
    harm_terms = {
        "betray",
        "betrayed",
        "betrayal",
        "lie",
        "lies",
        "lying",
        "anger",
        "angry",
        "hatred",
        "hurt",
        "trust",
        "trusted",
    }
    response_terms = {
        "revenge",
        "retaliate",
        "retaliation",
        "forgive",
        "forgiveness",
        "boundary",
        "boundaries",
        "truth",
        "protect",
        "protection",
        "calm",
        "contact",
    }
    return any(term in lower for term in harm_terms) and any(term in lower for term in response_terms)


def _betrayal_revenge_citation_grounded(citations: list[dict[str, Any]], pathway: str) -> bool:
    lower = pathway.lower()
    citation_ids = {str(citation.get("id") or "").lower() for citation in citations}
    source_terms = {
        "romans",
        "bible",
        "dhammapada",
        "gita",
        "bhagavad",
        "quran",
        "sutta",
        "upanishad",
    }
    scripture_terms = {
        "overcome evil",
        "good",
        "hatred",
        "non-hatred",
        "anger",
        "delusion",
        "intellect",
        "forgiveness",
        "retaliation",
        "revenge",
        "compassion",
    }
    source_hits = sum(1 for term in source_terms if term in lower)
    scripture_hits = sum(1 for term in scripture_terms if term in lower)
    if {"c3", "b2"}.issubset(citation_ids):
        return source_hits >= 1 and scripture_hits >= 2
    return source_hits >= 1 and scripture_hits >= 1


def _scripture_source_mismatches(citations: list[dict[str, Any]], pathway: str) -> list[str]:
    grounding = _scripture_grounding_text(pathway)
    if not grounding:
        return []

    indexed = []
    for index, citation in enumerate(citations):
        aliases = _source_aliases(citation)
        if not aliases:
            continue
        indexed.append(
            {
                "key": str(citation.get("id") or citation.get("source") or index),
                "source": str(citation.get("source") or citation.get("faith") or f"citation {index + 1}"),
                "translation": _normalized_text(citation.get("translation") or ""),
                "aliases": aliases,
            }
        )

    mismatches: list[str] = []
    for sentence in _grounding_sentences(grounding):
        sentence_lower = _normalized_text(sentence)
        attributed = _attributed_source_key(sentence_lower, indexed)
        if not attributed:
            named = [item for item in indexed if _contains_any_source_alias(sentence_lower, item["aliases"])]
            attributed = named[0]["key"] if len(named) == 1 else ""
        if not attributed:
            continue

        quote_owner = _quote_owner_key(sentence, indexed)
        if quote_owner and quote_owner != attributed:
            mismatches.append(f"{attributed}->{quote_owner}")
            continue

        reference_owner = _parenthetical_reference_owner_key(sentence_lower, indexed)
        if reference_owner and reference_owner != attributed:
            mismatches.append(f"{attributed}->{reference_owner}")

    return mismatches[:4]


def _scripture_grounding_text(pathway: str) -> str:
    match = re.search(
        r"(?:^|[\n.]\s*)scripture grounding\s*:\s*(?P<section>.*?)(?=(?:\n|$)\s*(?:one[- ]line summary|summary|reflection|judg(?:e)?ment|next step)\s*:|\Z)",
        str(pathway or ""),
        flags=re.I | re.S,
    )
    return match.group("section").strip() if match else ""


def _grounding_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", compact) if part.strip()]


def _source_aliases(citation: dict[str, Any]) -> list[str]:
    source = _normalized_text(citation.get("source") or "")
    aliases = [source] if source else []
    if ":" in source:
        aliases.extend(part.strip() for part in source.split(":") if part.strip())
    source_aliases = {
        "holy bible": ["bible"],
        "bhagavad gita": ["gita"],
        "al-quran": ["quran"],
        "quran": ["al-quran"],
    }
    for known, extra_aliases in source_aliases.items():
        if known in source:
            aliases.extend(extra_aliases)
    for term in re.findall(r"\b(?:romans|matthew|dhammapada|gita|quran|upanishad|sutta)\b", source):
        aliases.append(term)
    return [alias for alias in dict.fromkeys(aliases) if len(alias) >= 4]


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _contains_source_alias(text: str, alias: str) -> bool:
    if " " in alias or ":" in alias or "-" in alias:
        return alias in text
    return bool(re.search(rf"\b{re.escape(alias)}\b", text))


def _contains_any_source_alias(text: str, aliases: list[str]) -> bool:
    return any(_contains_source_alias(text, alias) for alias in aliases)


def _attributed_source_key(sentence_lower: str, indexed: list[dict[str, Any]]) -> str:
    attribution_verbs = (
        "advises",
        "teaches",
        "reminds",
        "says",
        "warns",
        "suggests",
        "points",
        "calls",
        "encourages",
        "highlights",
        "shows",
    )
    for item in indexed:
        for alias in item["aliases"]:
            alias_pattern = re.escape(alias)
            pattern = (
                rf"(?:^|(?:similarly|also|in contrast|instead)\s*,?\s+)"
                rf"(?:the\s+)?{alias_pattern}(?:\s+also)?\s+"
                rf"(?:{'|'.join(attribution_verbs)})\b"
            )
            if re.search(pattern, sentence_lower):
                return item["key"]
    return ""


def _quote_owner_key(sentence: str, indexed: list[dict[str, Any]]) -> str:
    for quote in re.findall(r"[\"“](.*?)[\"”]", sentence):
        normalized_quote = _normalized_text(quote)
        if len(normalized_quote) < 12:
            continue
        owners = [
            item["key"]
            for item in indexed
            if item["translation"] and normalized_quote in item["translation"]
        ]
        if len(owners) == 1:
            return owners[0]
    return ""


def _parenthetical_reference_owner_key(sentence_lower: str, indexed: list[dict[str, Any]]) -> str:
    for parenthetical in re.findall(r"\(([^)]*)\)", sentence_lower):
        owners = [
            item["key"]
            for item in indexed
            if _contains_any_source_alias(parenthetical, item["aliases"])
        ]
        if len(owners) == 1:
            return owners[0]
    return ""


def _focus_term_in_text(term: str, text: str) -> bool:
    candidates = [term, *FOCUS_TERM_ALIASES.get(term, [])]
    return any(candidate and candidate in text for candidate in candidates)


def _should_reject_synthesis(dilemma: str, citations: list[dict[str, Any]], pathway: str) -> bool:
    return bool(_synthesis_rejection_reason(dilemma, citations, pathway))


def _synthesis_rejection_reason(dilemma: str, citations: list[dict[str, Any]], pathway: str) -> str:
    # Return the first guardrail reason so logs explain why the LLM text was rejected.
    if _contains_prompt_like_response_text(pathway):
        return "prompt_like_response"
    if not re.search(r"^(?:one[- ]line summary|summary)\s*:\s*\S+", pathway, re.I | re.M):
        return "missing_summary_section"
    if not re.search(r"(?:^|[\n.]\s*)scripture grounding\s*:\s*\S+", pathway, re.I | re.M):
        return "missing_scripture_grounding_section"
    if _scripture_source_mismatches(citations, pathway):
        return "scripture_source_mismatch"
    if _unsupported_relationship_drift(dilemma, pathway):
        return "unsupported_relationship_drift"
    if not _is_summary_relevant(dilemma, citations, pathway):
        return "summary_not_relevant_to_query"
    if _is_dropshipping_scam_dilemma(dilemma) and _business_integrity_answer_drifted(pathway):
        return "business_integrity_drift"
    return ""


def _should_retry_synthesis_rejection(reason: str) -> bool:
    return reason in {
        "missing_scripture_grounding_section",
        "summary_not_relevant_to_query",
        "scripture_source_mismatch",
    }


def _contains_prompt_like_response_text(pathway: str) -> bool:
    return bool(PROMPT_LIKE_RESPONSE_RE.search(str(pathway or "")))


def _unsupported_relationship_drift(dilemma: str, pathway: str) -> bool:
    allowed_groups = _relationship_role_groups(dilemma)
    for group, pattern in RELATIONSHIP_DRIFT_PATTERNS.items():
        if group not in allowed_groups and pattern.search(str(pathway or "")):
            return True
    return False


def _business_integrity_answer_drifted(pathway: str) -> bool:
    lower = pathway.lower()
    unsupported_patterns = [
        r"\byou might be feeling\b",
        r"\byou may be feeling\b",
        r"\binvested (?:time|money|.*so far)\b",
        r"\binitial costs?\b",
        r"\blosses\b",
        r"\bshopify\b",
        r"\boberlo\b",
        r"\breputable online platforms\b",
        r"\bsignificant commitments\b",
    ]
    if any(re.search(pattern, lower) for pattern in unsupported_patterns):
        return True

    required_terms = ["dropshipping", "scam"]
    if not all(term in lower for term in required_terms):
        return True

    integrity_terms = ["honest", "transparent", "mislead", "customer", "refund", "accountability", "responsibility"]
    return sum(1 for term in integrity_terms if term in lower) < 2


def _is_business_integrity_dilemma(value: str) -> bool:
    lower = value.lower()
    business_terms = {
        "business",
        "competitor",
        "competitors",
        "wealth",
        "wealthy",
        "profit",
        "profits",
        "selling",
        "seller",
        "customer",
        "dropshipping",
    }
    integrity_terms = {
        "ethical",
        "ethics",
        "integrity",
        "honest",
        "honesty",
        "corner",
        "corners",
        "scam",
        "scamming",
        "mislead",
        "fraud",
        "trust",
    }
    return any(term in lower for term in business_terms) and any(term in lower for term in integrity_terms)


def _is_dropshipping_scam_dilemma(value: str) -> bool:
    lower = value.lower()
    return "dropshipping" in lower and any(term in lower for term in {"scam", "scamming"})


def _is_betrayal_revenge_dilemma(value: str) -> bool:
    lower = value.lower()
    betrayal_terms = {"betray", "betrayed", "betrayal", "lies", "lying", "spread", "spreading", "anger", "hatred"}
    revenge_terms = {"revenge", "retaliate", "retaliation", "forgive", "forgiveness"}
    return any(term in lower for term in betrayal_terms) and any(term in lower for term in revenge_terms)


def _is_caregiver_burnout_dilemma(value: str) -> bool:
    lower = value.lower()
    caregiver_terms = {"parent", "sick", "care", "caregiver", "caring"}
    exhaustion_terms = {"burned out", "burnt out", "burnout", "hopeless", "exhausted", "giving up", "overwhelmed"}
    return any(term in lower for term in caregiver_terms) and any(term in lower for term in exhaustion_terms)
