"""Small JSON extraction helpers for local structured-output models."""
from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(raw: str, *, object_name: str = "LLM response") -> dict[str, Any]:
    """Parse a JSON object from local-model output, repairing common syntax drift."""
    text = _strip_code_fence(str(raw or "").strip())
    candidates = [text, _object_candidate(text)]
    last_error: Exception | None = None
    for candidate in candidates:
        if not candidate:
            continue
        for repaired in _repair_candidates(candidate):
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if not isinstance(parsed, dict):
                raise ValueError(f"{object_name} JSON must be an object")
            return parsed
    if last_error:
        raise last_error
    raise ValueError(f"{object_name} JSON object not found")


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    return text


def _object_candidate(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""

    chars: list[str] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    started = False
    for char in text[start:]:
        if not started:
            if char != "{":
                continue
            started = True
            stack.append("}")
            chars.append(char)
            continue

        if in_string:
            if escaped:
                chars.append(char)
                escaped = False
                continue
            if char == "\\":
                chars.append(char)
                escaped = True
                continue
            if char == '"':
                chars.append(char)
                in_string = False
                continue
            chars.append(" " if char in "\r\n\t" else char)
            continue

        if char == '"':
            chars.append(char)
            in_string = True
            continue
        if char in "{[":
            stack.append("}" if char == "{" else "]")
            chars.append(char)
            continue
        if char in "}]":
            if stack and char == stack[-1]:
                stack.pop()
            chars.append(char)
            if not stack:
                return "".join(chars)
            continue
        chars.append(char)

    if in_string:
        chars.append('"')
    while stack:
        chars.append(stack.pop())
    return "".join(chars)


def _repair_candidates(candidate: str) -> list[str]:
    base = candidate.strip()
    repairs = [
        base,
        _basic_repair(base),
        _quote_bare_keys(_basic_repair(base)),
    ]
    deduped: list[str] = []
    for item in repairs:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _basic_repair(text: str) -> str:
    repaired = text.strip()
    repaired = repaired.replace("“", '"').replace("”", '"').replace("’", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    return repaired


def _quote_bare_keys(text: str) -> str:
    return re.sub(r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*:', r'\1"\2":', text)
