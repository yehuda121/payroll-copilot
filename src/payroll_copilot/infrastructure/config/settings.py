"""Application settings from environment variables."""

from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Payroll Copilot"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = Field(min_length=32)
    default_locale: str = "he"
    api_prefix: str = "/api/v1"

    database_url: PostgresDsn
    database_pool_size: int = 10
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "payroll-copilot"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    encryption_key: str = Field(min_length=64)

    guest_session_ttl_hours: int = 24

    model_provider: str = "ollama"
    ollama_base_url: str = ""
    ollama_host_url: str = "http://host.docker.internal:11434"
    ollama_docker_url: str = "http://ollama:11434"
    ollama_auto_fallback: bool = True
    ollama_probe_timeout_seconds: float = 2.0
    ollama_default_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    ocr_provider: str = "tesseract"
    tesseract_lang: str = "heb+eng+ara"

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    max_upload_size_mb: int = 50
    max_bulk_pdf_size_mb: int = 200

    rules_config_path: str = "config/rules"
    legal_rules_path: str = "config/rules/labor_law"
    department_rules_path: str = "config/rules/departments"

    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_top_k: int = 5
    rag_min_confidence: float = 0.7

    mcp_enabled: bool = True
    kol_zchut_base_url: str = "https://www.kolzchut.org.il"

    n8n_api_key: str = ""

    log_level: str = "INFO"
    log_format: str = "json"

    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
