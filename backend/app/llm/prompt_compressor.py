from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.agents.pipeline_errors import ServiceUnavailableError
from app.config import get_settings

logger = logging.getLogger(__name__)

_compressor: Any | None = None
_compressor_failed = False


@dataclass
class CompressionResult:
    compressed_prompt: str
    compressed_question: str
    origin_tokens: int
    compressed_tokens: int
    compression_ratio: str
    enabled: bool
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "compressedPrompt": self.compressed_prompt,
            "compressedQuestion": self.compressed_question,
            "originTokens": self.origin_tokens,
            "compressedTokens": self.compressed_tokens,
            "compressionRatio": self.compression_ratio,
            "enabled": self.enabled,
            "method": self.method,
        }


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _resolve_device(preferred: str) -> str:
    if preferred != "auto":
        return preferred
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _passthrough_compress(context: str, question: str) -> CompressionResult:
    combined = f"{context}\n\n{question}".strip() if context else question
    tokens = _estimate_tokens(combined)
    return CompressionResult(
        compressed_prompt=combined,
        compressed_question=question,
        origin_tokens=tokens,
        compressed_tokens=tokens,
        compression_ratio="1.0x",
        enabled=False,
        method="passthrough",
    )


def _get_compressor() -> Any:
    global _compressor, _compressor_failed

    if _compressor_failed:
        raise ServiceUnavailableError("LLMLingua", "compressor failed to initialize on a previous attempt")
    if _compressor is not None:
        return _compressor

    settings = get_settings()
    try:
        from llmlingua import PromptCompressor

        device = _resolve_device(settings.llmlingua_device)
        _compressor = PromptCompressor(
            model_name=settings.llmlingua_model,
            use_llmlingua2=settings.llmlingua_use_v2,
            device_map=device,
        )
        return _compressor
    except Exception as exc:
        logger.error("LLMLingua init failed: %s", exc)
        _compressor_failed = True
        raise ServiceUnavailableError("LLMLingua", str(exc)) from exc


def _parse_compression_output(
    raw: Any,
    question: str,
    context_parts: list[str],
) -> CompressionResult:
    if isinstance(raw, dict):
        compressed = str(raw.get("compressed_prompt", question))
        origin = int(raw.get("origin_tokens", _estimate_tokens("\n\n".join(context_parts) + question)))
        compressed_tokens = int(raw.get("compressed_tokens", _estimate_tokens(compressed)))
        ratio = str(raw.get("ratio", f"{origin / max(compressed_tokens, 1):.1f}x"))
    else:
        compressed = str(raw)
        origin = _estimate_tokens("\n\n".join(context_parts) + question)
        compressed_tokens = _estimate_tokens(compressed)
        ratio = f"{origin / max(compressed_tokens, 1):.1f}x"

    return CompressionResult(
        compressed_prompt=compressed,
        compressed_question=question,
        origin_tokens=origin,
        compressed_tokens=compressed_tokens,
        compression_ratio=ratio,
        enabled=True,
        method="LLMLingua",
    )


def compress_query_prompt(
    question: str,
    context: str = "",
    keywords: list[str] | None = None,
) -> CompressionResult:
    settings = get_settings()
    question = question.strip()
    context_parts: list[str] = []
    if context.strip():
        context_parts.append(context.strip())
    if keywords:
        context_parts.append(f"Retrieval keywords: {', '.join(keywords)}")

    ctx = "\n\n".join(context_parts)
    if not settings.llmlingua_enabled:
        return _passthrough_compress(ctx, question)

    compressor = _get_compressor()
    force_tokens = ["\n", "?", ".", ":", ",", "—", "-"]
    try:
        if context_parts and settings.llmlingua_use_longllmlingua and not settings.llmlingua_use_v2:
            raw = compressor.compress_prompt(
                context_parts,
                question=question,
                rate=settings.llmlingua_compression_rate,
                condition_in_question="after_condition",
                reorder_context="sort",
                dynamic_context_compression_ratio=0.3,
                condition_compare=True,
                context_budget="+100",
                rank_method="longllmlingua",
            )
            result = _parse_compression_output(raw, question, context_parts)
            result.method = "LongLLMLingua"
            return result

        instruction = (
            "Dharma-guided moral reasoning assistant. "
            "Retrieve multi-faith scripture evidence for the user's dilemma."
        )
        context_block = "\n".join(context_parts) if context_parts else ""
        structured = (
            f"{instruction}\n\nContext:\n{context_block}\n\nQuestion:\n{question}"
            if context_block
            else question
        )
        raw = compressor.compress_prompt(
            structured,
            rate=settings.llmlingua_compression_rate,
            force_tokens=force_tokens,
        )
        result = _parse_compression_output(raw, question, context_parts)
        result.method = "LLMLingua-2" if settings.llmlingua_use_v2 else "LLMLingua"
        return result
    except ServiceUnavailableError:
        raise
    except Exception as exc:
        logger.error("LLMLingua compression failed: %s", exc)
        raise ServiceUnavailableError("LLMLingua", str(exc)) from exc
