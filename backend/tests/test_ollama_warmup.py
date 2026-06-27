from app.llm import generator


def test_active_ollama_warmup_models_are_unique_and_skip_gemini(monkeypatch):
    routes = {
        "planner": "qwen3:4b",
        "synthesizer": "llama3.2:3b",
        "judge": "qwen3:4b",
    }
    monkeypatch.setattr(generator, "select_model", lambda task: routes[task])

    assert generator._active_ollama_warmup_models() == ["qwen3:4b", "llama3.2:3b"]

    routes["planner"] = "gemini-flash"

    assert generator._active_ollama_warmup_models() == ["llama3.2:3b", "qwen3:4b"]
