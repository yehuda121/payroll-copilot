"""Amazon Cognito authentication adapter.

Verifies Cognito JWTs via JWKS and performs USER_PASSWORD_AUTH login/refresh
against Cognito User Pools. Authorization (role/org/employee binding) remains
in the application layer after identity is established.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
import httpx
from botocore.exceptions import ClientError
from jose import JWTError, jwk, jwt

from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_COGNITO_GROUP_TO_ROLE: dict[str, str] = {
    "employee": UserRole.EMPLOYEE.value,
    "payroll_accountant": UserRole.ACCOUNTANT.value,
    "accountant": UserRole.ACCOUNTANT.value,
    "developer_admin": UserRole.ADMIN.value,
    "admin": UserRole.ADMIN.value,
}

# Frontend / TokenResponse role aliases (UI routes use longer names).
_API_ROLE_ALIASES: dict[str, str] = {
    UserRole.ACCOUNTANT.value: "payroll_accountant",
    UserRole.ADMIN.value: "developer_admin",
}


def api_role_from_domain(role: str) -> str:
    """Map domain role values to the TokenResponse / SPA role strings."""
    return _API_ROLE_ALIASES.get(role, role)


@dataclass(frozen=True, slots=True)
class CognitoAuthResult:
    access_token: str
    id_token: str | None
    refresh_token: str | None
    expires_in: int
    token_type: str
    claims: dict[str, Any]


class CognitoConfigurationError(Exception):
    """Cognito is required but not configured."""


class CognitoAuthenticationError(Exception):
    """Invalid credentials or Cognito rejected the auth request."""


def cognito_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool((s.cognito_user_pool_id or "").strip() and (s.cognito_app_client_id or "").strip())


def role_from_cognito_claims(claims: dict[str, Any]) -> str | None:
    """Map Cognito groups / custom attributes to an application role."""
    custom_role = claims.get("custom:role") or claims.get("role")
    if isinstance(custom_role, str) and custom_role.strip():
        normalized = custom_role.strip().lower()
        if normalized in {r.value for r in UserRole}:
            return normalized
        mapped = _COGNITO_GROUP_TO_ROLE.get(normalized)
        if mapped:
            return mapped

    groups = claims.get("cognito:groups") or claims.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    for group in groups:
        mapped = _COGNITO_GROUP_TO_ROLE.get(str(group).strip().lower())
        if mapped:
            return mapped
    return None


class CognitoTokenVerifier:
    """Validate Cognito access or ID tokens using the user-pool JWKS."""

    def __init__(self, settings: Settings) -> None:
        if not cognito_configured(settings):
            raise CognitoConfigurationError(
                "Cognito is not configured. Set COGNITO_USER_POOL_ID, "
                "COGNITO_APP_CLIENT_ID, and COGNITO_REGION."
            )
        self._settings = settings
        self._region = settings.cognito_region.strip()
        self._pool_id = settings.cognito_user_pool_id.strip()
        self._client_id = settings.cognito_app_client_id.strip()
        self._issuer = f"https://cognito-idp.{self._region}.amazonaws.com/{self._pool_id}"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at = 0.0
        self._jwks_ttl_seconds = 3600.0

    def _load_jwks(self, *, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if (
            not force
            and self._jwks is not None
            and (now - self._jwks_fetched_at) < self._jwks_ttl_seconds
        ):
            return self._jwks
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._jwks_url)
            response.raise_for_status()
            self._jwks = response.json()
            self._jwks_fetched_at = now
            return self._jwks

    def _jwk_for_kid(self, kid: str) -> Any:
        jwks = self._load_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwk.construct(key)
        jwks = self._load_jwks(force=True)
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwk.construct(key)
        raise JWTError(f"Unable to find Cognito JWK for kid={kid}")

    def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                raise JWTError("Token header missing kid")
            key = self._jwk_for_kid(str(kid))
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "verify_aud": False,  # access tokens use client_id, not aud
                    "verify_at_hash": False,
                },
            )
        except JWTError:
            raise
        except Exception as exc:
            raise JWTError(f"Cognito token verification failed: {exc}") from exc

        token_use = str(claims.get("token_use") or "")
        if token_use == "id":
            aud = claims.get("aud")
            if aud != self._client_id:
                raise JWTError("ID token audience does not match app client id")
        elif token_use == "access":
            client_id = claims.get("client_id")
            if client_id != self._client_id:
                raise JWTError("Access token client_id does not match app client id")
        else:
            raise JWTError(f"Unsupported Cognito token_use: {token_use or 'missing'}")

        if not claims.get("sub"):
            raise JWTError("Token missing sub")
        return claims


class CognitoAuthClient:
    """Cognito Identity Provider operations used by /auth/login and /auth/refresh."""

    def __init__(self, settings: Settings) -> None:
        if not cognito_configured(settings):
            raise CognitoConfigurationError(
                "Cognito is not configured. Set COGNITO_USER_POOL_ID, "
                "COGNITO_APP_CLIENT_ID, and COGNITO_REGION."
            )
        self._settings = settings
        self._client_id = settings.cognito_app_client_id.strip()
        self._client_secret = (settings.cognito_app_client_secret or "").strip()
        self._idp = boto3.client("cognito-idp", region_name=settings.cognito_region.strip())
        self._verifier = CognitoTokenVerifier(settings)

    def _secret_hash(self, username: str) -> str | None:
        if not self._client_secret:
            return None
        digest = hmac.new(
            self._client_secret.encode("utf-8"),
            f"{username}{self._client_id}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _auth_parameters(self, username: str, password: str | None = None) -> dict[str, str]:
        params: dict[str, str] = {"USERNAME": username}
        if password is not None:
            params["PASSWORD"] = password
        secret_hash = self._secret_hash(username)
        if secret_hash:
            params["SECRET_HASH"] = secret_hash
        return params

    def _result_from_authentication(self, auth_result: dict[str, Any]) -> CognitoAuthResult:
        access_token = str(auth_result["AccessToken"])
        id_token = auth_result.get("IdToken")
        refresh_token = auth_result.get("RefreshToken")
        expires_in = int(auth_result.get("ExpiresIn") or 3600)
        # Prefer ID token claims for profile; fall back to access token.
        claims: dict[str, Any]
        if id_token:
            claims = self._verifier.verify(str(id_token))
        else:
            claims = self._verifier.verify(access_token)
        return CognitoAuthResult(
            access_token=access_token,
            id_token=str(id_token) if id_token else None,
            refresh_token=str(refresh_token) if refresh_token else None,
            expires_in=expires_in,
            token_type=str(auth_result.get("TokenType") or "Bearer"),
            claims=claims,
        )

    def login(self, *, email: str, password: str) -> CognitoAuthResult:
        username = email.strip()
        try:
            response = self._idp.initiate_auth(
                ClientId=self._client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters=self._auth_parameters(username, password),
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            logger.info("Cognito login failed: %s", code)
            raise CognitoAuthenticationError("Invalid credentials") from exc

        if response.get("ChallengeName"):
            raise CognitoAuthenticationError(
                f"Additional authentication challenge required: {response['ChallengeName']}"
            )
        auth_result = response.get("AuthenticationResult")
        if not auth_result:
            raise CognitoAuthenticationError("Cognito did not return tokens")
        return self._result_from_authentication(auth_result)

    def refresh(self, *, refresh_token: str, username: str | None = None) -> CognitoAuthResult:
        params: dict[str, str] = {"REFRESH_TOKEN": refresh_token}
        # SECRET_HASH for refresh requires username when the client has a secret.
        if self._client_secret:
            if not username:
                raise CognitoAuthenticationError(
                    "username is required to refresh tokens for a confidential app client"
                )
            secret_hash = self._secret_hash(username)
            if secret_hash:
                params["SECRET_HASH"] = secret_hash
        try:
            response = self._idp.initiate_auth(
                ClientId=self._client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters=params,
            )
        except ClientError as exc:
            raise CognitoAuthenticationError("Invalid or expired refresh token") from exc

        auth_result = response.get("AuthenticationResult")
        if not auth_result:
            raise CognitoAuthenticationError("Cognito did not return tokens")
        # Refresh responses often omit RefreshToken — preserve caller token.
        if "RefreshToken" not in auth_result:
            auth_result = {**auth_result, "RefreshToken": refresh_token}
        return self._result_from_authentication(auth_result)


@lru_cache
def get_cognito_token_verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier(get_settings())


@lru_cache
def get_cognito_auth_client() -> CognitoAuthClient:
    return CognitoAuthClient(get_settings())
