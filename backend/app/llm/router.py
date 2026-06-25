"""Local-first LLM routing: Ollama default, Gemini optional."""
from app.config import get_settings


def select_model(task: str) -> str:
    settings = get_settings()
    if settings.gemini_api_key and task in {"synthesizer", "planner"}:
        return "gemini-flash"
    routing = {
        "classifier": "gemma2:2b",
        "optimizer": "llama3.2:3b",
        "planner": "gemma2:2b",
        "synthesizer": "llama3.2:3b",
        "judge": "llama3.2:3b",
    }
    return routing.get(task, "llama3.2:3b")
