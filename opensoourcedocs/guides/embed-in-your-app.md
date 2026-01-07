# Embed MozaiksAI In Your App

This guide explains how to use MozaiksAI as the agentic workflow runtime inside *your* product.

## Choose Your Integration Style

### Option A: Embed the included ChatUI (recommended)

- Fastest path to a working product experience
- You use MozaiksAI’s existing event protocol + artifact rendering

You still build your own control plane for:

- users/orgs/apps
- entitlements
- workflow selection
- token issuance

### Option B: Build your own UI (advanced)

- You connect to MozaiksAI over WebSocket
- You render the transcript and artifacts yourself

## Step 1 — Run The Runtime

Run MozaiksAI (self-hosted, container, VM, etc.) and ensure it can reach MongoDB.

For local development, the repo provides scripts (see `README.md`).

## Step 2 — Your Control Plane: “Launch” a Workflow

MozaiksAI needs these values for a session:

- `workflow_name`
- `app_id`
- `user_id`
- `chat_id`

### Start a chat session

The runtime exposes a chat start endpoint:

```http
POST /api/chats/{app_id}/{workflow_name}/start
Content-Type: application/json
Authorization: Bearer <token>

{
  "user_id": "user-123",
  "client_request_id": "optional-idempotency-key",
  "force_new": false
}
```

It returns a `chat_id` and a `websocket_url`.

Important: if auth is enabled, `user_id` must match the authenticated principal.

## Step 3 — Connect via WebSocket

### WebSocket URL

```text
/ws/{workflow_name}/{app_id}/{chat_id}/{user_id}
```

If your deployment requires passing a token via query param, enable:

- `MOZAIKS_WS_ALLOW_QUERY_TOKEN=true`

…and connect like:

```text
wss://<runtime-host>/ws/<workflow>/<app_id>/<chat_id>/<user_id>?access_token=<JWT>
```

## Step 4 — Send User Input

If you build your own client, you’ll send “user input” events.

A common message shape (used by the included ChatUI adapter) looks like:

```json
{
  "type": "user.input.submit",
  "chat_id": "<chat_id>",
  "text": "Hello — help me generate an agent pack",
  "context": {
    "source": "chat_interface",
    "conversation_mode": "workflow",
    "workflow_name": "<workflow_name>",
    "app_id": "<app_id>",
    "user_id": "<user_id>"
  }
}
```

The runtime responds by streaming events/messages/artifacts back over the same socket.

## Step 5 — Make It Your Product

To build “your own ecosystem”:

- Treat MozaiksAI as the execution layer.
- Keep product policy (plans, entitlements, quotas) in your control plane.
- Create workflows that match your product capabilities.

See:

- [MozaiksAI In Your Ecosystem](../concepts/ecosystem.md)
- [Auth Boundary](../concepts/auth-boundary.md)
- [Create a Workflow](create-a-workflow.md)
