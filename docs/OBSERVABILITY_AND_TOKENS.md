# Observability and Token Tracking

Note: Token accounting is strictly event-driven. See `PERSISTENCE.md` and `docs/EVENT_ARCHITECTURE.md` for the authoritative schema and event flows. We do not use periodic backfills; missing `UsageSummaryEvent` is treated as an error to surface pipeline issues early.

This repo is set up to run “production-like” locally: Azure Key Vault for secrets, AG2 for token accounting, and optional OpenTelemetry (OTEL) via OpenLIT for telemetry.

## What does what

- AG2 UsageSummaryEvent (source of truth)
  - Providers emit `actual` and/or `total` summaries. We compute deltas from these events and persist them.

## Real-time tracking path (how it flows)

- Agents are configured with AG2’s OpenAIWrapper-based config (see `core/core_config.py: make_llm_config`).
- During runs, AG2 emits events; we iterate `response.events` (see `UIEventProcessor`).
- On each `UsageSummaryEvent`, we parse model and token counts, compute deltas, and call `PerformanceManager.record_token_usage()`.
- `PerformanceManager` persists cumulative totals and last deltas to Mongo and emits `token_update` over WebSocket.
  - When the provider emits a `mode=total` summary, we persist authoritative totals.

## How token tracking works here

- Per-turn: deltas come only from `UsageSummaryEvent`. We persist to `ChatSessions.real_time_tracking.*`, emit `token_update` over WebSocket, and debit wallet by delta.
- Finalization: on `mode=total`, we persist authoritative totals and skip final wallet debit when incremental debits already happened.

Where to look:

- `core/observability/performance_manager.py`: real-time deltas + websocket events.
- `core/data/persistence_manager.py`: `save_usage_summary` guarded against double-debit.
- `core/transport/simple_transport.py`: triggers per-turn capture.
- `core/workflow/orchestration_patterns.py`: stores agents on the connection for capture.
