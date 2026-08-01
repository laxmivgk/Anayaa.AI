"""Local-first named entity recognition for privacy scrubbing."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NerEntity:
    text: str
    label: str
    start: int
    end: int
    score: float = 1.0
    source: str = "heuristic"


class NerRecognizer(Protocol):
    def detect(self, text: str) -> list[NerEntity]:
        ...


CAPITALIZED_TOKEN = r"[A-Z][a-z'’-]{1,31}"
FULL_NAME_RE = re.compile(rf"\b({CAPITALIZED_TOKEN}(?:\s+{CAPITALIZED_TOKEN}){{1,2}})\b")
LEADING_DETERMINERS_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

ENTITY_ALLOWLIST = {
    "al-quran",
    "anayaa",
    "anayaa ai",
    "bhagavad gita",
    "bible",
    "dhammapada",
    "galatians",
    "guru granth sahib",
    "holy bible",
    "interactive guidance",
    "isha",
    "isha upanishad",
    "jesus christ",
    "karaniya metta sutta",
    "lord krishna",
    "luke",
    "mahabharata",
    "matthew",
    "metta sutta",
    "new dilemma",
    "no relevant scripture",
    "quran",
    "ramayana",
    "rig veda",
    "romans",
    "safety review required",
    "scripture grounding",
    "surah",
    "sutta nipata",
    "the interactive guidance",
    "upanishad",
    "workflow notice",
}
ENTITY_LOCATION_ALLOWLIST = {
    "new york",
    "san francisco",
    "los angeles",
    "st jude",
}
ENTITY_TOKEN_BLOCKLIST = {
    "chapter",
    "guidance",
    "judgement",
    "next",
    "reflection",
    "scripture",
    "summary",
    "verse",
}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalized_entity(value: str) -> str:
    normalized = LEADING_DETERMINERS_RE.sub("", value).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _is_allowed_entity(value: str) -> bool:
    normalized = _normalized_entity(value)
    tokens = set(normalized.split())
    return (
        normalized in ENTITY_ALLOWLIST
        or normalized in ENTITY_LOCATION_ALLOWLIST
        or bool(tokens & ENTITY_TOKEN_BLOCKLIST)
    )


class HeuristicNerRecognizer:
    """Small offline fallback that recognizes person-like full names without a model download."""

    def detect(self, text: str) -> list[NerEntity]:
        entities: list[NerEntity] = []
        for match in FULL_NAME_RE.finditer(text):
            entity_text = match.group(1).strip()
            if _is_allowed_entity(entity_text):
                continue
            entities.append(
                NerEntity(
                    text=entity_text,
                    label="PERSON",
                    start=match.start(1),
                    end=match.end(1),
                    score=0.72,
                    source="heuristic",
                )
            )
        return entities


class TransformersNerRecognizer:
    """Use a locally cached Hugging Face token-classification model when configured."""

    def __init__(self, model_name: str, *, local_files_only: bool = True) -> None:
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=local_files_only)
        model = AutoModelForTokenClassification.from_pretrained(model_name, local_files_only=local_files_only)
        self._pipeline = pipeline(
            "ner",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
        )

    def detect(self, text: str) -> list[NerEntity]:
        entities: list[NerEntity] = []
        for item in self._pipeline(text):
            entity_text = str(item.get("word", "")).strip()
            label = str(item.get("entity_group") or item.get("entity") or "").upper()
            if not entity_text or _is_allowed_entity(entity_text):
                continue
            entities.append(
                NerEntity(
                    text=entity_text,
                    label=label,
                    start=int(item.get("start", 0) or 0),
                    end=int(item.get("end", 0) or 0),
                    score=float(item.get("score", 0.0) or 0.0),
                    source="transformers",
                )
            )
        return entities


@lru_cache(maxsize=1)
def get_ner_recognizer() -> NerRecognizer:
    if not _env_bool("PII_NER_ENABLED", True):
        return HeuristicNerRecognizer()

    model_name = os.environ.get("PII_NER_MODEL", "").strip()
    if model_name:
        try:
            recognizer = TransformersNerRecognizer(
                model_name,
                local_files_only=_env_bool("PII_NER_LOCAL_FILES_ONLY", True),
            )
            logger.info("Loaded local PII NER model %s", model_name)
            return recognizer
        except Exception as exc:
            if not _env_bool("PII_NER_FALLBACK_ENABLED", True):
                raise
            logger.warning("Local PII NER model unavailable; using heuristic recognizer: %s", exc)

    return HeuristicNerRecognizer()


def detect_named_entities(text: str) -> list[NerEntity]:
    return get_ner_recognizer().detect(text)


def person_entity_texts(text: str) -> list[str]:
    names: list[str] = []
    for entity in detect_named_entities(text):
        if entity.label.upper() not in {"PER", "PERSON"}:
            continue
        if not any(existing.lower() == entity.text.lower() for existing in names):
            names.append(entity.text)
    return names
