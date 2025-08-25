# Observability and Token Tracking

Note: Token accounting now follows the AG2 lifecycle: incremental visibility via `print_usage_summary` and authoritative reconciliation via `gather_usage_summary`. We no longer parse individual `UsageSummaryEvent` objects for delta billing.

This repo is set up to run “production-like” locally: Azure Key Vault for secrets, AG2 for token accounting, and optional OpenTelemetry (OTEL) via OpenLIT for telemetry.

## What does what

– AG2 lifecycle usage summary
  - `print_usage_summary()` exposes current cumulative totals; we bill the delta (if not in free trial) via `PerformanceManager.bill_usage_from_print_summary`.
  - `gather_usage_summary()` produces final totals; we reconcile any residual via `PerformanceManager.record_final_usage_from_agents`.

## Real-time tracking path (how it flows)

- Agents are configured with AG2’s OpenAIWrapper-based config (see `core/core_config.py: make_llm_config`).
– During runs, orchestrator detects turn boundaries and calls `print_usage_summary` + `bill_usage_from_print_summary`.
– Final step: orchestrator calls `gather_usage_summary` + `record_final_usage_from_agents`.
– WebSocket delta broadcasting is currently disabled (can be reintroduced from in-memory state if needed).

## How token tracking works here

– Per-turn: delta = cumulative_from_print - last_billed_total_tokens.
– Finalization: residual = final_total - last_billed_total_tokens (debited unless FREE_TRIAL_ENABLED) then final_* fields persisted.

Where to look:

– `core/observability/performance_manager.py`: lifecycle billing helpers.
– `core/workflow/orchestration_patterns.py`: orchestrator invoking print/gather lifecycle.
– `core/data/persistence_manager.py`: wallet debits only (no balance mirroring in ChatSessions).
