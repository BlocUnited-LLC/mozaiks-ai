## ChatSessions persistence schema (canonical) ✅

This document defines the authoritative schema and write paths in `MozaiksAI.ChatSessions` for live performance and token accounting. The system now uses the AG2 lifecycle (`print_usage_summary` for incremental visibility + `gather_usage_summary` for final reconciliation) instead of per-`UsageSummaryEvent` delta billing.

### Document shape

Top-level fields used by runtime:

- chat_id: string
- enterprise_id: string
- workflow_name: string
- user_id: string
- trace_id: string | null
- created_at: ISO datetime (set by create_chat_session)
- status: string (in_progress | completed | failed)

Runtime metrics live under `real_time_tracking`:

- real_time_tracking:
  - last_usage_recorded_at: ISO datetime
  - last_flush_at: ISO datetime
  - trace_id: string | null
  - overall:
    - runtime_sec: number
  - counts:
    - agent_turns: number
    - tool_calls: number
    - errors: number
  - latency:
    - last_turn_duration_sec: number | null
    - avg_turn_duration_sec: number
    - max_turn_duration_sec: number | null
    - turn_count: number
    - latency_by_agent: { [agent_key: string]: { count: number, avg_sec: number } }
  - tokens:
    - total_tokens: number (cumulative – updated opportunistically; final_* fields authoritative post-run)
    - prompt_tokens: number
    - completion_tokens: number
    - total_cost: number (may be provisional until final reconciliation)
    - last_model: string | null
    - incremental_debits: boolean (true if any incremental billing occurred via print summaries)
    - last_billed_total_tokens: number (cumulative tokens billed so far)
    - final_total_tokens / final_prompt_tokens / final_completion_tokens / final_cost: numbers (authoritative after final gather)

### Writers and responsibilities

- AG2PersistenceManager.create_chat_session
  - Upserts a baseline doc at chat start
  - Sets: chat_id, enterprise_id, workflow_name, user_id, created_at, status = "in_progress"

- PerformanceManager.record_workflow_start
  - Initializes in-memory perf state; logs workflow start

– AG2 lifecycle incremental billing (after each agent turn boundary):
  - Orchestrator calls `print_usage_summary()` then `PerformanceManager.bill_usage_from_print_summary()`
  - Wallet debits delta (unless FREE_TRIAL_ENABLED) and updates `last_billed_total_tokens` + marks `incremental_debits=true`

– Final reconciliation:
  - At workflow end orchestrator invokes `gather_usage_summary()` and `PerformanceManager.record_final_usage_from_agents()`
  - Any residual (final_total - last_billed_total_tokens) is debited (unless FREE_TRIAL_ENABLED) then final_* fields persisted

– PerformanceManager.record_final_token_usage (legacy helper) remains for compatibility but final authoritative write is via `record_final_usage_from_agents` now.

- PerformanceManager.record_agent_turn
  - Updates `real_time_tracking.latency` and `counts.agent_turns`

- PerformanceManager.record_tool_call
  - Increments `counts.tool_calls` and `counts.errors` (if error)

- PerformanceManager.flush
  - Writes `counts`, `latency`, and `overall.runtime_sec`, plus `last_flush_at`

### Invariants and rules

– Token billing is lifecycle-based: deltas = (current cumulative from `print_usage_summary` - `last_billed_total_tokens`).
– `final_*` fields override provisional cumulative fields post-run.
– Wallet balance is stored only in the Wallets collection (no `remaining_balance` field in ChatSessions).
– FREE_TRIAL_ENABLED skips all debits but still records usage analytics.

### Example (trimmed)

```json
{
  "chat_id": "c-123",
  "enterprise_id": "ent-1",
  "workflow_name": "generator",
  "user_id": "u-1",
  "real_time_tracking": {
    "counts": {"agent_turns": 3, "tool_calls": 1, "errors": 0},
    "latency": {
      "last_turn_duration_sec": 1.42,
      "avg_turn_duration_sec": 0.95,
      "max_turn_duration_sec": 1.98,
      "turn_count": 3,
      "latency_by_agent": {"Planner": {"count": 2, "avg_sec": 0.9}}
    },
    "tokens": {
      "total_tokens": 523,
      "prompt_tokens": 312,
      "completion_tokens": 211,
      "total_cost": 0.0021,
      "last_model": "gpt-4o-mini",
      "incremental_debits": true,
      "last_billed_total_tokens": 523,
      "final_total_tokens": 523,
      "final_prompt_tokens": 312,
      "final_completion_tokens": 211,
      "final_cost": 0.0021
    },
    "last_usage_recorded_at": "2025-08-16T06:12:33.000Z",
    "last_flush_at": "2025-08-16T06:12:34.000Z",
    "overall": {"runtime_sec": 9.8}
  }
}
```

### Operational notes

– Incremental visibility relies on `print_usage_summary`; if an agent/provider omits it, only final reconciliation occurs.
– Costs may be provisional; authoritative values written with final_* fields.
– No per-event token deltas are broadcast currently; could be reintroduced by sampling from in-memory state post-billing if needed.

# MozaiksAI Persistence Layer

The persistence layer in MozaiksAI is designed to be robust, real-time, and simple. It is built around the `AG2PersistenceManager` and uses MongoDB as the data store. Its primary responsibility is to save the state of every workflow as it happens, enabling features like chat resumption and live performance tracking.

## Core Component: `AG2PersistenceManager`

This class is the sole interface to the database for all workflow-related data. It does **not** contain complex business logic. Instead, it provides simple, event-driven methods:

-   `save_event(event, ...)`: This is the workhorse method. It receives an event from the `UIEventProcessor`, identifies its type, and performs the corresponding database operation.
-   `resume_chat(chat_id, ...)`: This method is called by the `Orchestrator` at the beginning of a session. It queries the database for a given `chat_id` and returns the message history, allowing the conversation to be resumed.

## Database Schema: The Session Document

We use a single, comprehensive document in the `chat_sessions` collection to store all data related to a single chat session. This denormalized approach is highly efficient for our use case, as it allows us to retrieve all information for a chat in a single database query.

Here is a sample structure of a session document:

```json
{
  "_id": "ObjectId('64a5e7d6f8e1d2c3b4a5e6f7')",
  "chat_id": "chat_abc123",
  "enterprise_id": "ent_xyz789",
  "user_id": "user_456",
  "workflow_name": "Generator",
  "created_at": "ISODate('2025-08-07T10:00:00Z')",
  "updated_at": "ISODate('2025-08-07T10:05:00Z')",
  "status": 1, // 0 = running, 1 = completed, -1 = failed
  "real_time_tracking": {
    "tokens": {
      "total_tokens": 1250,
      "prompt_tokens": 800,
      "completion_tokens": 450,
      "total_cost": 0.0025
    }
  },
  "messages": [
    {
      "sender": "user",
      "content": "Please generate a summary of the latest AI trends.",
      "role": "user",
      "timestamp": "ISODate('2025-08-07T10:00:05Z')",
      "event_type": "TextEvent",
      "event_id": "uuid_1"
    },
    {
      "sender": "ResearchAgent",
      "content": "Searching for the latest AI trends...",
      "role": "assistant",
      "timestamp": "ISODate('2025-08-07T10:01:10Z')",
      "event_type": "TextEvent",
      "event_id": "uuid_2"
    },
    {
      "sender": "WriterAgent",
      "content": "Here is the summary you requested...",
      "role": "assistant",
      "timestamp": "ISODate('2025-08-07T10:04:50Z')",
      "event_type": "TextEvent",
      "event_id": "uuid_3"
    }
  ]
}
```

### Field Descriptions

-   `chat_id`: The unique identifier for the chat session.
-   `enterprise_id`, `user_id`: Identifiers for multi-tenancy and user tracking.
-   `workflow_name`: The name of the workflow being executed (e.g., "Generator", "Chat").
-   `status`: The current status of the workflow.
-   `real_time_tracking`: An object containing live performance metrics.
    -   `tokens`: This sub-document is incremented in real-time by `UsageSummaryEvent`s.
-   `messages`: An array containing every message exchanged during the conversation.
    -   Each message is a self-contained object with the sender, content, role, and timestamp.
    -   We also store the `event_type` and `event_id` for complete traceability back to the source AG2 event.

## How real-time persistence works

1) TextEvent: `AG2PersistenceManager.save_event` appends a message to `messages`.
2) After each agent turn boundary: orchestrator calls `print_usage_summary` then `PerformanceManager.bill_usage_from_print_summary` (delta debit + update markers).
3) Workflow end: orchestrator calls `gather_usage_summary` then `PerformanceManager.record_final_usage_from_agents` (residual debit + final_* fields).

This event-driven approach keeps the session document accurate in near real time with minimal write contention.
