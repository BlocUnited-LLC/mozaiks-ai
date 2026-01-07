# Auth Boundary (Authentication vs Authorization)

MozaiksAI is an execution runtime.

- **Authentication**: proving the request came from a trusted caller.
- **Authorization**: deciding whether a user is allowed to do something.

MozaiksAI owns **authentication**.
Your app (the control plane) owns **authorization**.

## What The Runtime Authenticates

When auth is enabled, MozaiksAI validates tokens for:

- signature
- issuer
- audience
- expiration
- required scope (delegated user scope)

This applies to both HTTP endpoints and WebSocket connections.

## What The Runtime Does Not Authorize

MozaiksAI does **not** decide:

- whether a user is entitled to a workflow
- whether a subscription is active
- whether quotas/credits remain
- whether a workflow is “paid”

If a decision feels like product policy, it belongs in your control plane.

## Practical Integration Pattern

A common pattern is:

1. Your control plane authenticates the user (cookies, OAuth, etc.)
2. Your control plane authorizes the action (feature gate / plan check)
3. Your control plane issues a runtime token scoped for MozaiksAI
4. Your UI connects to the runtime and starts/resumes a chat

MozaiksAI then executes what it’s told to execute.

## WebSocket Token Transport

In this repo’s current WebSocket auth helper, the token can be provided via:

- a direct parameter (server-side wiring), or
- the `access_token` query parameter **only if** `MOZAIKS_WS_ALLOW_QUERY_TOKEN=true`

If you are writing your own client, the simplest approach is:

```text
wss://<runtime-host>/ws/<workflow>/<app_id>/<chat_id>/<user_id>?access_token=<JWT>
```

If you embed ChatUI, you can either:

- run with auth disabled for local dev, or
- adjust the ChatUI websocket URL builder to append `access_token`.

## Related Configuration

See [Runtime Configuration](../reference/configuration.md).
