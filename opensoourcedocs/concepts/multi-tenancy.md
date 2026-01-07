# Multi-Tenancy (app_id Isolation)

MozaiksAI is designed to run as a **multi-tenant runtime**.

At minimum, you should treat these as the runtime’s isolation keys:

- `app_id`: your application/workspace/tenant boundary
- `user_id`: the end-user identity (from the validated token)
- `chat_id`: an execution session within a workflow

## How Isolation Works

The runtime scopes persisted state and queries using `app_id` (and in many places also `user_id`).

The control plane’s responsibilities are still critical:

- issue a token for the correct user
- ensure the user is allowed to act in the given `app_id`
- pass the correct `app_id` into the runtime routes

MozaiksAI intentionally does not maintain a user/org database; it trusts the control plane to have made those decisions before launch.

## WebSocket Route Shape

The primary workflow WebSocket route is:

```text
/ws/{workflow_name}/{app_id}/{chat_id}/{user_id}
```

When auth is enabled, the runtime verifies the JWT user matches the `{user_id}` path segment.

## Recommended Control Plane Contract

When you build your own ecosystem around MozaiksAI, define a small “launch contract” in your control plane:

- **Capability** (what product feature the user asked for)
- resolved **workflow_name**
- `app_id`
- `user_id`
- optional `chat_id` (for resume) or request a new chat

The runtime executes the workflow and streams events; your control plane can store the higher-level business objects.
