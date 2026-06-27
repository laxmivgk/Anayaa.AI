from app.config import Settings
from app.llm.router import select_model


def test_local_latency_defaults_disable_heavy_optional_components():
    settings = Settings(JWT_SECRET="x" * 32)

    assert settings.llmlingua_enabled is False
    assert settings.cross_encoder_enabled is False


def test_local_model_routes_match_edge_latency_profile():
    assert select_model("classifier") == "gemma2:2b"
    assert select_model("planner") == "qwen3:4b"
    assert select_model("synthesizer") == "llama3.2:3b"
    assert select_model("judge") == "qwen3:4b"
