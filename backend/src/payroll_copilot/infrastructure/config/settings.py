"""Application settings from environment variables.

Configuration precedence (explicit, no host-name magic for Postgres):

1. Process environment variables (always win) — used by Docker Compose ``env_file: .env``
2. Optional dotenv files, first match wins among the list below — for host-local uvicorn only:
   ``../.env.local`` → ``../.env`` → ``.env.local`` → ``.env``

Docker development: copy ``.env.docker.example`` → ``.env`` (Compose injects it).
Host development: copy ``.env.local.example`` → ``.env.local`` (backend loads it from repo root).
Future production: inject secrets via the orchestrator; do not rely on committed dotenv files.

``DATABASE_URL`` is the single source of truth for FastAPI and Alembic.
"""

from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env.local", "../.env", ".env.local", ".env"),
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
    redis_local_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_local_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "payroll-copilot"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    # Local-vs-Docker service resolution. When auto-fallback is enabled and the
    # configured host is unreachable (e.g. Docker hostname `redis`/`minio` while the
    # backend runs locally), the resolver probes the *_LOCAL_URL fallback instead.
    service_auto_fallback: bool = True
    service_probe_timeout_seconds: float = 0.5

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    encryption_key: str = Field(min_length=64)

    guest_session_ttl_hours: int = 24

    guest_validation_confidence_penalty_attendance: float = 0.12
    guest_validation_confidence_penalty_contract: float = 0.12
    guest_validation_confidence_penalty_national_id: float = 0.08
    guest_validation_confidence_penalty_historical: float = 0.08
    guest_validation_confidence_penalty_extraction: float = 0.20
    guest_validation_confidence_minimum: float = 0.35

    model_provider: str = "ollama"
    ollama_base_url: str = ""
    ollama_local_url: str = "http://127.0.0.1:11434"
    ollama_host_url: str = "http://host.docker.internal:11434"
    ollama_docker_url: str = "http://ollama:11434"
    ollama_auto_fallback: bool = True
    ollama_probe_timeout_seconds: float = 2.0
    ollama_default_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Phase 2A AI payslip parser (Ollama). Does not change other Ollama consumers.
    payslip_parser_model: str = ""
    payslip_parser_timeout_seconds: float = 180.0
    payslip_parser_temperature: float = 0.0
    payslip_parser_use_json_format: bool = True
    payslip_parser_layout_enabled: bool = True
    payslip_parser_include_words: bool = True
    payslip_parser_max_lines: int = 300
    payslip_parser_max_words: int = 2000
    payslip_parser_min_word_confidence: float = 0.0
    payslip_parser_max_context_chars: int = 50_000

    # OCR: paddleocr is primary (en/ar). Hebrew uses transparent Tesseract fallback (H1).
    ocr_provider: str = "paddleocr"
    tesseract_lang: str = "heb+eng"
    ocr_timeout_seconds: float = 120.0
    ocr_use_gpu: bool = False
    # Tesseract-only image preprocessing (does not change language/provider/PSM).
    ocr_preprocessing_enabled: bool = True
    ocr_preprocessing_target_long_edge: int = 2000
    ocr_preprocessing_max_scale_factor: float = 3.0
    ocr_preprocessing_max_pixels: int = 20_000_000
    ocr_preprocessing_contrast_factor: float = 1.4
    ocr_preprocessing_sharpness_factor: float = 1.3
    # Tesseract multi-PSM layout strategy (does not change language mapping).
    ocr_tesseract_multi_psm_enabled: bool = True
    ocr_tesseract_psm_candidates: str = "3,4,6,11"
    ocr_tesseract_default_oem: int = 3
    ocr_tesseract_max_candidates: int = 4
    ocr_tesseract_min_valid_word_confidence: float = 0.0

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_broker_local_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_result_backend_local_url: str = "redis://localhost:6379/2"

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
