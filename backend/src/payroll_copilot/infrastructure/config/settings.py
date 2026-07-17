"""Application settings from environment variables.

Configuration precedence:

1. Process environment variables (always win) — Compose ``env_file`` and production orchestrators.
2. Optional dotenv files, first match wins:
   ``../.env.local`` → ``../.env`` → ``.env.local`` → ``.env``

Templates:
- ``.env.production.example`` / ``.env.example`` — AWS defaults (S3, DynamoDB, Cognito, SES, Bedrock, CloudWatch)
- ``.env.docker.example`` / ``.env.local.example`` — local development substitutes

Runtime persistence is DynamoDB. ``DATABASE_URL`` is optional (legacy Alembic/SQLAlchemy only).
"""

from functools import lru_cache
from typing import Any

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env.local", "../.env", ".env.local", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Payroll Copilot"
    app_env: str = "production"
    debug: bool = False
    secret_key: str = Field(min_length=32)
    default_locale: str = "he"
    api_prefix: str = "/api/v1"

    # Shared AWS region (adapters may override per service).
    aws_region: str = "us-east-1"

    # Legacy PostgreSQL — optional; runtime uses DynamoDB.
    database_url: PostgresDsn | None = None
    database_pool_size: int = 10
    database_max_overflow: int = 20

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_database_url_as_none(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    redis_url: str = "redis://localhost:6379/0"
    redis_local_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = ""
    s3_local_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "payroll-copilot"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = True
    # Auto-create is honored only for custom endpoints (MinIO). Always false for Amazon S3.
    s3_auto_create_bucket: bool = False

    # Local-vs-Docker service resolution. When auto-fallback is enabled and the
    # configured host is unreachable (e.g. Docker hostname `redis`/`minio` while the
    # backend runs locally), the resolver probes the *_LOCAL_URL fallback instead.
    service_auto_fallback: bool = True
    service_probe_timeout_seconds: float = 0.5

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Amazon Cognito (primary authentication for authenticated users)
    cognito_region: str = "us-east-1"
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    cognito_app_client_secret: str = ""

    # Amazon DynamoDB (primary business database — single-table design)
    # Empty DYNAMODB_ENDPOINT → Amazon DynamoDB in DYNAMODB_REGION (default credentials).
    # Non-empty endpoint → DynamoDB Local / compatible (auto-create table when enabled).
    dynamodb_table_name: str = "PayrollCopilot"
    dynamodb_region: str = "us-east-1"
    dynamodb_endpoint: str = ""
    dynamodb_local_endpoint: str = "http://localhost:8001"
    dynamodb_auto_create_table: bool = False

    # Amazon SES (outbound email). Leave SES_FROM_EMAIL empty for local console logging.
    ses_region: str = "us-east-1"
    ses_from_email: str = ""
    ses_from_name: str = "Payroll Copilot"
    ses_configuration_set: str = ""
    ses_endpoint: str = ""  # optional LocalStack / custom SES endpoint

    encryption_key: str = Field(min_length=64)

    guest_session_ttl_hours: int = 24

    guest_validation_confidence_penalty_attendance: float = 0.12
    guest_validation_confidence_penalty_contract: float = 0.12
    guest_validation_confidence_penalty_national_id: float = 0.08
    guest_validation_confidence_penalty_historical: float = 0.08
    guest_validation_confidence_penalty_extraction: float = 0.20
    guest_validation_confidence_minimum: float = 0.35

    model_provider: str = "bedrock"
    ollama_base_url: str = ""
    ollama_local_url: str = "http://127.0.0.1:11434"
    ollama_host_url: str = "http://host.docker.internal:11434"
    ollama_docker_url: str = "http://ollama:11434"
    ollama_auto_fallback: bool = True
    ollama_probe_timeout_seconds: float = 2.0
    ollama_default_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    # Amazon Bedrock (primary LLM when MODEL_PROVIDER=bedrock)
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    bedrock_embedding_dimensions: int = 1024
    bedrock_endpoint: str = ""  # optional LocalStack / custom endpoint

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Phase 2A AI payslip parser (Ollama). Does not change other Ollama consumers.
    payslip_parser_model: str = ""
    payslip_parser_timeout_seconds: float = 180.0
    payslip_parser_total_budget_seconds: float = 240.0
    payslip_parser_max_predict: int = 8192
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
    ocr_tesseract_multi_psm_enabled: bool = False
    ocr_tesseract_psm_candidates: str = "3,6"
    ocr_tesseract_primary_psm: int = 3
    ocr_tesseract_fallback_psm: int = 6
    ocr_tesseract_default_oem: int = 3
    ocr_tesseract_max_candidates: int = 2
    ocr_tesseract_min_valid_word_confidence: float = 0.0
    ocr_tesseract_min_usable_text_chars: int = 20
    ocr_tesseract_max_pages: int = 20

    guest_ephemeral_ttl_hours: float = 1.0

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

    # CloudWatch — app emits JSON to stdout; platform ships to CloudWatch Logs.
    cloudwatch_enabled: bool = True
    cloudwatch_log_group: str = "/payroll-copilot/api"
    cloudwatch_metrics_namespace: str = "PayrollCopilot"

    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url_str(self) -> str:
        if self.database_url is None:
            raise RuntimeError(
                "DATABASE_URL is not set. Runtime persistence uses DynamoDB; "
                "provide DATABASE_URL only for legacy Alembic/SQLAlchemy tooling."
            )
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
