# Auth Integration Gaps Report (MozaiksAI repo code-only)

Scope: This report lists what the current auth-related code does in this repo
and the gaps to close for a single shared auth system with MozaiksCore. It is
based only on code in this repository (no .md sources).

## Code inventory (auth-relevant)
- Runtime auth core: `core/auth/config.py`, `core/auth/discovery.py`,
  `core/auth/jwks.py`, `core/auth/jwt_validator.py`, `core/auth/dependencies.py`,
  `core/auth/websocket_auth.py`
- Runtime endpoints: `shared_app.py`
- Workflow router: `workflows/AppGenerator/tools/sandbox_api.py`
- ChatUI auth + API adapters: `ChatUI/src/adapters/auth.js`,
  `ChatUI/src/adapters/api.js`, `ChatUI/src/services/index.js`,
  `ChatUI/src/pages/ChatPage.js`
- Auth tests: `tests/test_auth.py`

## Current auth behavior (runtime)
- JWT validation via OIDC discovery + JWKS caching; overrides via
  `AUTH_ISSUER`/`AUTH_JWKS_URL`. Required scope enforced via `AUTH_REQUIRED_SCOPE`.
  `AUTH_ENABLED=false` bypasses auth and returns "anonymous".
  Sources: `core/auth/config.py`, `core/auth/discovery.py`,
  `core/auth/jwks.py`, `core/auth/jwt_validator.py`
- HTTP auth dependencies:
  - `require_user` enforces delegated user scope.
  - `require_any_auth` accepts any valid token.
  - `require_internal` accepts app-only tokens and rejects delegated user tokens.
  Sources: `core/auth/dependencies.py`
- WebSocket auth requires `access_token` (argument or query param when
  `MOZAIKS_WS_ALLOW_QUERY_TOKEN=true`) and validates path `user_id`.
  Source: `core/auth/websocket_auth.py`
- Protected endpoints are wired through these dependencies in `shared_app.py`
  and `workflows/AppGenerator/tools/sandbox_api.py`.
  Sources: `shared_app.py`, `workflows/AppGenerator/tools/sandbox_api.py`
- There are no token issuance or login endpoints in this repo.
  Source: `shared_app.py` (no `/api/auth/*` routes)

## Current auth behavior (ChatUI)
- Default auth mode is `mock`. `TokenAuthAdapter` expects `/api/auth/login` and
  `/api/auth/me` and stores a token in `localStorage`.
  Sources: `ChatUI/src/config/index.js`, `ChatUI/src/adapters/auth.js`
- API adapters do not attach Authorization headers; WebSocket URLs do not carry
  `access_token` query params.
  Source: `ChatUI/src/adapters/api.js`
- `user_id` and `app_id` can come from URL or defaults; fallback user_id is
  `"56132"` and app_id can be `"local-dev"` in dev.
  Source: `ChatUI/src/pages/ChatPage.js`

## Gaps to close for shared MozaiksCore + MozaiksAI auth
1. Token issuance is not in this repo.
   - Runtime only validates tokens; it does not issue or refresh them.
   - If ChatUI uses `TokenAuthAdapter`, `/api/auth/*` must exist elsewhere or
     a custom auth adapter must be injected.
   Sources: `shared_app.py`, `ChatUI/src/adapters/auth.js`
2. HTTP token propagation from ChatUI to runtime is missing.
   - No Authorization header injection in API adapters.
   - With `AUTH_ENABLED=true`, runtime endpoints require a valid token.
   Source: `ChatUI/src/adapters/api.js`
3. WebSocket token propagation from ChatUI to runtime is missing.
   - Runtime expects an `access_token` (query param allowed only if
     `MOZAIKS_WS_ALLOW_QUERY_TOKEN=true`).
   - ChatUI does not pass an access token in the WS URL.
   Sources: `core/auth/websocket_auth.py`, `ChatUI/src/adapters/api.js`
4. `app_id` is not bound to token claims.
   - Runtime validates `user_id` but does not validate `app_id` against the JWT.
   - Multi-tenant scope relies on path/body `app_id` and DB filters.
   Sources: `shared_app.py`, `core/multitenant/app_ids.py`
5. Header-based principal enforcement exists but is unused.
   - `_maybe_enforce_principal_headers` is defined but not called, so optional
     `x-app-id`/`x-user-id` headers are not enforced anywhere.
   Source: `shared_app.py`
6. Role-based auth helpers exist but are not applied to endpoints.
   - `require_role`/`require_any_role` are defined but unused in `shared_app.py`.
   Source: `core/auth/dependencies.py`, `shared_app.py`
7. App-only internal endpoints do not check allowlists or app roles.
   - `require_internal` validates token type but does not enforce client_id or
     app roles for access to internal endpoints.
   Sources: `core/auth/dependencies.py`, `shared_app.py`
8. Refresh token flow is stubbed in ChatUI.
   - `TokenAuthAdapter.refreshToken` returns a static success response.
   Source: `ChatUI/src/adapters/auth.js`

## Integration alignment checklist (code-level)
- Decide on the token format MozaiksCore will issue (user JWT vs runtime-scoped
  JWT). Runtime currently validates a single issuer/audience/scope.
- Ensure ChatUI (or a hosting app) attaches bearer tokens to all HTTP calls.
- Ensure WebSocket connections include an access token (query param or a custom
  handshake path supported by the runtime).
- Enforce `app_id` binding to the authenticated principal (JWT claim or
  enforced gateway headers).
- Add role-based enforcement where needed if MozaiksCore expects RBAC in
  runtime endpoints.

## References (code only)
- `core/auth/config.py`
- `core/auth/discovery.py`
- `core/auth/jwks.py`
- `core/auth/jwt_validator.py`
- `core/auth/dependencies.py`
- `core/auth/websocket_auth.py`
- `shared_app.py`
- `workflows/AppGenerator/tools/sandbox_api.py`
- `ChatUI/src/adapters/auth.js`
- `ChatUI/src/adapters/api.js`
- `ChatUI/src/services/index.js`
- `ChatUI/src/pages/ChatPage.js`
- `tests/test_auth.py`
