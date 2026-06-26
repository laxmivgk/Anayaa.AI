"""LLM response generation via Ollama — no template fallback."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.agents.pipeline_errors import ServiceUnavailableError
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


async def prewarm_synthesizer() -> None:
    """Load the selected Ollama synthesizer model before the first user query."""
    settings = get_settings()
    model = select_model("synthesizer")
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=60.0) as client:
            response = await client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": "ready",
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"temperature": 0.0, "num_predict": 1, "num_ctx": 512},
                },
            )
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Ollama synthesizer warmup skipped: %s", exc)


async def generate_moral_pathway(
    dilemma: str,
    citations: list[dict[str, Any]],
    tone_msg: str = "",
) -> tuple[str, dict[str, Any]]:
    """Generate a moral pathway using a local LLM."""
    if not citations:
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

    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=120.0) as client:
            response = await client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are Anayaa, a calm and practical moral guide. "
                                "Give a clear answer for the user's real situation before offering reflection. "
                                "Stay human, specific, and useful; avoid sounding academic, mystical, or sermon-like. "
                                "Use only the user's dilemma and the retrieved scripture text as evidence. "
                                "Do not invent facts, motives, outcomes, citations, verse meanings, or personal details. "
                                "If the dilemma is short or vague, say only what can be safely inferred and keep the guidance general. "
                                "Do not use markdown, bullet points, or numbered lists."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"temperature": 0.0, "num_predict": 320, "num_ctx": 2048},
                },
            )
            response.raise_for_status()
            data = response.json()
            pathway = (data.get("message") or {}).get("content", "").strip()
            if not pathway:
                raise ValueError("Empty LLM response")

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            used_fallback = False
            if not _is_summary_relevant(safe_dilemma, citations, pathway):
                logger.warning("LLM synthesis drifted from query; using grounded fallback summary")
                pathway = _build_grounded_fallback_summary(safe_dilemma, citations)
                used_fallback = True

            metrics = {
                "engine": "Grounded fallback" if used_fallback else "Ollama LLM",
                "modelName": model,
                "ttftMs": elapsed_ms,
                "totalTokens": data.get("eval_count") or len(pathway) // 4,
                "tokPerSec": round((data.get("eval_count") or 1) / max(elapsed_ms / 1000, 0.01), 1),
                "kvCacheHit": False,
                "staticPromptCache": "Inactive",
                "memoryUsageMb": None,
            }
            return pathway, metrics
    except ServiceUnavailableError:
        raise
    except Exception as exc:
        logger.error("LLM synthesis failed: %s", exc)
        raise ServiceUnavailableError("Ollama LLM", str(exc)) from exc


def _build_synthesis_prompt(
    dilemma: str,
    citations: list[dict[str, Any]],
    tone_msg: str,
) -> str:
    dilemma = _visible_dilemma_text(dilemma)
    citation_lines = []
    for idx, citation in enumerate(citations[:3], start=1):
        citation_lines.append(
            f"{idx}. [{citation.get('faith')}] {citation.get('source')} "
            f"{citation.get('chapter')}:{citation.get('verse')} — "
            f"\"{citation.get('translation')}\""
        )
    citations_block = "\n".join(citation_lines)
    tone = tone_msg or "Balanced guidance mode"
    focus_terms = _query_focus_terms(dilemma)
    focus_block = ", ".join(focus_terms) if focus_terms else "the user's exact dilemma"
    return (
        f"Dilemma:\n{dilemma}\n\n"
        f"Must stay focused on these user-topic words:\n{focus_block}\n\n"
        f"Tone mode: {tone}\n\n"
        f"Retrieved scriptures:\n{citations_block}\n\n"
        "Write exactly these 5 labeled sections, 180 words or fewer total.\n"
        "Use simple everyday words. Each title must be visible at the start of its own line:\n"
        "One-line summary: answer the dilemma directly in one compact sentence.\n"
        "Reflection: explain the feeling or conflict in simple words, without blaming the user.\n"
        "Judgement: say what choice seems wisest and kindest.\n"
        "Next step: give one concrete, stable action the user can take today; include both a fact-recording step and a practical protection step when the dilemma involves business or money.\n"
        "Scripture grounding: write 2 plain sentences explaining how at least two retrieved scriptures support the advice; name the source or tradition when useful.\n"
        "Only make claims supported by the dilemma or retrieved scriptures. If a detail is not given, keep the wording general.\n"
        "For one-word, fragmentary, or broad questions, do not invent a scenario; answer the dharma meaning of the words the user provided.\n"
        "The Summary must clearly address the user's actual dilemma and should reuse at least one user-topic word naturally.\n"
        "Do not include markdown, bullets, numbered steps, or generic openers like 'As you navigate'.\n"
        "Avoid abstract filler and ornate phrases such as 'cultivating self-awareness', 'delicate situation', "
        "'right intention', 'moral pathway', and 'may this guidance inspire you'."
    )


def _visible_dilemma_text(dilemma: str) -> str:
    """Return the user-facing dilemma, not Anayaa's internal retrieval frame."""
    text = re.sub(r"\s+", " ", str(dilemma or "")).strip()
    match = DHARMA_FRAME_RE.match(text)
    if match:
        return match.group("situation").strip(" .?!")
    match = IDENTITY_FRAME_RE.match(text)
    if match:
        return f"{match.group('situation')}; {match.group('terms')}".strip(" .?!")
    return text


def _query_focus_terms(dilemma: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "again",
        "because",
        "could",
        "their",
        "there",
        "these",
        "those",
        "through",
        "under",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
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


def _is_summary_relevant(dilemma: str, citations: list[dict[str, Any]], pathway: str) -> bool:
    pathway_lower = pathway.lower()
    focus_terms = _query_focus_terms(dilemma)
    if focus_terms:
        matches = [term for term in focus_terms if term in pathway_lower]
        required_matches = 1 if len(focus_terms) <= 2 else 2
        if len(matches) < required_matches:
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

    return not citation_terms or any(term in pathway_lower for term in citation_terms[:8])


def _build_grounded_fallback_summary(dilemma: str, citations: list[dict[str, Any]]) -> str:
    visible_dilemma = _visible_dilemma_text(dilemma)
    dilemma_text = _shorten_sentence(visible_dilemma)
    citation_keywords = _citation_keywords(citations)
    grounding = ", ".join(citation_keywords[:3]) if citation_keywords else "careful and truthful action"

    if _is_livelihood_choice_dilemma(visible_dilemma):
        return "\n".join(
            [
                f"One-line summary: Make a thoughtful choice about {dilemma_text}, not a random one.",
                "Reflection: This is a question about responsibility, real needs, and choosing without panic.",
                "Judgement: Choose the option that responsibly supports your needs while staying honest, steady, and aligned with your abilities.",
                "Next step: Write down your non-negotiable needs, then compare each job option against income, dignity, location, growth, and family responsibilities.",
                f"Scripture grounding: The retrieved scriptures point toward {grounding}, so keep the advice tied to those themes. Use the citations as a boundary: act with integrity and avoid unsupported claims or harmful escalation.",
            ]
        )

    return "\n".join(
        [
            f"One-line summary: Focus on the real question you asked: {dilemma_text}.",
            "Reflection: The situation needs a careful response, not a rushed or imagined one.",
            "Judgement: Choose the action that is honest, kind, and least harmful.",
            "Next step: Write the concrete choice in front of you, then choose one practical action that protects responsibility, truth, and peace.",
            f"Scripture grounding: The retrieved scriptures point toward {grounding}, so keep the advice tied to those themes. Use the citations as a boundary: act with integrity and avoid unsupported claims or harmful escalation.",
        ]
    )


def _citation_keywords(citations: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for citation in citations:
        for raw_term in citation.get("keywords") or []:
            term = str(raw_term).strip().lower()
            if len(term) >= 4 and term not in terms:
                terms.append(term)
    return terms


def _is_livelihood_choice_dilemma(value: str) -> bool:
    lower = value.lower()
    livelihood_terms = {"job", "jobs", "work", "career", "livelihood"}
    choice_terms = {"random", "randomly", "needs", "need", "fulfills", "select", "choose"}
    return any(term in lower for term in livelihood_terms) and any(term in lower for term in choice_terms)


def _shorten_sentence(value: str, max_words: int = 18) -> str:
    words = re.sub(r"\s+", " ", value).strip(" .").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "..."
