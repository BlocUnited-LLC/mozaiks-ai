# Observability and Token Tracking

Note: Token accounting is strictly event-driven. See `PERSISTENCE.md` and `docs/EVENT_ARCHITECTURE.md` for the authoritative schema and event flows. We do not use periodic backfills; missing `UsageSummaryEvent` is treated as an error to surface pipeline issues early.

This repo is set up to run “production-like” locally: Azure Key Vault for secrets, AG2 for token accounting, and optional OpenTelemetry (OTEL) via OpenLIT for telemetry.

## What does what

- AG2 UsageSummaryEvent (source of truth)
  - Providers emit `actual` and/or `total` summaries. We compute deltas from these events and persist them.
### Recommended local setup (with collector)

```powershell
# 1) Activate env + login (PowerShell)
.venv\Scripts\activate; az login --tenant blocunited.com

# 2) Start OTEL Collector (either natively or via Docker Compose)
# Native (collector must be installed):
otelcol --config=infra/otel/otel-collector-config.yaml

# Or run app + collector in Docker (from repo root):
docker compose -f infra/compose/docker-compose.yml up --build

# 3) Start backend
uvicorn shared_app:app --host 0.0.0.0 --port 8000

# 4) Start frontend
cd ChatUI; npm start
```

Verification cues:
- Backend logs show “OpenLIT initialized” (not “endpoint unreachable — disabling”).
- Collector logs show incoming traces/metrics when you chat.
  - We compute deltas from it and persist them.
- Wallet debits (business logic)
  - Optional; auto-disables if no collector is reachable.

## Real-time tracking path (how it flows)

- Agents are configured with AG2’s OpenAIWrapper-based config (see `core/core_config.py: make_llm_config`).
- During runs, AG2 emits events; we iterate `response.events` (see `UIEventProcessor`).
- On each `UsageSummaryEvent`, we parse model and token counts, compute deltas, and call `PerformanceManager.record_token_usage()`.
- `PerformanceManager` persists cumulative totals and last deltas to Mongo and emits `token_update` over WebSocket.
  - When the provider emits a `mode=total` summary, we persist authoritative totals.

## Key Vault (production-like local)

```powershell
az login --tenant <TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
```

2) Ensure your user has access to the vault (Key Vault Secrets User or appropriate access policy).

3) .env minimal:

```
AZURE_KEY_VAULT_NAME=<your-vault-name>
ENVIRONMENT=development
```

Secrets expected in the vault:

- MongoURI
- OpenAIApiKey

If a secret is missing, `core/core_config.py` falls back to environment variables.

## Telemetry options

- Off (local default): set once per shell

```powershell
$env:OPENLIT_ENABLED='false'
```

- On (local): run an OTEL Collector at `http://localhost:4317` and keep `OPENLIT_ENABLED` unset/true.
  - With Compose, the app uses `http://otel-collector:4317` inside the docker network automatically.

Minimal collector example (YAML sketch):

```yaml
receivers:
  otlp:
    protocols:
      grpc:
exporters:
  logging:
    loglevel: info
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging]
    metrics:
      receivers: [otlp]
      exporters: [logging]
```

## How token tracking works here

- Per-turn: deltas come only from `UsageSummaryEvent`. We persist to `ChatSessions.real_time_tracking.*`, emit `token_update` over WebSocket, and debit wallet by delta.
- Finalization: on `mode=total`, we persist authoritative totals and skip final wallet debit when incremental debits already happened.

Where to look:

- `core/observability/performance_manager.py`: real-time deltas + websocket events.
- `core/data/persistence_manager.py`: `save_usage_summary` guarded against double-debit.
- `core/transport/simple_transport.py`: triggers per-turn capture.
- `core/workflow/orchestration_patterns.py`: stores agents on the connection for capture.

## Run

```powershell
# Ensure tenant/subscription are set (see above)
uvicorn shared_app:app --host 0.0.0.0 --port 8000
```

Smoke test:

- Start a chat, send messages.
- Verify WebSocket `token_update` events.
- Check Mongo `ChatSessions.real_time_tracking.tokens` for cumulative and `last_delta` updates.
- Confirm wallet balance decrements gradually and no extra final debit is applied.

## Notes

- Telemetry is optional and non-blocking; enable it when you want dashboards.
- Accounting always uses AG2 totals; observability never touches wallet logic.
