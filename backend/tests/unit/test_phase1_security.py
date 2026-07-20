"""Phase 1 production security controls unit tests."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from payroll_copilot.infrastructure.config.production_guards import validate_production_settings
from payroll_copilot.infrastructure.security.rate_limiter import RateLimiter, reset_rate_limiter_for_tests
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage
from payroll_copilot.presentation.api.upload_limits import read_upload_with_size_limit


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "app_env": "development",
        "debug": True,
        "secret_key": "safe-secret-key-not-a-placeholder-value-32",
        "jwt_secret_key": "safe-jwt-secret-key-not-a-placeholder-32",
        "encryption_key": "a" * 64,
        "service_auto_fallback": True,
        "cognito_user_pool_id": "",
        "cognito_app_client_id": "",
        "cors_origins_list": ["http://localhost:3000"],
        "s3_endpoint": "http://localhost:9000",
        "s3_server_side_encryption": "AES256",
        "dynamodb_endpoint": "http://localhost:8001",
        "redis_url": "redis://localhost:6379/0",
        "celery_broker_url": "redis://localhost:6379/1",
        "celery_result_backend": "redis://localhost:6379/2",
        "rate_limit_enabled": False,
        "rate_limit_enforced": False,
    }
    base.update(overrides)
    if "rate_limit_enforced" not in overrides and overrides.get("rate_limit_enabled") is True:
        base["rate_limit_enforced"] = True
    if overrides.get("rate_limit_enabled") is False:
        base["rate_limit_enforced"] = False
    return SimpleNamespace(**base)


def test_rate_limiter_disabled_in_development() -> None:
    reset_rate_limiter_for_tests()
    limiter = RateLimiter(_settings(app_env="development", rate_limit_enabled=False))
    limiter.enforce("auth", "127.0.0.1", 1, 60)
    limiter.enforce("auth", "127.0.0.1", 1, 60)


def test_rate_limiter_enforces_when_enabled() -> None:
    reset_rate_limiter_for_tests()
    limiter = RateLimiter(_settings(rate_limit_enforced=True))
    limiter.enforce("auth", "test-ip", 2, 60)
    limiter.enforce("auth", "test-ip", 2, 60)
    with pytest.raises(HTTPException) as exc:
        limiter.enforce("auth", "test-ip", 2, 60)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_read_upload_rejects_oversize_before_full_read() -> None:
    upload = UploadFile(filename="big.pdf", file=BytesIO(b"x" * 10))
    upload.read = AsyncMock(side_effect=[b"a" * 5, b"b" * 5, b""])  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc:
        await read_upload_with_size_limit(upload, max_size_bytes=8, chunk_size=5)
    assert exc.value.status_code == 413
    assert upload.read.await_count == 2


def test_s3_upload_sets_server_side_encryption() -> None:
    client = MagicMock()
    storage = S3ObjectStorage.__new__(S3ObjectStorage)
    storage._bucket = "test-bucket"  # noqa: SLF001
    storage._server_side_encryption = "AES256"  # noqa: SLF001
    storage._client = client  # noqa: SLF001

    import asyncio

    asyncio.run(storage.upload("key", b"data", "application/pdf"))

    _, kwargs = client.upload_fileobj.call_args
    assert kwargs["ExtraArgs"]["ServerSideEncryption"] == "AES256"
    assert kwargs["ExtraArgs"]["ContentType"] == "application/pdf"


def test_validate_production_rejects_localhost_cors() -> None:
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=False,
                service_auto_fallback=False,
                cognito_user_pool_id="pool",
                cognito_app_client_id="client",
                cors_origins_list=["http://localhost:3000"],
                s3_endpoint="",
                dynamodb_endpoint="",
                redis_url="redis://elasticache.example:6379/0",
                celery_broker_url="redis://elasticache.example:6379/1",
                celery_result_backend="redis://elasticache.example:6379/2",
            )
        )


def test_validate_production_rejects_local_s3_endpoint() -> None:
    with pytest.raises(RuntimeError, match="S3_ENDPOINT"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=False,
                service_auto_fallback=False,
                cognito_user_pool_id="pool",
                cognito_app_client_id="client",
                cors_origins_list=["https://app.example.com"],
                s3_endpoint="http://minio:9000",
                dynamodb_endpoint="",
                redis_url="redis://elasticache.example:6379/0",
                celery_broker_url="redis://elasticache.example:6379/1",
                celery_result_backend="redis://elasticache.example:6379/2",
            )
        )


def test_validate_production_rejects_localhost_redis() -> None:
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=False,
                service_auto_fallback=False,
                cognito_user_pool_id="pool",
                cognito_app_client_id="client",
                cors_origins_list=["https://app.example.com"],
                s3_endpoint="",
                dynamodb_endpoint="",
            )
        )
