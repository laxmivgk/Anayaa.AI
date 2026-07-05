"""Pipeline errors — no silent fallbacks; callers surface meaningful messages."""


class PipelineError(Exception):
    """Base error for pipeline stages that require explicit handling."""

    def __init__(self, message: str, *, user_message: str | None = None, code: str = "pipeline_error"):
        super().__init__(message)
        self.user_message = user_message or message
        self.code = code


class ServiceUnavailableError(PipelineError):
    def __init__(self, service: str, detail: str):
        super().__init__(
            f"{service} unavailable: {detail}",
            user_message=(
                f"The {service} service is required but unavailable ({detail}). "
                "Please ensure it is running and configured, then try again."
            ),
            code="service_unavailable",
        )
        self.service = service


class SynthesisRejectedError(PipelineError):
    def __init__(self, detail: str):
        super().__init__(
            f"LLM synthesis rejected: {detail}",
            user_message=(
                "Anayaa generated a draft, but it cannot be shown as final guidance because it drifted from your question "
                "or was not grounded enough in the retrieved scriptures. Try again with one concrete detail, or use "
                "The Interactive Guidance to choose clearer concepts and scriptures."
            ),
            code="quality_threshold_not_met",
        )
        self.detail = detail


class RetrievalError(PipelineError):
    def __init__(self, detail: str):
        super().__init__(
            detail,
            user_message=(
                "Scripture retrieval failed and could not complete. "
                f"Details: {detail}. Verify Milvus and the MCP retrieval server, then try again."
            ),
            code="retrieval_failed",
        )
