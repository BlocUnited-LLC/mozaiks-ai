# ChatSessions Document Schema (Contract)

This file documents the schema persisted in `MozaiksAI.ChatSessions` and the ownership of each field.

Top-level
- chat_id: string (unique per enterprise)
- enterprise_id: string
- user_id: string
- workflow_name: string
- status: string; one of [in_progress, completed]
- created_at: datetime (UTC)
- last_updated_at: datetime (UTC)
- completed_at: datetime (UTC, optional)
- termination_reason: string (optional)
- trace_id: string (hex, optional)
- usage_summary: object (optional)
  - raw: object
  - finalized_at: datetime (UTC)
- messages: array of Message

Message
- sender: string (raw)
- agent_name: string (normalized)
- content: string (back-compat)
- content_text: string (normalized text content)
- content_json: object (parsed structured output when available)
- format: string; one of [text, json, mixed]
- content_parts: array<object> (optional). Ordered parts, each part is { type: 'text'|'json', value: string|object }.
- role: string; one of [assistant, user]
- timestamp: datetime (UTC)
- event_type: string
- event_id: string
- is_user_proxy: bool

real_time_tracking
- trace_id: string (hex, optional)
- tokens
  - total_tokens: int (provisional cumulative)
  - prompt_tokens: int
  - completion_tokens: int
  - total_cost: float (provisional cumulative)
  - last_model: string|null
  - incremental_debits: bool
  - last_billed_total_tokens: int
  - final_total_tokens: int (authoritative post-run)
  - final_prompt_tokens: int
  - final_completion_tokens: int
  - final_cost: float
- counts
  - agent_turns: int
  - tool_calls: int
  - errors: int
- latency
  - last_turn_duration_sec: float|null
  - avg_turn_duration_sec: float
  - max_turn_duration_sec: float|null
  - turn_count: int
  - latency_by_agent: dict[str, {count: int, avg_sec: float}]
- overall
  - runtime_sec: float
- last_usage_recorded_at: datetime (UTC, optional)
- last_flush_at: datetime (UTC, optional)

Ownership
- AG2PersistenceManager: create, messages, usage_summary, completion status
- PerformanceManager: trace_id, real_time_tracking.* (latency, tokens, counts, runtime, lifecycle billing markers), flush timestamps

Structured outputs
- We store both normalized fields and a parts array when available.
- If a reply is a single message containing interleaved JSON and text, we parse the first JSON into content_json and place the pieces into content_parts in order.

Indexes
- Unique: (enterprise_id, chat_id)
- Non-unique: status, created_at
