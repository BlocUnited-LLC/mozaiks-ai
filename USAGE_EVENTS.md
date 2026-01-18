# MozaiksAI Usage Events (v1)

This document describes the current usage events emitted by the runtime.
These are measurement/advisory signals only (no entitlements or billing logic).
This document is authoritative for current usage event schemas and boundaries.

## Emission Sources

Usage events are emitted via `core/tokens/manager.py` and the unified event
dispatcher. The main emitters are:

- AG2 LLM calls: `core/observability/realtime_token_logger.py` ->
  `TokenManager.emit_usage_delta(...)`.
- General (non-AG2) mode: `core/transport/simple_transport.py` emits
  both `chat.usage_delta` and `chat.usage_summary`.

Emission can be disabled globally with `USAGE_EVENTS_ENABLED=false`
(`core/tokens/manager.py`).

## Measurement Event Schema (TokenManager)

These events are the canonical measurement signals and include app/user/workflow
dimensions. They are emitted through the unified event dispatcher with
event types `chat.usage_delta` and `chat.usage_summary`.

### chat.usage_delta

Emitted per LLM call with per-agent granularity when available.

Fields:
- `event_id` string: short event id (12 hex chars).
- `event_ts` string: ISO-8601 timestamp.
- `chat_id` string: chat/session id.
- `app_id` string: tenant/app id.
- `user_id` string: user id (or "anonymous").
- `workflow_name` string: workflow identifier.
- `agent_name` string|null: agent label if available.
- `model_name` string|null: model name if available.
- `prompt_tokens` integer: prompt token count (>=0).
- `completion_tokens` integer: completion token count (>=0).
- `total_tokens` integer: total tokens (>=0).
- `cached` boolean: cached response flag.
- `duration_sec` number: call duration (seconds).
- `invocation_id` string|null: AG2 invocation id when available.

Example:
```json
{
  "event_id": "a1b2c3d4e5f6",
  "event_ts": "2026-01-12T03:12:34.567890+00:00",
  "chat_id": "chat_123",
  "app_id": "app_abc",
  "user_id": "user_456",
  "workflow_name": "AgentGenerator",
  "agent_name": "PlannerAgent",
  "model_name": "gpt-4o-mini",
  "prompt_tokens": 120,
  "completion_tokens": 48,
  "total_tokens": 168,
  "cached": false,
  "duration_sec": 0.82,
  "invocation_id": "inv_789"
}
```

### chat.usage_summary

Emitted as a summary snapshot (currently used in general mode).

Fields:
- `event_id` string
- `event_ts` string
- `chat_id` string
- `app_id` string
- `user_id` string
- `workflow_name` string
- `prompt_tokens` integer
- `completion_tokens` integer
- `total_tokens` integer

Example:
```json
{
  "event_id": "f1e2d3c4b5a6",
  "event_ts": "2026-01-12T03:12:35.000000+00:00",
  "chat_id": "chat_123",
  "app_id": "app_abc",
  "user_id": "user_456",
  "workflow_name": "GeneralCapability",
  "prompt_tokens": 400,
  "completion_tokens": 200,
  "total_tokens": 600
}
```

## Dimensions

- Per chat: `chat_id`
- Per app: `app_id`
- Per user: `user_id`
- Per workflow: `workflow_name`
- Optional per agent/model: `agent_name`, `model_name` (delta only)

## Storage and Forwarding

- Stored in MongoDB:
  - `ChatSessions.usage_*` fields (final totals)
  - `WorkflowStats` rollups via `AG2PersistenceManager.update_session_metrics`
  - See `core/data/persistence/persistence_manager.py` and `core/data/models.py`.
- Forwarded to the UI through the unified dispatcher and transport:
  - `core/events/unified_event_dispatcher.py`
  - `core/transport/simple_transport.py` sends `{"kind": "usage_delta|usage_summary", ...}`

## Note: AG2 UsageSummaryEvent (UI Stream Only)

AG2 can emit a `UsageSummaryEvent` which is serialized for the WebSocket stream
with a different payload shape (`{"kind": "usage_summary", "usage": {...}}`)
in `core/events/event_serialization.py`. This does not include app/user/workflow
dimensions and is separate from the TokenManager measurement events above.

## Billing & Entitlements Boundary

MozaiksAI is advisory and measurement-only. It does not:
- Enforce subscriptions or entitlements.
- Mutate billing state, plans, or pricing.
- Call Stripe or Payment APIs.

Billing and entitlement enforcement must live in the control plane, not in the runtime.

## Allowed Advisory Patterns

Permitted runtime behaviors (read-only, advisory):
- Usage aggregation (token/workflow/agent rollups).
- Warnings (UI-only, no blocking or gating).
- Recommendations (UX or control-plane suggestions).
- Pricing proposals (external only; runtime emits signals, control plane decides).

## Optional Control-Plane Ingest Hook

An optional best-effort hook can POST `chat.usage_summary` payloads to a
control-plane endpoint. This does not mutate state and is off by default.

Enable:
- `CONTROL_PLANE_USAGE_INGEST_ENABLED=true`
- `CONTROL_PLANE_USAGE_INGEST_URL=https://control-plane.example/usage/ingest`

Behavior:
- Posts the raw `chat.usage_summary` payload as JSON.
- Retries with exponential backoff on 429/5xx.
- Non-fatal (errors are logged and dropped; execution is never blocked).
- Implemented in `core/events/usage_ingest.py` and registered in
  `core/events/unified_event_dispatcher.py`.
