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
TERSE_CHOICE_FRAME_RE = re.compile(
    r"^I am asking a dharma dilemma about this terse user-provided choice:\s*(?P<situation>.*?)"
    r"\.\s*The situation may involve competing duties, relationships, values, needs, or responsibilities\.",
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
    r"Task:|"
    r"Rules:|"
    r"Context package:|"
    r"Compact dilemma:|"
    r"Dilemma:|"
    r"Must stay focused on these user-topic words:|"
    r"User-topic words:|"
    r"Tone mode:|"
    r"Relationship context:|"
    r"Retrieved scriptures:|"
    r"Citation cards:|"
    r"Citation anchors:|"
    r"Required citation anchors:|"
    r"Deterministic output skeleton:|"
    r"Output skeleton:|"
    r"\d+\.\s*\[[^\]]+\]\s+.+|"
    r"\d+\.\s*.+\s+anchors:\s*.+|"
    r"\d+\.\s*Source:\s*.+|"
    r"\s*(?:Faith|Passage|Anchors to reuse|Principle):\s*.+|"
    r"Write exactly these \d+ labeled sections\b|"
    r"Fill only the text after each label\b|"
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
    r"Scripture grounding:\s*write (?:1-2|2) plain sentences\b"
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
    r"write (?:1-2|2) plain sentences"
    r")\b",
    re.I,
)
FOCUS_TERM_ALIASES = {
    "disciplined": ["discipline", "self-control"],
    "discipline": ["disciplined", "self-control"],
    "grudge": ["grudges", "resentment", "forgiveness", "anger", "hurt", "attachment", "hatred"],
    "grudges": ["grudge", "resentment", "forgiveness", "anger", "hurt", "attachment", "hatred"],
    "resentment": ["grudge", "grudges", "forgiveness", "anger", "hurt", "attachment", "hatred"],
    "resentments": ["grudge", "grudges", "resentment", "forgiveness", "anger", "hurt", "attachment", "hatred"],
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

SYNTHESIS_SYSTEM_PROMPT = (
    "You are Anayaa, a calm and practical moral guide. "
    "Give a clear answer for the user's real situation before offering reflection. "
    "Stay human, specific, and useful; avoid sounding academic, mystical, or sermon-like. "
    "Use only the dynamic dilemma and retrieved scripture text as evidence. "
    "Do not invent facts, motives, outcomes, citations, verse meanings, or personal details. "
    "If the dilemma is short or vague, say only what can be safely inferred and keep the guidance general. "
    "Write exactly these 5 labeled sections, 210 words or fewer total. "
    "Do not design a new structure; fill only the deterministic skeleton from the user message. "
    "Do not print bracketed helper text from the skeleton. "
    "Use simple everyday words. Each title must be visible at the start of its own line: "
    "One-line summary: answer the dilemma directly in one compact sentence. "
    "Reflection: explain the feeling or conflict in simple words, without blaming the user. "
    "Judgement: say what choice seems wisest and kindest, without naming scripture sources, chapters, verses, or citation labels. "
    "Next step: give a useful small sequence the user can take today in plain prose: one concrete action, one way to prepare, "
    "and one calm follow-through if the situation still feels hard or does not improve. Do not use literal sublabels such as "
    "Preparation detail or Calm follow-through. "
    "Only mention another person listening or not listening when the dilemma confirms a relationship, workplace, family, "
    "or caregiving conflict. For patience, discipline, identity, anxiety, or other self-regulation questions, make the "
    "Next step an inner practice plus one small duty or action, not a conversation plan. "
    "Do not make the whole Next step only writing, documenting, or gathering evidence; use notes only to support "
    "a real-world conversation, boundary, repair, protection, or ethical choice. "
    "For follow-up friendship repair after the user told the truth, apologized, or tried to repair harm and the friend stopped talking, "
    "do not tell the user to keep pushing. The Next step should be one short accountable message, then respectful space, "
    "with one later gentle check-in if appropriate. "
    "For business, money, workplace, or unfair-treatment dilemmas, include a specific constructive conversation "
    "or accountability move plus a brief fact-recording/protection detail when useful. "
    "Scripture grounding: write 1-2 plain sentences explaining how the retrieved citation cards support the advice; "
    "name every exact source from Required citation anchors and reuse at least one anchor keyword from each. "
    "When two or more citation cards are available, name at least two exact sources. "
    "Keep scripture names, chapter numbers, verse numbers, and citation labels only in Scripture grounding; "
    "do not put them in One-line summary, Reflection, Judgement, or Next step. "
    "In Scripture grounding, never mix sources: if a sentence quotes or references Romans, the sentence subject must be "
    "Romans or Holy Bible, not Bhagavad Gita, Dhammapada, Quran, or another scripture. "
    "Only make claims supported by the dilemma or retrieved scriptures. If a detail is not given, keep the wording general. "
    "Use the relationship context from the dynamic input: if no specific role is confirmed, use neutral wording like "
    "the other person or them; do not invent mom, parent, spouse, manager, or friend. If confirmed roles are listed, "
    "use only those confirmed roles or neutral wording, and do not change one relationship into another. "
    "If a private name was redacted, never print [NAME_REDACTED] in final guidance. "
    "For one-word, fragmentary, or broad questions, do not invent a scenario; answer the dharma meaning of the words provided. "
    "For caregiver-burnout questions involving parent care plus exhaustion, hopelessness, or giving up, treat exhaustion, "
    "hopelessness, and 'giving up' as the urgent center. The Next step must not start with business finances, debt tracking, "
    "saving money, or productivity. The Next step should tell the user to contact one real person today, say they are burned "
    "out and cannot carry this alone, and ask for one concrete relief action such as parent-care coverage, a meal, a ride, "
    "or help calling a doctor, social worker, or respite resource. If the user may harm themselves or cannot stay safe, "
    "tell them to contact local emergency or crisis support now. Keep business decisions secondary until immediate support "
    "and rest are in place. "
    "For conflict questions involving betrayal, lies, revenge, retaliation, hatred, or anger toward another person, "
    "make the Next step calm and proportionate. Plain explanation questions about anger or judgement are not "
    "betrayal/revenge dilemmas; explain the concept without adding retaliation instructions. The One-line summary should "
    "say not to seek revenge, to protect yourself with truth and boundaries, and that forgiveness can be a later process; "
    "do not frame protection as the opposite of forgiveness. Do not say the user should choose lawful protection rather than "
    "trying to forgive. Do not use the phrase lawful protection for ordinary lies or betrayal; say truth and calm boundaries instead. "
    "Tell the user not to retaliate today, to speak once calmly when safe, name the hurt or concern clearly, and give the other person "
    "a real chance to respond. If they do not listen, tell the user to stop repeating the argument, set a clear boundary, "
    "and note key facts only if it helps protect truth or prevent further harm. Do not make law enforcement or authority escalation the default first step. "
    "Mention a trusted person or appropriate authority only if the lies affect safety, work, school, housing, or reputation; "
    "mention emergency support only for threats, stalking, or immediate danger. Do not mention legal action unless the user "
    "describes a concrete legal threat, safety threat, stalking, workplace/school action, or serious reputation harm. "
    "For confidentiality, secret, or privacy dilemmas where keeping the secret may let someone be harmed, do not treat secrecy as absolute. "
    "The Next step should first assess whether the harm risk is serious or immediate, then disclose only the minimum necessary information "
    "to someone able to protect the person at risk, or seek confidential advice from a trusted responsible person if the risk is unclear. "
    "Do not tell the user to broadcast the secret, punish the friend, or keep silent when serious harm is likely. "
    "For dropshipping or business-model scam questions, answer directly whether the business model is automatically wrong: "
    "say it is not automatically scamming, but it becomes unethical if it hides risk, misleads customers, uses unreliable "
    "fulfillment, conceals delays, refuses fair refunds, or avoids accountability. Do not assume the user has invested money, "
    "suffered losses, or already started the business. Do not name specific commercial platforms, tools, or companies unless "
    "the user named them. "
    "For other business-integrity questions, answer the user's exact wealth-versus-integrity conflict directly: say that "
    "pursuing wealth is not wrong by itself, but pursuing wealth at the cost of honesty, fairness, lawful conduct, or integrity "
    "is not wise. Do not turn the question into dropshipping, scamming, or a specific business model unless the user named one. "
    "Keep the practical step focused on identifying the exact corner the user feels tempted to cut and choosing an ethical alternative. "
    "The Summary must clearly address the user's actual dilemma and should reuse at least one user-topic word naturally. "
    "Do not include markdown, bullets, numbered steps, or generic openers like 'As you navigate'. "
    "Avoid abstract filler and ornate phrases such as 'cultivating self-awareness', 'delicate situation', 'right intention', "
    "'moral pathway', and 'may this guidance inspire you'. "
    "The user's message contains the compact dynamic payload at the end: compact dilemma, topic words, tone, "
    "relationship context, citation cards, required citation anchors, and the deterministic output skeleton."
)

MAX_SYNTHESIS_CITATIONS = 2
MAX_SYNTHESIS_DILEMMA_CHARS = 520
MAX_CITATION_PASSAGE_CHARS = 260
MAX_CITATION_PRINCIPLE_CHARS = 160

SYNTHESIS_OUTPUT_SKELETON = "\n".join(
    [
        "Summary: [direct answer in one compact sentence]",
        "Reflection: [name the feeling or conflict without blame]",
        "Judgement: [wisest and kindest choice; no scripture names or verse references here]",
        "Next step: [one plain-prose action today; no extra sublabels]",
        "Scripture grounding: [1-2 sentences naming exact citation-card source names and anchor words]",
    ]
)
ORDERED_SECTION_LABELS = ["Summary", "Reflection", "Judgement", "Next step", "Scripture grounding"]
ORDERED_SECTION_RE = re.compile(
    r"^(summary|reflection|judg(?:e)?ment|next step|scripture grounding)\s*:\s*(.*)$",
    re.I | re.M,
)


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
    prompt_pack = _synthesis_prompt_pack_metrics(safe_dilemma, prompt, citations)
    started = time.perf_counter()
    system_message = SYNTHESIS_SYSTEM_PROMPT
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
            pathway = _repair_synthesis_sections(
                safe_dilemma,
                citations,
                _clean_synthesis_output((data.get("message") or {}).get("content", "")),
            )
            if not pathway:
                raise ValueError("Empty LLM response")

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            rejection_reason = _synthesis_rejection_reason(safe_dilemma, citations, pathway)
            if rejection_reason:
                retry_reason = rejection_reason
                if _should_retry_synthesis_rejection(rejection_reason):
                    caregiver_retry_instruction = ""
                    if _is_caregiver_burnout_dilemma(safe_dilemma):
                        caregiver_retry_instruction = (
                            "This is a caregiver-burnout and hopelessness query. The answer must explicitly center "
                            "burnout, exhaustion, or hopelessness; tell the user to contact one real person today; "
                            "ask for one concrete relief action such as care coverage, a meal, a ride, or help calling "
                            "a doctor, social worker, or respite resource; and include a safety line such as contacting "
                            "emergency or crisis support now if they may harm themselves or cannot stay safe. "
                            "Keep business decisions secondary until support and rest are in place. "
                        )
                    retry_system_message = (
                        f"{system_message} "
                        "Your previous draft was incomplete or not visibly grounded. Regenerate the full answer now. "
                        "You must include all 5 labels exactly once, and the final label must be "
                        "Scripture grounding: with the retrieved source names and their anchor keywords. "
                        f"{caregiver_retry_instruction}"
                        "Do not mention scripture sources, chapters, verses, or citation labels before Scripture grounding. "
                        "Do not attach a quote, chapter, or verse reference from one scripture to a different scripture source."
                    )
                    retry_response = await client.post(
                        "/api/chat",
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": retry_system_message},
                                {"role": "user", "content": prompt},
                            ],
                            "stream": False,
                            "think": False,
                            "keep_alive": "30m",
                            "options": synthesis_options,
                        },
                    )
                    retry_response.raise_for_status()
                    retry_data = retry_response.json()
                    retry_pathway = _repair_synthesis_sections(
                        safe_dilemma,
                        citations,
                        _clean_synthesis_output((retry_data.get("message") or {}).get("content", "")),
                    )
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
                        "synthesisInput": prompt_pack,
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
                "synthesisInput": prompt_pack,
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
    visible_dilemma = _visible_dilemma_text(dilemma)
    compact_dilemma = _compact_synthesis_context(visible_dilemma)
    citation_cards, anchor_lines = _build_citation_cards(citations)
    citations_block = "\n".join(citation_cards)
    anchors_block = "\n".join(anchor_lines)
    tone = tone_msg or "Balanced guidance mode"
    focus_terms = _query_focus_terms(visible_dilemma)
    focus_block = ", ".join(focus_terms) if focus_terms else "the user's exact dilemma"
    relationship_context = _relationship_role_context(visible_dilemma)
    return (
        "Task:\n"
        "Fill the deterministic output skeleton. Do not add headings, bullets, markdown, citations, or new labels. "
        "Replace bracketed helper text with final user-facing wording.\n\n"
        f"Compact dilemma:\n{compact_dilemma}\n\n"
        f"User-topic words:\n{focus_block}\n\n"
        f"Tone mode: {tone}\n\n"
        f"Relationship context: {relationship_context}\n\n"
        f"Citation cards:\n{citations_block}\n\n"
        f"Required citation anchors:\n{anchors_block}\n\n"
        "Rules:\n"
        "- Use scripture source names, chapters, verses, and citation labels only in Scripture grounding.\n"
        "- In Scripture grounding, name each source from Required citation anchors and reuse at least one anchor word for each.\n"
        "- Keep Judgement practical and source-free.\n\n"
        f"Deterministic output skeleton:\n{SYNTHESIS_OUTPUT_SKELETON}"
    )


def _build_citation_cards(citations: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    cards: list[str] = []
    anchor_lines: list[str] = []
    for idx, citation in enumerate(citations[:MAX_SYNTHESIS_CITATIONS], start=1):
        keywords = _citation_anchor_keywords(citation)
        citation_label = _citation_reference_label(citation)
        passage = _truncate_for_prompt(str(citation.get("translation") or ""), MAX_CITATION_PASSAGE_CHARS)
        principle = _citation_principle(citation, keywords)
        anchors = ", ".join(keywords) if keywords else str(citation.get("source") or "retrieved scripture")
        cards.append(
            "\n".join(
                [
                    f"{idx}. Source: {citation_label}",
                    f"   Faith: {citation.get('faith') or 'unspecified'}",
                    f"   Passage: \"{passage}\"",
                    f"   Anchors to reuse: {anchors}",
                    f"   Principle: {principle}",
                ]
            )
        )
        anchor_lines.append(f"{idx}. {citation_label} anchors: {anchors}")
    return cards, anchor_lines


def _citation_anchor_keywords(citation: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    for keyword in citation.get("keywords", [])[:4]:
        normalized = str(keyword).strip().lower()
        if normalized and normalized not in keywords:
            keywords.append(normalized)
    return keywords


def _citation_principle(citation: dict[str, Any], keywords: list[str]) -> str:
    context = _truncate_for_prompt(str(citation.get("context") or ""), MAX_CITATION_PRINCIPLE_CHARS)
    if context:
        return context
    if keywords:
        return f"Use this card for: {', '.join(keywords)}."
    return "Use only the passage and exact source name from this card."


def _compact_synthesis_context(dilemma: str) -> str:
    text = re.sub(r"\s+", " ", _visible_dilemma_text(dilemma)).strip()
    if len(text) <= MAX_SYNTHESIS_DILEMMA_CHARS:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        candidate = " ".join([*kept, sentence]).strip()
        if len(candidate) > MAX_SYNTHESIS_DILEMMA_CHARS:
            break
        kept.append(sentence)
    compact = " ".join(kept).strip() or text[:MAX_SYNTHESIS_DILEMMA_CHARS]
    if "?" in text and "?" not in compact:
        question_tail = text.rsplit("?", 1)[0].rsplit(".", 1)[-1].strip()
        if question_tail:
            compact = _truncate_for_prompt(f"{compact} {question_tail}?", MAX_SYNTHESIS_DILEMMA_CHARS)
    return compact.rstrip(" ,;:") + ("..." if len(compact) < len(text) and not compact.endswith("...") else "")


def _truncate_for_prompt(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 3].rsplit(" ", 1)[0].strip()
    return f"{truncated}..." if truncated else text[:max_chars]


def _synthesis_prompt_pack_metrics(dilemma: str, prompt: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    visible_dilemma = _visible_dilemma_text(dilemma)
    compact_dilemma = _compact_synthesis_context(visible_dilemma)
    original_context_tokens = max(1, len(visible_dilemma) // 4)
    compact_context_tokens = max(1, len(compact_dilemma) // 4)
    packed_prompt_tokens = max(1, len(prompt) // 4)
    return {
        "method": "deterministic_context_pack",
        "citationCards": min(len(citations), MAX_SYNTHESIS_CITATIONS),
        "contextTokensApprox": original_context_tokens,
        "compactContextTokensApprox": compact_context_tokens,
        "packedPromptTokensApprox": packed_prompt_tokens,
        "contextCompressionRatio": f"{original_context_tokens / max(compact_context_tokens, 1):.1f}x",
    }


def _citation_reference_label(citation: dict[str, Any]) -> str:
    parts = [
        _clean_citation_label_part(str(citation.get("source") or "").strip()),
        _clean_citation_label_part(str(citation.get("chapter") or "").strip()),
        _clean_citation_label_part(str(citation.get("verse") or "").strip()),
    ]
    return ", ".join(part for part in parts if part) or "retrieved scripture"


def _clean_citation_label_part(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"(?:\[NAME_REDACTED\]|the other person)\s*(?=(?:Al-)?Quran\b|Quran\b|Ma['’]idah\b)", "", text, flags=re.I)
    text = re.sub(r"^(?:the other person|\[NAME_REDACTED\])\s*", "", text)
    return text.strip(" ,")


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
    return "\n".join(_render_ordered_synthesis_sections(_merge_duplicate_answer_sections(normalized)))


def _render_ordered_synthesis_sections(lines: list[str]) -> list[str]:
    sections: dict[str, str] = {}
    current_label = ""
    for line in lines:
        match = ORDERED_SECTION_RE.match(line)
        if match:
            raw_label = match.group(1).lower()
            label = "Judgement" if raw_label in {"judgement", "judgment"} else BARE_ANSWER_LABELS.get(raw_label, "Summary")
            if raw_label == "summary":
                label = "Summary"
            text = match.group(2).strip()
            sections[label] = f"{sections.get(label, '').rstrip()} {text}".strip() if sections.get(label) else text
            current_label = label
            continue
        if current_label and line.strip():
            sections[current_label] = f"{sections[current_label].rstrip()} {line.strip()}".strip()

    if not sections:
        return lines
    return [f"{label}: {sections[label]}" if sections.get(label) else f"{label}:" for label in ORDERED_SECTION_LABELS if label in sections]


def _parse_synthesis_sections(pathway: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_label = ""
    for raw_line in str(pathway or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = ORDERED_SECTION_RE.match(line)
        if match:
            raw_label = match.group(1).lower()
            label = "Judgement" if raw_label in {"judgement", "judgment"} else BARE_ANSWER_LABELS.get(raw_label, "Summary")
            if raw_label == "summary":
                label = "Summary"
            sections[label] = match.group(2).strip()
            current_label = label
            continue
        if current_label:
            sections[current_label] = f"{sections.get(current_label, '').rstrip()} {line}".strip()
    return sections


def _render_synthesis_sections(sections: dict[str, str]) -> str:
    return "\n".join(
        f"{label}: {sections[label]}" if sections.get(label) else f"{label}:"
        for label in ORDERED_SECTION_LABELS
        if label in sections
    )


def _repair_synthesis_sections(dilemma: str, citations: list[dict[str, Any]], pathway: str) -> str:
    sections = _parse_synthesis_sections(pathway)
    if not sections:
        return pathway
    if _is_confidentiality_safety_dilemma(dilemma):
        sections = _repair_confidentiality_safety_sections(sections)
    if _is_friend_repair_follow_up_dilemma(dilemma):
        sections = _repair_friend_follow_up_sections(sections)
    if "Next step" in sections:
        sections["Next step"] = _repair_next_step_for_dilemma(dilemma, sections["Next step"])
    if "Scripture grounding" in sections:
        sections["Scripture grounding"] = _deterministic_scripture_grounding(dilemma, citations)
    return _render_synthesis_sections(sections)


def _repair_confidentiality_safety_sections(sections: dict[str, str]) -> dict[str, str]:
    repaired = {**sections}
    repaired["Summary"] = (
        "Do not treat confidentiality as absolute if keeping a secret may allow real harm; protect safety with the least necessary disclosure."
    )
    repaired["Reflection"] = (
        "This is hard because loyalty to a friend's trust is pulling against responsibility for someone who may be hurt."
    )
    repaired["Judgement"] = (
        "The wisest and kindest choice is to protect the person at risk while sharing only what is needed with someone able to help."
    )
    repaired["Next step"] = (
        "Today, decide whether the risk is serious or immediate. If someone may be harmed, tell only the person best able to protect them, "
        "using the minimum necessary facts; if the risk is unclear, ask a trusted responsible adult, supervisor, counselor, or appropriate safety contact for confidential guidance."
    )
    return repaired


def _repair_friend_follow_up_sections(sections: dict[str, str]) -> dict[str, str]:
    repaired = {**sections}
    repaired["Summary"] = (
        "After you told the truth and your friend stopped talking, the kindest repair is accountability without pressure: offer one calm message, then give your friend space."
    )
    repaired["Reflection"] = (
        "It hurts when honesty leads to silence, but your friend's distance may be their way of processing what happened."
    )
    repaired["Judgement"] = (
        "The wisest choice is to respect their space while staying ready to repair the harm without defending yourself or forcing a response."
    )
    repaired["Next step"] = (
        "Today, send one short message that accepts the hurt, says you will give them space, and leaves the door open to talk when they are ready. "
        "After that, stop repeating the apology for now; if some time passes, make one gentle check-in without demanding forgiveness."
    )
    return repaired


def _repair_next_step_for_dilemma(dilemma: str, next_step: str) -> str:
    visible = _visible_dilemma_text(dilemma)
    lower_dilemma = visible.lower()
    lower_step = str(next_step or "").lower()
    has_relationship_context = bool(_relationship_role_groups(visible))
    template_style_leak = bool(
        re.search(
            r"\b(?:preparation detail|calm follow[- ]through|before calling|immediate solutions|brainstorm ways)\b",
            lower_step,
        )
    )
    invented_conversation = (
        not has_relationship_context
        and (
            re.search(
                r"\b(friend|family member|trusted person|other person|they do not listen|they don't listen|call(?:ing)?|conversation)\b",
                lower_step,
            )
            or "before our conversation" in lower_step
            or "emotional support" in lower_step
        )
    )
    explanation_query = _is_explanation_style_query(visible)
    if explanation_query and invented_conversation:
        return _explanation_next_step_for_query(visible)

    cleaned_next_step = _strip_next_step_template_sublabels(next_step)
    if explanation_query and template_style_leak:
        return cleaned_next_step
    self_regulation_query = any(
        phrase in lower_dilemma
        for phrase in [
            "patience",
            "things don't go my way",
            "things do not go my way",
            "discipline",
            "disciplined",
            "self-control",
            "anxiety",
            "worry",
        ]
    )
    if invented_conversation and _is_gift_time_money_choice(visible):
        return (
            "Today, choose one specific way to give time, such as a visit, shared meal, call, or helping with something "
            "they care about. If time is not possible, give a modest useful gift with a personal note, keeping the focus "
            "on care rather than price."
        )
    if invented_conversation and not self_regulation_query:
        return _choice_next_step_for_query(visible)
    if self_regulation_query and (
        template_style_leak
        or re.search(r"\b(friend|family member|conversation|calling?|emotional support)\b", lower_step)
    ):
        return (
            "Today, pause for one minute before reacting, name one thing outside your control, and choose one small duty "
            "you can do with care. If frustration returns, repeat the pause and adjust the next action instead of forcing the outcome."
        )
    return cleaned_next_step


def _is_explanation_style_query(dilemma: str) -> bool:
    lower = _visible_dilemma_text(dilemma).lower()
    return bool(re.search(r"\b(?:explain|what is|what does|meaning of|define)\b", lower))


def _explanation_next_step_for_query(dilemma: str) -> str:
    focus_terms = _query_focus_terms(dilemma)
    topic = " and ".join(focus_terms[:2]) if focus_terms else "this teaching"
    return (
        f"Today, connect {topic} to one real choice: pause, ask what would be truthful and kind, "
        "and take one small action that fits. If it still feels abstract, bring one concrete situation "
        "to Anayaa instead of staying with a general explanation."
    )


def _is_gift_time_money_choice(dilemma: str) -> bool:
    lower = _current_dilemma_text(dilemma).lower()
    return bool(
        re.search(r"\b(?:gift|give|giving)\b", lower)
        and "time" in lower
        and re.search(r"\b(?:money|wealth|material)\b", lower)
    )


def _is_confidentiality_safety_dilemma(dilemma: str) -> bool:
    lower = _current_dilemma_text(dilemma).lower()
    confidentiality_terms = re.search(r"\b(?:confidential|confidentiality|secret|privacy|private|trust)\b", lower)
    safety_terms = re.search(r"\b(?:harm|harmed|harmful|hurt|hurting|danger|dangerous|unsafe|safety|risk|protect)\b", lower)
    disclosure_terms = re.search(r"\b(?:break|tell|disclose|share|reveal|keep|keeping|hide|hiding)\b", lower)
    return bool(confidentiality_terms and safety_terms and disclosure_terms)


def _is_friend_repair_follow_up_dilemma(dilemma: str) -> bool:
    visible = _visible_dilemma_text(dilemma).lower()
    current = _current_dilemma_text(dilemma).lower()
    friend_terms = re.search(r"\bfriend\b", visible)
    repair_context = re.search(r"\b(?:truth|truthful|told the truth|lie|lied|apolog(?:y|ize|ized)|sorry|guilt|guilty|repair)\b", visible)
    silence_terms = re.search(
        r"\b(?:stopped talking|stop talking|not talking|won't talk|wouldn't talk|silent|silence|ignoring|ignored|no response|space)\b",
        current,
    )
    return bool(friend_terms and repair_context and silence_terms)


def _choice_next_step_for_query(dilemma: str) -> str:
    focus_terms = _query_focus_terms(dilemma)
    topic = " and ".join(focus_terms[:2]) if focus_terms else "the two options"
    return (
        f"Today, compare {topic} by asking which option serves the real person and the real duty best. "
        "Then choose one small concrete action that expresses care without trying to prove your worth."
    )


def _strip_next_step_template_sublabels(next_step: str) -> str:
    text = str(next_step or "").strip()
    text = re.sub(r"\bPreparation detail\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\bCalm follow[- ]through(?:\s+if[^:]{0,80})?\s*:\s*", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _deterministic_scripture_grounding(dilemma: str, citations: list[dict[str, Any]]) -> str:
    grounded_parts: list[str] = []
    for citation in citations[:MAX_SYNTHESIS_CITATIONS]:
        label = _citation_reference_label(citation)
        anchors = _citation_anchor_keywords(citation)
        anchor_text = " and ".join(anchors[:2]) if anchors else "the retrieved passage"
        grounded_parts.append(f"{label} emphasizes {anchor_text}")
    if not grounded_parts:
        return "The retrieved scripture evidence was not available, so Anayaa cannot add a grounded scripture explanation."
    if len(grounded_parts) == 1:
        return f"{grounded_parts[0]}, which supports acting carefully and keeping the next step grounded in that teaching."
    if _is_job_security_purpose_choice(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support weighing security alongside purpose, then choosing the offer that lets you act responsibly and meaningfully."
        )
    if _is_gift_time_money_choice(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support choosing a gift by care, presence, and responsibility rather than by material value alone."
        )
    if _is_investment_risk_dilemma(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support treating wealth and opportunity with restraint, weighing risk, duty, and real needs before committing everything."
        )
    if _is_confidentiality_safety_dilemma(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support honoring trust with care while protecting people from harm through limited, responsible disclosure."
        )
    if _is_friend_repair_follow_up_dilemma(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support honest repair, patient restraint, and care for the friendship without forcing a response."
        )
    if _is_ai_moral_decision_dilemma(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support using AI as a tool for reflection while keeping moral responsibility, justice, and accountability with the person making the choice."
        )
    if _is_truthfulness_dilemma(dilemma):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support turning away from repeated falsehood and choosing honesty, accountability, and repair."
        )
    if any(
        phrase in _visible_dilemma_text(dilemma).lower()
        for phrase in ["patience", "things don't go my way", "things do not go my way"]
    ):
        return (
            f"{grounded_parts[0]}, while {grounded_parts[1]}. "
            "Together, these citations support taking the next right action patiently while staying responsible for effort rather than controlling every outcome."
        )
    return (
        f"{grounded_parts[0]}, while {grounded_parts[1]}. "
        "Together, these citations support choosing a practical next action that honors responsibility, care, and the real choice in front of the user."
    )


def _is_job_security_purpose_choice(dilemma: str) -> bool:
    lower = _current_dilemma_text(dilemma).lower()
    return bool(
        re.search(r"\b(?:job|career|work|offer|offers|livelihood)\b", lower)
        and "security" in lower
        and "purpose" in lower
    )


def _is_truthfulness_dilemma(dilemma: str) -> bool:
    lower = _current_dilemma_text(dilemma).lower()
    return bool(
        re.search(
            r"\b(?:lie|lies|lied|lying|liar|falsehood|falsehoods|dishonest|dishonesty|truth|truthful|caught)\b",
            lower,
        )
    )


def _is_investment_risk_dilemma(dilemma: str) -> bool:
    lower = _current_dilemma_text(dilemma).lower()
    investment_terms = re.search(r"\b(?:invest|investing|investment|crypto|opportunity|savings?)\b", lower)
    concentration_terms = re.search(r"\b(?:everything|all|entire|one|single|only|risk|risky|wealth|money)\b", lower)
    return bool(investment_terms and concentration_terms)


def _is_ai_moral_decision_dilemma(dilemma: str) -> bool:
    lower = _current_dilemma_text(dilemma).lower()
    return bool(
        re.search(r"\b(?:ai|artificial intelligence|algorithm|machine)\b", lower)
        and re.search(r"\b(?:moral|ethical|ethics|decision|decisions|choose|choice)\b", lower)
    )


def _current_dilemma_text(dilemma: str) -> str:
    visible = _visible_dilemma_text(dilemma)
    match = re.search(r"\bFollow-up question:\s*(?P<current>.+)$", visible, flags=re.I)
    if match:
        return match.group("current").strip(" .?!")
    return visible


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
    match = TERSE_CHOICE_FRAME_RE.match(text)
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
        "decision",
        "facts",
        "guide",
        "harmful",
        "inventing",
        "kindest",
        "least",
        "missing",
        "most",
        "people",
        "provided",
        "situation",
        "their",
        "there",
        "these",
        "this",
        "those",
        "through",
        "between",
        "choice",
        "define",
        "offers",
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
        "explain",
        "meaning",
        "simple",
        "words",
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
    if _has_caregiver_parent_context(text):
        groups.add("parent")
    return groups


def _relationship_role_context(dilemma: str) -> str:
    groups = _relationship_role_groups(dilemma)
    if not groups:
        return "No specific relationship role is confirmed."

    allowed = ", ".join(RELATIONSHIP_ROLE_DISPLAY[group] for group in sorted(groups))
    context = f"Known relationship roles from the dilemma: {allowed}."
    if "parent" in groups and _has_caregiver_parent_context(dilemma):
        context += " Parent-care wording is allowed because the dilemma is about caregiving duties."
    return context


def _is_summary_relevant(dilemma: str, citations: list[dict[str, Any]], pathway: str) -> bool:
    pathway_lower = pathway.lower()
    focus_terms = _query_focus_terms(dilemma)
    if focus_terms:
        matches = [term for term in focus_terms if _focus_term_in_text(term, pathway_lower)]
        required_matches = 1 if len(focus_terms) <= 2 else 2
        if len(matches) < required_matches and not (
            _is_betrayal_revenge_dilemma(dilemma) and _is_betrayal_revenge_pathway_relevant(pathway)
        ) and not (
            _is_caregiver_burnout_dilemma(dilemma) and _is_caregiver_burnout_pathway_relevant(pathway)
        ) and not (
            _is_friend_repair_follow_up_dilemma(dilemma) and _is_friend_repair_pathway_relevant(pathway)
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
    if _is_caregiver_burnout_dilemma(dilemma) and _is_caregiver_burnout_pathway_relevant(pathway):
        return True
    if _is_friend_repair_follow_up_dilemma(dilemma) and _is_friend_repair_pathway_relevant(pathway):
        return True
    return _is_betrayal_revenge_dilemma(dilemma) and _betrayal_revenge_citation_grounded(citations, pathway)


def _is_caregiver_burnout_pathway_relevant(pathway: str) -> bool:
    lower = pathway.lower()
    burnout_terms = {
        "burned out",
        "burnt out",
        "burnout",
        "hopeless",
        "exhausted",
        "giving up",
        "cannot carry",
        "can't carry",
        "overwhelmed",
        "despair",
        "too much",
        "worn down",
    }
    support_terms = {
        "contact",
        "call",
        "trusted",
        "person",
        "someone",
        "friend",
        "family",
        "relative",
        "neighbor",
        "support",
        "relief",
        "cover",
        "coverage",
        "meal",
        "ride",
        "doctor",
        "social worker",
        "respite",
        "rest",
    }
    safety_terms = {
        "safe",
        "safety",
        "harm",
        "hurt yourself",
        "at risk",
        "risk of",
        "emergency",
        "crisis",
        "988",
        "lifeline",
    }
    return (
        any(term in lower for term in burnout_terms)
        and any(term in lower for term in support_terms)
        and any(term in lower for term in safety_terms)
    )


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


def _is_friend_repair_pathway_relevant(pathway: str) -> bool:
    lower = pathway.lower()
    relationship_terms = {"friend", "friendship"}
    repair_terms = {"truth", "truthful", "accountability", "apology", "apologize", "repair", "hurt"}
    restraint_terms = {"space", "without pressure", "gentle check-in", "ready", "forcing", "response"}
    return (
        any(term in lower for term in relationship_terms)
        and any(term in lower for term in repair_terms)
        and any(term in lower for term in restraint_terms)
    )


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


def _scripture_reference_outside_grounding(citations: list[dict[str, Any]], pathway: str) -> bool:
    outside = _normalized_text(_pathway_without_scripture_grounding(pathway))
    if not outside:
        return False
    for citation in citations:
        if _contains_any_source_alias(outside, _source_aliases(citation)):
            return True
    return False


def _pathway_without_scripture_grounding(pathway: str) -> str:
    return re.sub(
        r"(?:^|[\n.]\s*)scripture grounding\s*:\s*.*?(?=(?:\n|$)\s*(?:one[- ]line summary|summary|reflection|judg(?:e)?ment|next step)\s*:|\Z)",
        " ",
        str(pathway or ""),
        flags=re.I | re.S,
    )


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
    if _scripture_reference_outside_grounding(citations, pathway):
        return "scripture_reference_outside_grounding"
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
        "scripture_reference_outside_grounding",
    }


def _contains_prompt_like_response_text(pathway: str) -> bool:
    return bool(PROMPT_LIKE_RESPONSE_RE.search(str(pathway or "")))


def _unsupported_relationship_drift(dilemma: str, pathway: str) -> bool:
    allowed_groups = _relationship_role_groups(dilemma)
    caregiver_parent_context = _has_caregiver_parent_context(dilemma)
    if caregiver_parent_context:
        allowed_groups.add("parent")
    for group, pattern in RELATIONSHIP_DRIFT_PATTERNS.items():
        if group in allowed_groups:
            continue
        for match in pattern.finditer(str(pathway or "")):
            if caregiver_parent_context and _is_caregiver_support_helper_reference(pathway, match.start(), match.end()):
                continue
            return True
    return False


def _is_caregiver_support_helper_reference(pathway: str, start: int, end: int) -> bool:
    """Allow possible helpers in caregiver next steps without treating them as confirmed roles."""
    text = str(pathway or "")
    if _section_label_at(text, start) != "next step":
        return False
    window = text[max(0, start - 120) : min(len(text), end + 160)].lower()
    support_actions = {
        "ask",
        "call",
        "contact",
        "reach out",
        "tell",
        "request",
        "help",
        "support",
        "cover",
        "coverage",
        "relief",
    }
    return any(term in window for term in support_actions)


def _section_label_at(pathway: str, index: int) -> str:
    labels = list(ORDERED_SECTION_RE.finditer(str(pathway or "")))
    active = ""
    for match in labels:
        if match.start() > index:
            break
        active = match.group(1).lower()
    return "judgement" if active in {"judgement", "judgment"} else active


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


def _has_caregiver_parent_context(value: str) -> bool:
    lower = _visible_dilemma_text(value).lower()
    parent_terms = {"parent", "parents", "mother", "father", "mom", "dad"}
    caregiver_terms = {"care", "caregiver", "caring", "sick", "duties", "duty", "share"}
    return any(term in lower for term in parent_terms) and any(term in lower for term in caregiver_terms)
