"""Phase 0 production security hardening unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from payroll_copilot.infrastructure.config.production_guards import (
    is_local_dev_env,
    is_production_env,
    validate_production_settings,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.routes.integrations import _require_n8n_api_key
from payroll_copilot.presentation.api.security import require_guest


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
        "cors_origins_list": ["https://app.example.com"],
        "s3_endpoint": "",
        "s3_server_side_encryption": "AES256",
        "dynamodb_endpoint": "",
        "redis_url": "redis://elasticache.example:6379/0",
        "celery_broker_url": "redis://elasticache.example:6379/1",
        "celery_result_backend": "redis://elasticache.example:6379/2",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_is_production_env_detects_prod_aliases() -> None:
    assert is_production_env(_settings(app_env="production"))
    assert is_production_env(_settings(app_env="PROD"))
    assert not is_production_env(_settings(app_env="development"))
    assert is_local_dev_env(_settings(app_env="local"))


def test_validate_production_settings_skips_non_production() -> None:
    validate_production_settings(_settings(app_env="development", debug=True))


def test_validate_production_settings_rejects_debug() -> None:
    with pytest.raises(RuntimeError, match="DEBUG must be false"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=True,
                service_auto_fallback=False,
                cognito_user_pool_id="pool",
                cognito_app_client_id="client",
            )
        )


def test_validate_production_settings_rejects_missing_cognito() -> None:
    with pytest.raises(RuntimeError, match="Cognito"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=False,
                service_auto_fallback=False,
                cognito_user_pool_id="",
                cognito_app_client_id="",
            )
        )


def test_validate_production_settings_rejects_placeholder_secrets() -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=False,
                service_auto_fallback=False,
                cognito_user_pool_id="pool",
                cognito_app_client_id="client",
                secret_key="change-me-please-this-is-long-enough-32",
            )
        )


def test_validate_production_settings_rejects_auto_fallback() -> None:
    with pytest.raises(RuntimeError, match="SERVICE_AUTO_FALLBACK"):
        validate_production_settings(
            _settings(
                app_env="production",
                debug=False,
                service_auto_fallback=True,
                cognito_user_pool_id="pool",
                cognito_app_client_id="client",
            )
        )


def test_validate_production_settings_accepts_safe_production() -> None:
    validate_production_settings(
        _settings(
            app_env="production",
            debug=False,
            service_auto_fallback=False,
            cognito_user_pool_id="eu-west-1_abc",
            cognito_app_client_id="clientid",
        )
    )


def test_n8n_api_key_fail_closed_when_empty() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_n8n_api_key("anything", "")
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "n8n_not_configured"


def test_n8n_api_key_rejects_mismatch() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_n8n_api_key("wrong-key", "expected-key")
    assert exc.value.status_code == 401


def test_n8n_api_key_accepts_match() -> None:
    _require_n8n_api_key("expected-key", "expected-key")


@pytest.mark.asyncio
async def test_require_guest_rejects_missing_authorization() -> None:
    with pytest.raises(HTTPException) as exc:
        await require_guest(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_guest_rejects_non_guest_token() -> None:
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "iat": datetime.now(UTC),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as exc:
        await require_guest(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "guest_token_required"


@pytest.mark.asyncio
async def test_require_guest_accepts_guest_token() -> None:
    settings = get_settings()
    guest_id = str(uuid4())
    token = jwt.encode(
        {
            "sub": guest_id,
            "type": "guest",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "iat": datetime.now(UTC),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    principal = await require_guest(authorization=f"Bearer {token}")
    assert principal.guest_id == guest_id
