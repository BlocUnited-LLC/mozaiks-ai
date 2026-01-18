"""
Tests for core.auth module.

Run with: pytest tests/test_auth.py -v
"""

import pytest
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


# Generate test RSA keys
def generate_test_keys():
    """Generate RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()
    return private_key, public_key


# Test fixtures
TEST_PRIVATE_KEY, TEST_PUBLIC_KEY = generate_test_keys()

TEST_KID = "test-key-id-001"
TEST_ISSUER = "https://test-tenant.ciamlogin.com/test-tenant/v2.0"
TEST_AUDIENCE = "api://test-app"
TEST_USER_ID = "user-123-abc"
TEST_EMAIL = "test@example.com"


def create_test_token(
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    scopes: str = "access_as_user",
    roles: list = None,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    exp_offset: int = 3600,
    nbf_offset: int = 0,
    kid: str = TEST_KID,
) -> str:
    """Create a signed test JWT."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "scp": scopes,
        "roles": roles or [],
        "iss": issuer,
        "aud": audience,
        "exp": now + exp_offset,
        "nbf": now + nbf_offset,
        "iat": now,
    }
    headers = {"kid": kid, "alg": "RS256"}
    return jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256", headers=headers)


def get_test_jwk() -> dict:
    """Get JWK representation of test public key."""
    from jwt import algorithms
    jwk = algorithms.RSAAlgorithm.to_jwk(TEST_PUBLIC_KEY, as_dict=True)
    jwk["kid"] = TEST_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return jwk


# ============================================================
# Config Tests
# ============================================================

class TestAuthConfig:
    """Tests for auth configuration."""

    def test_default_config(self, monkeypatch):
        """Test default Mozaiks CIAM config."""
        from mozaiksai.core.auth.config import get_auth_config, clear_auth_config_cache

        # Clear any cached config
        clear_auth_config_cache()

        # Clear env vars to use defaults
        for var in ["AUTH_ENABLED", "AUTH_ISSUER", "AUTH_JWKS_URL", "AUTH_AUDIENCE",
                    "MOZAIKS_OIDC_AUTHORITY", "MOZAIKS_OIDC_TENANT_ID"]:
            monkeypatch.delenv(var, raising=False)

        config = get_auth_config()
        assert config.enabled is True
        assert "mozaiks.ciamlogin.com" in config.oidc_authority
        assert config.oidc_tenant_id == "9d0073d5-42e8-46f0-a325-5b4be7b1a38d"
        assert config.audience == "api://mozaiks-auth"
        assert config.required_scope == "access_as_user"
        # By default, no overrides set - should use discovery
        assert config.use_discovery is True

        clear_auth_config_cache()

    def test_custom_config(self, monkeypatch):
        """Test custom config from env vars."""
        from mozaiksai.core.auth.config import get_auth_config, clear_auth_config_cache

        clear_auth_config_cache()

        monkeypatch.setenv("AUTH_ENABLED", "false")
        monkeypatch.setenv("AUTH_ISSUER", "https://custom-issuer.com")
        monkeypatch.setenv("AUTH_JWKS_URL", "https://custom-jwks.com/keys")
        monkeypatch.setenv("AUTH_AUDIENCE", "custom-audience")
        monkeypatch.setenv("AUTH_REQUIRED_SCOPE", "custom_scope")
        monkeypatch.setenv("AUTH_USER_ID_CLAIM", "oid")

        config = get_auth_config()
        assert config.enabled is False
        assert config.issuer_override == "https://custom-issuer.com"
        assert config.jwks_url_override == "https://custom-jwks.com/keys"
        assert config.audience == "custom-audience"
        assert config.required_scope == "custom_scope"
        assert config.user_id_claim == "oid"
        # Both overrides set - should skip discovery
        assert config.use_discovery is False

        clear_auth_config_cache()


# ============================================================
# JWT Validator Tests
# ============================================================

class TestJWTValidator:
    """Tests for JWT validation."""

    @pytest.fixture(autouse=True)
    def setup_config(self, monkeypatch):
        """Setup test config with explicit overrides (skip discovery)."""
        from mozaiksai.core.auth.config import clear_auth_config_cache
        from mozaiksai.core.auth.jwt_validator import reset_jwt_validator
        from mozaiksai.core.auth.jwks import reset_jwks_client
        from mozaiksai.core.auth.discovery import reset_discovery_client

        clear_auth_config_cache()
        reset_jwt_validator()
        reset_jwks_client()
        reset_discovery_client()

        monkeypatch.setenv("AUTH_ENABLED", "true")
        # Set both overrides to skip discovery in tests
        monkeypatch.setenv("AUTH_ISSUER", TEST_ISSUER)
        monkeypatch.setenv("AUTH_JWKS_URL", "https://test-jwks.com/keys")
        monkeypatch.setenv("AUTH_AUDIENCE", TEST_AUDIENCE)
        monkeypatch.setenv("AUTH_REQUIRED_SCOPE", "access_as_user")

        yield

        clear_auth_config_cache()
        reset_jwt_validator()
        reset_jwks_client()
        reset_discovery_client()

    @pytest.mark.asyncio
    async def test_valid_token(self, monkeypatch):
        """Test validation of a valid token."""
        from mozaiksai.core.auth.jwt_validator import get_jwt_validator
        from mozaiksai.core.auth.jwks import get_jwks_client

        # Mock JWKS client
        jwks_client = get_jwks_client()
        async def mock_get_key(kid):
            if kid == TEST_KID:
                return get_test_jwk()
            return None
        monkeypatch.setattr(jwks_client, "get_signing_key", mock_get_key)

        token = create_test_token()
        validator = get_jwt_validator()
        claims = await validator.validate_token(token)

        assert claims.user_id == TEST_USER_ID
        assert claims.email == TEST_EMAIL
        assert "access_as_user" in claims.scopes
        assert claims.has_user_scope is True

    @pytest.mark.asyncio
    async def test_expired_token(self, monkeypatch):
        """Test rejection of expired token."""
        from mozaiksai.core.auth.jwt_validator import get_jwt_validator, AuthError
        from mozaiksai.core.auth.jwks import get_jwks_client

        jwks_client = get_jwks_client()
        async def mock_get_key(kid):
            return get_test_jwk() if kid == TEST_KID else None
        monkeypatch.setattr(jwks_client, "get_signing_key", mock_get_key)

        token = create_test_token(exp_offset=-3600)  # Expired 1 hour ago
        validator = get_jwt_validator()

        with pytest.raises(AuthError) as exc_info:
            await validator.validate_token(token)
        assert "expired" in exc_info.value.message.lower()
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_issuer(self, monkeypatch):
        """Test rejection of wrong issuer."""
        from mozaiksai.core.auth.jwt_validator import get_jwt_validator, AuthError
        from mozaiksai.core.auth.jwks import get_jwks_client

        jwks_client = get_jwks_client()
        async def mock_get_key(kid):
            return get_test_jwk() if kid == TEST_KID else None
        monkeypatch.setattr(jwks_client, "get_signing_key", mock_get_key)

        token = create_test_token(issuer="https://wrong-issuer.com")
        validator = get_jwt_validator()

        with pytest.raises(AuthError) as exc_info:
            await validator.validate_token(token)
        assert "issuer" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_wrong_audience(self, monkeypatch):
        """Test rejection of wrong audience."""
        from mozaiksai.core.auth.jwt_validator import get_jwt_validator, AuthError
        from mozaiksai.core.auth.jwks import get_jwks_client

        jwks_client = get_jwks_client()
        async def mock_get_key(kid):
            return get_test_jwk() if kid == TEST_KID else None
        monkeypatch.setattr(jwks_client, "get_signing_key", mock_get_key)

        token = create_test_token(audience="wrong-audience")
        validator = get_jwt_validator()

        with pytest.raises(AuthError) as exc_info:
            await validator.validate_token(token)
        assert "audience" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_missing_scope(self, monkeypatch):
        """Test rejection when required scope is missing."""
        from mozaiksai.core.auth.jwt_validator import get_jwt_validator, AuthError
        from mozaiksai.core.auth.jwks import get_jwks_client

        jwks_client = get_jwks_client()
        async def mock_get_key(kid):
            return get_test_jwk() if kid == TEST_KID else None
        monkeypatch.setattr(jwks_client, "get_signing_key", mock_get_key)

        token = create_test_token(scopes="some_other_scope")
        validator = get_jwt_validator()

        with pytest.raises(AuthError) as exc_info:
            await validator.validate_token(token, require_scope=True)
        assert exc_info.value.status_code == 403
        assert "scope" in exc_info.value.message.lower()


# ============================================================
# HTTP Dependencies Tests
# ============================================================

class TestHTTPDependencies:
    """Tests for FastAPI auth dependencies."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        from mozaiksai.core.auth.config import clear_auth_config_cache
        from mozaiksai.core.auth.jwt_validator import reset_jwt_validator
        from mozaiksai.core.auth.jwks import reset_jwks_client

        clear_auth_config_cache()
        reset_jwt_validator()
        reset_jwks_client()

        yield

        clear_auth_config_cache()
        reset_jwt_validator()
        reset_jwks_client()

    @pytest.mark.asyncio
    async def test_require_user_auth_disabled(self, monkeypatch):
        """Test require_user with auth disabled returns anonymous."""
        from mozaiksai.core.auth.dependencies import require_user

        monkeypatch.setenv("AUTH_ENABLED", "false")

        # Create mock request
        request = MagicMock()
        request.state = MagicMock()
        request.query_params = {}

        principal = await require_user(request, authorization=None)

        assert principal.user_id == "anonymous"
        assert request.state.user_id == "anonymous"

    @pytest.mark.asyncio
    async def test_require_user_missing_token(self, monkeypatch):
        """Test require_user raises 401 when token is missing."""
        from mozaiksai.core.auth.dependencies import require_user
        from fastapi import HTTPException

        monkeypatch.setenv("AUTH_ENABLED", "true")

        request = MagicMock()
        request.state = MagicMock()
        request.query_params = {}

        with pytest.raises(HTTPException) as exc_info:
            await require_user(request, authorization=None)
        assert exc_info.value.status_code == 401


# ============================================================
# WebSocket Auth Tests
# ============================================================

class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        from mozaiksai.core.auth.config import clear_auth_config_cache
        from mozaiksai.core.auth.jwt_validator import reset_jwt_validator
        from mozaiksai.core.auth.jwks import reset_jwks_client

        clear_auth_config_cache()
        reset_jwt_validator()
        reset_jwks_client()

        yield

        clear_auth_config_cache()
        reset_jwt_validator()
        reset_jwks_client()

    @pytest.mark.asyncio
    async def test_authenticate_websocket_auth_disabled(self, monkeypatch):
        """Test WebSocket auth with auth disabled returns anonymous."""
        from mozaiksai.core.auth.websocket_auth import authenticate_websocket

        monkeypatch.setenv("AUTH_ENABLED", "false")

        websocket = MagicMock()
        websocket.state = MagicMock()
        websocket.query_params = {}

        user = await authenticate_websocket(websocket)

        assert user is not None
        assert user.user_id == "anonymous"
        assert websocket.state.user_id == "anonymous"

    @pytest.mark.asyncio
    async def test_authenticate_websocket_missing_token(self, monkeypatch):
        """Test WebSocket auth closes connection when token is missing."""
        from mozaiksai.core.auth.websocket_auth import authenticate_websocket, WS_CLOSE_AUTH_REQUIRED

        monkeypatch.setenv("AUTH_ENABLED", "true")

        websocket = MagicMock()
        websocket.state = MagicMock()
        websocket.query_params = {}
        websocket.close = AsyncMock()

        user = await authenticate_websocket(websocket)

        assert user is None
        websocket.close.assert_called_once()
        call_args = websocket.close.call_args
        assert call_args.kwargs.get("code") == WS_CLOSE_AUTH_REQUIRED

    @pytest.mark.asyncio
    async def test_verify_user_owns_resource(self):
        """Test resource ownership verification."""
        from mozaiksai.core.auth.websocket_auth import verify_user_owns_resource

        assert verify_user_owns_resource("user-123", "user-123") is True
        assert verify_user_owns_resource("user-123", "user-456") is False
        assert verify_user_owns_resource("", "user-123") is False
        assert verify_user_owns_resource("user-123", "") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
