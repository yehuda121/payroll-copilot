"""Fail-fast production configuration checks.

Local/dev environments are intentionally untouched. Production (`app_env` of
`production` / `prod`) refuses unsafe or incomplete settings at startup.
"""

from __future__ import annotations

from urllib.parse import urlparse

from payroll_copilot.infrastructure.auth.cognito import cognito_configured
from payroll_copilot.infrastructure.config.settings import Settings

_PLACEHOLDER_SECRET_FRAGMENTS = (
    "change-me",
    "changeme",
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_production_env(settings: Settings) -> bool:
    return settings.app_env.strip().lower() in {"production", "prod"}


def is_local_dev_env(settings: Settings) -> bool:
    return settings.app_env.strip().lower() in {"development", "dev", "local"}


def _url_host(url: str) -> str:
    return (urlparse(url.strip()).hostname or "").lower()


def _url_points_to_localhost(url: str) -> bool:
    host = _url_host(url)
    return host in _LOCAL_HOSTS


def _origin_is_localhost(origin: str) -> bool:
    parsed = urlparse(origin.strip())
    host = (parsed.hostname or "").lower()
    return host in _LOCAL_HOSTS


def validate_production_settings(settings: Settings) -> None:
    """Raise ``RuntimeError`` when production configuration is unsafe."""
    if not is_production_env(settings):
        return

    errors: list[str] = []

    if settings.debug:
        errors.append("DEBUG must be false when APP_ENV is production.")

    if not cognito_configured(settings):
        errors.append(
            "Amazon Cognito must be configured in production "
            "(COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID)."
        )

    for name, value in (
        ("SECRET_KEY", settings.secret_key),
        ("JWT_SECRET_KEY", settings.jwt_secret_key),
        ("ENCRYPTION_KEY", settings.encryption_key),
    ):
        lowered = value.strip().lower()
        if any(fragment in lowered for fragment in _PLACEHOLDER_SECRET_FRAGMENTS):
            errors.append(f"{name} appears to be a placeholder value; refuse to start.")

    if settings.service_auto_fallback:
        errors.append(
            "SERVICE_AUTO_FALLBACK must be false in production "
            "(refuses silent localhost service fallback)."
        )

    if not settings.cors_origins_list:
        errors.append("CORS_ORIGINS must list at least one explicit production origin.")
    else:
        for origin in settings.cors_origins_list:
            lowered = origin.lower()
            if lowered == "*":
                errors.append("CORS_ORIGINS must not use wildcard '*' in production.")
            elif _origin_is_localhost(origin):
                errors.append(
                    f"CORS_ORIGINS must not include localhost origin in production ({origin})."
                )

    if (settings.s3_endpoint or "").strip():
        errors.append(
            "S3_ENDPOINT must be empty in production (use Amazon S3, not MinIO/local)."
        )

    if not (settings.s3_server_side_encryption or "").strip():
        errors.append(
            "S3_SERVER_SIDE_ENCRYPTION must be set in production (e.g. AES256)."
        )

    if (settings.dynamodb_endpoint or "").strip():
        errors.append(
            "DYNAMODB_ENDPOINT must be empty in production (use Amazon DynamoDB)."
        )

    for name, url in (
        ("REDIS_URL", settings.redis_url),
        ("CELERY_BROKER_URL", settings.celery_broker_url),
        ("CELERY_RESULT_BACKEND", settings.celery_result_backend),
    ):
        if _url_points_to_localhost(url):
            errors.append(
                f"{name} must not point to localhost in production "
                "(use ElastiCache / managed Redis)."
            )

    if errors:
        joined = " ".join(errors)
        raise RuntimeError(f"Production configuration invalid: {joined}")
