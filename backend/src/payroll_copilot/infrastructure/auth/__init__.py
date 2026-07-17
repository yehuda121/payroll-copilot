"""Authentication infrastructure (Amazon Cognito)."""

from payroll_copilot.infrastructure.auth.cognito import (
    CognitoAuthClient,
    CognitoAuthenticationError,
    CognitoConfigurationError,
    CognitoTokenVerifier,
    api_role_from_domain,
    cognito_configured,
    get_cognito_auth_client,
    get_cognito_token_verifier,
    role_from_cognito_claims,
)

__all__ = [
    "CognitoAuthClient",
    "CognitoAuthenticationError",
    "CognitoConfigurationError",
    "CognitoTokenVerifier",
    "api_role_from_domain",
    "cognito_configured",
    "get_cognito_auth_client",
    "get_cognito_token_verifier",
    "role_from_cognito_claims",
]
