# Runtime Configuration

This page lists the main environment variables you’ll care about when embedding MozaiksAI.

## Auth

These control runtime authentication.

- `MOZAIKS_OIDC_AUTHORITY`: OIDC authority / issuer
- `AUTH_AUDIENCE`: expected `aud` claim
- `AUTH_REQUIRED_SCOPE`: required delegated user scope (default behavior expects a user-delegated token)

### WebSocket token transport

- `MOZAIKS_WS_ALLOW_QUERY_TOKEN`: if `true`, allows `?access_token=<JWT>` on WebSocket URLs

## Multi-tenancy

- `app_id` is a request/session-level isolation key (passed on routes)

See: [Multi-Tenancy](../concepts/multi-tenancy.md).

## Docs / Open Source

Public documentation is built from `opensoourcedocs/` (internal repo docs under `/docs` are intentionally not published).
