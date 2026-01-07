# Runtime API (Practical Reference)

This is a pragmatic reference for integrating with the current MozaiksAI runtime server.

## WebSocket (Workflow Execution)

### Connect

```text
GET /ws/{workflow_name}/{app_id}/{chat_id}/{user_id}
```

When auth is enabled, the runtime validates that the token user matches `{user_id}`.

If you are using query-string token transport, enable `MOZAIKS_WS_ALLOW_QUERY_TOKEN=true` and connect with:

```text
wss://<host>/ws/<workflow>/<app_id>/<chat_id>/<user_id>?access_token=<JWT>
```

### Send user input

A common input event shape:

```json
{
  "type": "user.input.submit",
  "chat_id": "<chat_id>",
  "text": "Hello",
  "context": {
    "workflow_name": "<workflow_name>",
    "app_id": "<app_id>",
    "user_id": "<user_id>"
  }
}
```

## HTTP (Chat Session Management)

### Start a chat

```text
POST /api/chats/{app_id}/{workflow_name}/start
```

Returns `chat_id` and a `websocket_url` for connecting.

### Check existence / metadata

```text
GET /api/chats/exists/{app_id}/{workflow_name}/{chat_id}
GET /api/chats/meta/{app_id}/{workflow_name}/{chat_id}
```
