from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    jwt_exp_minutes: int = 15
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "anayaa"
    postgres_user: str = "anayaa"
    postgres_password: str = "anayaa_dev"
    redis_url: str = "redis://127.0.0.1:6379/0"
    postgres_enabled: bool = True
    milvus_enabled: bool = True
    # ANAYAA_MILVUS_URI avoids clashing with pymilvus's global MILVUS_URI env (which expects http://)
    milvus_uri: str = Field(default="data/milvus.db", validation_alias="ANAYAA_MILVUS_URI")
    milvus_collection: str = "scripture_verses"
    offline_mode: bool = True
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_backend: str = "onnx"
    embedding_onnx_dir: str = "data/onnx_embeddings"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    cross_encoder_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    gemini_api_key: str = ""
    hitl_enabled: bool = True
    rate_limit_per_minute: int = 20
    session_refresh_rate_limit_per_minute: int = 10
    pii_ner_enabled: bool = True
    pii_ner_model: str = ""
    pii_ner_local_files_only: bool = True
    pii_ner_fallback_enabled: bool = True
    scriptures_json_path: str = "data/scriptures.json"
    llmlingua_enabled: bool = False
    llmlingua_model: str = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
    llmlingua_use_v2: bool = True
    llmlingua_use_longllmlingua: bool = False
    llmlingua_device: str = "auto"
    llmlingua_compression_rate: float = 0.5
    adk_enabled: bool = True
    retrieval_confidence_threshold: float = 40.0
    retrieval_semantic_similarity_threshold: float = 0.17
    audit_min_score: int = 3
    react_loop_enabled: bool = True
    react_max_turns: int = 2
    audit_logs_retention_days: int = 90
    request_eco_metrics_retention_days: int = 90
    agent_traces_retention_days: int = 30
    hitl_terminal_retention_days: int = 7
    turns_retention_days: int = 30
    retention_cleanup_interval_seconds: int = 86400
    password_reset_base_url: str = "http://127.0.0.1:8000"

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        unsafe_values = {
            "",
            "change-me",
            "change-me-generate-with-start-backend",
        }
        if value in unsafe_values or value.startswith("anayaa-edge-secret-key-") or len(value) < 32:
            raise ValueError("JWT_SECRET must be set to a unique secret with at least 32 characters.")
        return value

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
