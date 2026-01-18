# MozaiksAI Advisory Role (Measurement + Advisory Only)

MozaiksAI is a runtime execution layer. It measures and emits telemetry and workflow events.
It does not price, bill, enforce, or provision. Control-plane systems consume signals and decide.

## 1. Role Clarification (Measurement + Advisory Only)

MozaiksAI is measurement and advisory only. It emits the following signals that could influence
pricing, lifecycle suggestions, or upsell recommendations:

### Usage Measurement Events (authoritative)
- `chat.usage_delta` per LLM call, emitted by `core/tokens/manager.py`:
  - `chat_id`, `app_id`, `user_id`, `workflow_name`
  - `agent_name`, `model_name`
  - `prompt_tokens`, `completion_tokens`, `total_tokens`
  - `cached`, `duration_sec`, `invocation_id`
- `chat.usage_summary` per chat/session, emitted by `core/tokens/manager.py`:
  - `chat_id`, `app_id`, `user_id`, `workflow_name`
  - `prompt_tokens`, `completion_tokens`, `total_tokens`

Notes:
- Emitted through the unified event dispatcher and forwarded to the UI via
  `core/transport/simple_transport.py`.
- Optional best-effort control-plane ingest exists for `chat.usage_summary` only
  (see `core/events/usage_ingest.py`).
- `USAGE_EVENTS_ENABLED=false` disables these emissions.

### Workflow Lifecycle and Reliability Signals (event stream)
- `chat.run_start`, `chat.run_complete` (session start/completion)
- `chat.error` (runtime errors)
- `chat.input_request`, `chat.input_timeout` (human-in-loop friction)
- `chat.tool_call`, `chat.tool_response` (tooling intensity)

These are AG2 runtime events serialized to the WebSocket stream.

### Performance and Operational Metrics (read-only endpoints)
- `/metrics/perf/aggregate` and `/metrics/perf/chats[/{chat_id}]`:
  - `active_chats`, `agent_turns`, `tool_calls`, `errors`
  - `runtime_sec`, `last_turn_duration_sec`
  - `prompt_tokens`, `completion_tokens`, `total_cost`
- `/health/active-runs`:
  - active run registry summary (concurrency signal)

### Storage Signals (Mongo, read-only to control plane)
- `ChatSessions` usage fields:
  - `usage_prompt_tokens_final`, `usage_completion_tokens_final`
  - `usage_total_tokens_final`, `usage_total_cost_final`, `duration_sec`, `status`
- Workflow rollups in `WorkflowStats` (`mon_{app_id}_{workflow_name}`) with per-agent averages.

### Attachment Volume Signals
- `chat.attachment_uploaded` events to the UI stream.
- `ChatSessions.attachments` metadata includes `size_bytes`, `intent`, and timestamps.

## 2. AI-Driven Pricing Inputs (Control Plane Derived)

These inputs are derived from the signals above. MozaiksAI does not compute or enforce them.

Subscription upgrade suggestions:
- Sustained high `total_tokens` or `total_cost` per `user_id` or `app_id`.
- Rising tool usage (`chat.tool_call`) and multi-agent intensity (`agent_name` diversity).
- Large or frequent attachments (`size_bytes`) and long `runtime_sec` sessions.

Hosting readiness suggestions:
- Increased `active_chats` and `run_start` rates (concurrency and throughput).
- Higher `runtime_sec` or `last_turn_duration_sec` (capacity strain).
- Elevated `errors` or `input_timeout` rates (stability and latency risks).
- High `tool_calls` per session (infrastructure pressure).

Enterprise outreach suggestions:
- Growth in distinct `user_id` counts per `app_id` (adoption).
- Multiple workflows with consistent `run_complete` volume (breadth of use).
- Stable high spend signals (`total_cost`, `total_tokens`) with low error rates.
- Large attachment usage and complex tool usage patterns.

## 3. Explicit Boundaries (Must NEVER Do)

MozaiksAI must never:
- Mutate or create subscription plans or pricing.
- Call Stripe, entitlements, or payment APIs.
- Gate access, block chats, or enforce limits based on usage.
- Provision, scale, or deploy infrastructure based on usage signals.
- Expose secrets or billing data in events or logs.

`MONETIZATION_ENABLED` and related flags are platform configuration only. No billing or
enforcement logic exists in this runtime.

## 4. Safe Integration Points (Approved Outbound)

Only the following outbound integrations are approved for advisory signals:
- WebSocket event stream to ChatUI (internal) for usage and lifecycle events.
- Optional control-plane usage ingest:
  - `CONTROL_PLANE_USAGE_INGEST_ENABLED=true`
  - `CONTROL_PLANE_USAGE_INGEST_URL=<endpoint>`
  - Posts raw `chat.usage_summary` payloads only, best-effort, no blocking.

No other outbound billing or entitlement integrations exist in this runtime.
