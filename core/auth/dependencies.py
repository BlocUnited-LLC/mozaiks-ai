"""
FastAPI authentication dependencies for protected HTTP routes.

Usage:
    from core.auth.dependencies import require_user, require_any_auth

    @app.get("/api/user/profile")
    async def get_profile(user: UserPrincipal = Depends(require_user)):
        return {"user_id": user.user_id, "email": user.email}

    @app.get("/api/admin/stats")
    async def get_stats(user: UserPrincipal = Depends(require_role("admin"))):
        ...
"""

from typing import Optional, List, Callable
from dataclasses import dataclass

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.auth.config import get_auth_config
from core.auth.jwt_validator import get_jwt_validator, TokenClaims, AuthError
from logs.logging_config import get_core_logger

logger = get_core_logger("auth.dependencies")

# FastAPI security scheme for OpenAPI docs
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class UserPrincipal:
    """
    Authenticated user principal.

    Attached to request.state.user for downstream access.
    """

    user_id: str
    email: Optional[str]
    roles: List[str]
    scopes: List[str]
    raw_claims: dict

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def has_any_role(self, roles: List[str]) -> bool:
        """Check if user has any of the specified roles."""
        return any(r in self.roles for r in roles)

    def has_scope(self, scope: str) -> bool:
        """Check if user has a specific scope."""
        return scope in self.scopes


def _extract_token(
    authorization: Optional[HTTPAuthorizationCredentials],
    request: Request,
) -> Optional[str]:
    """
    Extract bearer token from Authorization header or query param.

    Priority:
    1. Authorization: Bearer <token> header
    2. ?access_token=<token> query param (for WebSocket upgrade)
    """
    if authorization and authorization.credentials:
        return authorization.credentials

    # Fallback to query param (useful for WS upgrade requests)
    token = request.query_params.get("access_token")
    return token if token else None


async def _validate_and_attach(
    request: Request,
    token: str,
    require_scope: bool = True,
) -> UserPrincipal:
    """Validate token and attach user principal to request.state."""
    validator = get_jwt_validator()

    try:
        claims: TokenClaims = await validator.validate_token(token, require_scope=require_scope)
    except AuthError as e:
        logger.warning(f"Auth failed: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)

    principal = UserPrincipal(
        user_id=claims.user_id,
        email=claims.email,
        roles=claims.roles,
        scopes=claims.scopes,
        raw_claims=claims.raw_claims,
    )

    # Attach to request state for downstream access
    request.state.user = principal
    request.state.user_id = principal.user_id

    return principal


async def require_user(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UserPrincipal:
    """
    Dependency that requires a valid user token with access_as_user scope.

    Returns UserPrincipal on success, raises HTTPException on failure.
    """
    config = get_auth_config()

    # Auth bypass for local development
    if not config.enabled:
        logger.warning("Auth disabled - using anonymous principal")
        principal = UserPrincipal(
            user_id="anonymous",
            email=None,
            roles=[],
            scopes=["access_as_user"],
            raw_claims={},
        )
        request.state.user = principal
        request.state.user_id = principal.user_id
        return principal

    token = _extract_token(authorization, request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    return await _validate_and_attach(request, token, require_scope=True)


async def require_any_auth(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UserPrincipal:
    """
    Dependency that requires any valid token (no scope enforcement).

    Useful for endpoints that should be accessible to any authenticated user
    regardless of delegated scopes.
    """
    config = get_auth_config()

    if not config.enabled:
        logger.warning("Auth disabled - using anonymous principal")
        principal = UserPrincipal(
            user_id="anonymous",
            email=None,
            roles=[],
            scopes=[],
            raw_claims={},
        )
        request.state.user = principal
        request.state.user_id = principal.user_id
        return principal

    token = _extract_token(authorization, request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    return await _validate_and_attach(request, token, require_scope=False)


def require_role(role: str) -> Callable:
    """
    Dependency factory that requires a specific role.

    Usage:
        @app.get("/admin")
        async def admin_only(user: UserPrincipal = Depends(require_role("admin"))):
            ...
    """

    async def role_checker(
        request: Request,
        authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    ) -> UserPrincipal:
        principal = await require_user(request, authorization)
        if not principal.has_role(role):
            raise HTTPException(
                status_code=403,
                detail=f"Required role: {role}",
            )
        return principal

    return role_checker


def require_any_role(roles: List[str]) -> Callable:
    """
    Dependency factory that requires any of the specified roles.

    Usage:
        @app.get("/moderator")
        async def mod_area(user: UserPrincipal = Depends(require_any_role(["admin", "moderator"]))):
            ...
    """

    async def role_checker(
        request: Request,
        authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    ) -> UserPrincipal:
        principal = await require_user(request, authorization)
        if not principal.has_any_role(roles):
            raise HTTPException(
                status_code=403,
                detail=f"Required roles (any): {roles}",
            )
        return principal

    return role_checker


async def optional_user(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[UserPrincipal]:
    """
    Dependency that optionally validates a token if present.

    Returns UserPrincipal if token is valid, None if no token.
    Raises HTTPException if token is present but invalid.
    """
    config = get_auth_config()

    if not config.enabled:
        return None

    token = _extract_token(authorization, request)
    if not token:
        return None

    return await _validate_and_attach(request, token, require_scope=False)


# ---------------------------------------------------------------------------
# Semantic aliases for enforcement clarity
# ---------------------------------------------------------------------------

# Alias for user-facing endpoints requiring delegated user tokens
require_user_scope = require_user


@dataclass
class ServicePrincipal:
    """
    Authenticated service principal (app-only token).
    
    Used for S2S internal calls where there is no user context.
    App-only tokens have no 'scp' claim; identity is the client_id/app.
    """
    
    client_id: str
    tenant_id: Optional[str]
    roles: List[str]
    raw_claims: dict

    def has_role(self, role: str) -> bool:
        """Check if service has a specific app role."""
        return role in self.roles


async def _validate_internal_token(
    request: Request,
    token: str,
) -> ServicePrincipal:
    """Validate app-only token for S2S calls."""
    validator = get_jwt_validator()
    
    try:
        # Validate token WITHOUT requiring user scope
        claims: TokenClaims = await validator.validate_token(token, require_scope=False)
    except AuthError as e:
        logger.warning(f"Internal auth failed: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    
    # App-only tokens should NOT have user scopes
    config = get_auth_config()
    if claims.scopes and config.required_scope in claims.scopes:
        # This is a delegated user token being used for internal call - reject
        logger.warning("Delegated user token used for internal endpoint - rejecting")
        raise HTTPException(
            status_code=403,
            detail="Internal endpoint requires app-only token, not delegated user token",
        )
    
    # Extract client_id (app identity) from standard claims
    client_id = claims.raw_claims.get("azp") or claims.raw_claims.get("appid") or claims.raw_claims.get("client_id")
    tenant_id = claims.raw_claims.get("tid")
    
    # App roles typically in 'roles' claim for app-only tokens
    app_roles = claims.raw_claims.get("roles", [])
    if isinstance(app_roles, str):
        app_roles = [app_roles]
    
    principal = ServicePrincipal(
        client_id=client_id or "unknown",
        tenant_id=tenant_id,
        roles=app_roles,
        raw_claims=claims.raw_claims,
    )
    
    # Attach to request state
    request.state.service = principal
    request.state.client_id = principal.client_id
    
    return principal


async def require_internal(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> ServicePrincipal:
    """
    Dependency for S2S/internal endpoints requiring app-only tokens.
    
    REJECTS delegated user tokens (those with access_as_user scope).
    Only accepts app-only tokens without user delegation.
    
    Usage:
        @app.post("/internal/webhook")
        async def internal_webhook(service: ServicePrincipal = Depends(require_internal)):
            # service.client_id identifies the calling app
            ...
    """
    config = get_auth_config()
    
    # Auth bypass for local development
    if not config.enabled:
        logger.warning("Auth disabled - using anonymous service principal")
        principal = ServicePrincipal(
            client_id="internal-dev",
            tenant_id=None,
            roles=[],
            raw_claims={},
        )
        request.state.service = principal
        request.state.client_id = principal.client_id
        return principal
    
    token = _extract_token(authorization, request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    
    return await _validate_internal_token(request, token)
