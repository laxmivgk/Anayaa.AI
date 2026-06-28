"""Local-first LLM routing: Ollama default, Gemini optional."""
from app.config import get_settings


def select_model(task: str) -> str:
    settings = get_settings()
    if settings.gemini_api_key and task in {"synthesizer", "planner"}:
        return "gemini-flash"
    routing = {
        "classifier": "gemma2:2b",
        "optimizer": "qwen3:4b",
        "planner": "qwen3:4b",
        "optimizer": "qwen3:4b",
        "planner": "qwen3:4b",
        "synthesizer": "llama3.2:3b",
        "judge": "qwen3:4b",
    }
    return routing.get(task, "qwen3:4b")
        "synthesizer": "llama3.2:3b",
        "judge": "qwen3:4b",
    }
    return routing.get(task, "qwen3:4b")
