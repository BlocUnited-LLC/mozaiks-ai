# MozaiksAI Architecture Overview

**Version:** 5.0.0  
**Last Updated:** October 2025  
**Maintainer:** BlocUnited LLC

## Introduction

MozaiksAI is a production-grade orchestration runtime built on Microsoft's Autogen (AG2) framework. It adds event-driven persistence, real-time WebSocket streaming, multi-tenant isolation, dynamic UI component invocation, and app-scale observability to the AG2 agent collaboration model.

The platform is designed around a **strategically lean** philosophy: every component serves a clear, non-overlapping purpose, and the overall architecture minimizes coupling while maximizing flexibility for workflow composition.

## High-Level System Layers

```
┌─────────────────────────────────────────────────────────┐
│              ChatUI (React Frontend)                    │
│  - WebSocket Transport                                  │
│  - Artifact Design System                               │
│  - Dynamic Component Rendering                          │
└──────────────────┬──────────────────────────────────────┘
                   │ WebSocket/HTTP
┌──────────────────▼──────────────────────────────────────┐
│         MozaiksAI Runtime (FastAPI + AG2)               │
│  ┌────────────────────────────────────────────────┐     │
│  │  SimpleTransport (WebSocket Management)        │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  UnifiedEventDispatcher (Business/UI/AG2)      │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  Orchestration Layer (Workflow Execution)      │     │
│  │  - Pattern Registry (handoffs, context vars)   │     │
│  │  - Auto-Tool Execution                         │     │
│  │  - Structured Output Handling                  │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  AG2PersistenceManager (MongoDB)               │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │  PerformanceManager (Metrics & Observability)  │     │
│  └────────────────────────────────────────────────┘     │
└──────────────────┬──────────────────────────────────────┘
                   │ MongoDB Protocol
┌──────────────────▼──────────────────────────────────────┐
│              MongoDB Atlas / Local Instance             │
│  Collections:                                           │
│  - chat_sessions (lean session + message log)           │
│  - workflow_stats_{app}_{workflow}               │
│  - app_themes                                    │
└─────────────────────────────────────────────────────────┘
```

## Core Subsystems

### 1. Transport Layer (`core/transport/simple_transport.py`)

**Purpose:** Real-time bidirectional communication between runtime and frontend.

**Key Responsibilities:**
- WebSocket connection lifecycle management (connect, heartbeat, disconnect)
- Message filtering based on `visual_agents` configuration (prevents internal agent chatter from reaching UI)
- Event envelope construction (maps AG2 `kind` → frontend `type` namespace)
- Pre-connection buffering (holds messages if WebSocket not yet established)
- Input request correlation (links frontend user input submissions back to orchestration callbacks)

**Special Logic:**
- **Agent visibility filtering:** Only agents listed in `workflow.json` → `visual_agents` array emit messages to the UI. This keeps internal coordination agents (like orchestrators or tool managers) invisible to end users.
- **Auto-tool deduplication:** Agents with `auto_tool_mode: true` emit both `text` (with `agent_message`) and `tool_call` events. The transport suppresses the `text` variant to prevent duplicate messages in the chat UI.
- **UI_HIDDEN triggers:** Context variable derived triggers (e.g., `interview_complete` → `"NEXT"`) are marked `ui_hidden: true` in `context_variables.json`. Transport sets `_mozaiks_hide: true` on matching messages so the frontend can suppress them while still evaluating the trigger.

**Module Reference:** `core/transport/simple_transport.py` (class `SimpleTransport`)

---

### 2. Event Dispatcher (`core/events/unified_event_dispatcher.py`)

**Purpose:** Centralized routing for all event types in the platform.

**Event Categories:**

1. **Business Events** (`BusinessLogEvent`)
   - **Identifier:** `log_event_type` field
   - **Examples:** `SERVER_STARTUP_COMPLETED`, `WORKFLOW_SYSTEM_READY`
   - **Handler:** `BusinessLogHandler` → structured logging
   - **Usage:** `await dispatcher.emit_business_event(log_event_type="...", description="...", context={...})`

2. **UI Tool Events** (`UIToolEvent`)
   - **Identifier:** `ui_tool_id` field
   - **Examples:** `agent_api_key_input`, `action_plan`, `file_download_center`
   - **Handler:** `UIToolHandler` → WebSocket transport
   - **Usage:** `await dispatcher.emit_ui_tool_event(ui_tool_id="...", payload={...}, workflow_name="...")`

3. **AG2 Runtime Events** (not an enum member; handled separately)
   - **Identifier:** `kind` field (e.g., `text`, `tool_call`, `structured_output_ready`)
   - **Flow:** AG2 → `event_serialization.py` → `SimpleTransport.build_outbound_event_envelope()` → WebSocket
   - **No direct dispatcher involvement:** These events are serialized and forwarded by the transport layer, not emitted via `emit()` methods.

**Key Methods:**
- `emit_business_event()` – For monitoring/logging
- `emit_ui_tool_event()` – For agent-UI interactions
- `build_outbound_event_envelope()` – Transforms AG2 dict events for WebSocket

**Module Reference:** `core/events/unified_event_dispatcher.py` (class `UnifiedEventDispatcher`)

---

### 3. Orchestration Layer (`core/workflow/orchestration_patterns.py`)

**Purpose:** Executes multi-agent workflows with handoffs, context variables, and structured outputs.

**Key Components:**

- **Pattern Registry:** Maps workflow orchestration patterns (currently `DefaultPattern` only) to execution logic.
- **Context Variables:** Runtime key-value store accessible to all agents in a session; supports database lookups, environment vars, declarative constants, and derived triggers.
- **Handoff Rules:** Define agent-to-agent transitions (conditional or unconditional) via `handoffs.json`.
- **Structured Outputs:** Agents with `structured_outputs_required: true` emit Pydantic-validated JSON instead of free-form text.
- **Auto-Tool Execution:** Agents with `auto_tool_mode: true` automatically invoke their registered UI tool when emitting structured output.

**Special Logic:**
- **Cache Seed Propagation:** Each chat session gets a deterministic 32-bit cache seed derived from `app_id:chat_id` SHA-256 hash. This seed is stored in the `ChatSessions` document, emitted to the frontend via `chat_meta` event, and used to key UI component caches and LLM reproducibility layers.
- **Input Request Correlation:** When an agent emits `InputRequestEvent`, the orchestration layer registers a callback in the transport's `_input_request_registries`. Frontend submissions via `/api/input/submit` invoke the callback to resume the agent.

**Module Reference:** `core/workflow/orchestration_patterns.py` (function `run_default_pattern()`)

---

### 4. Persistence Layer (`core/data/persistence_manager.py`)

**Purpose:** Durable storage for chat sessions, messages, context snapshots, and workflow analytics.

**Schema:**

**Collection:** `chat_sessions` (one document per chat)

```json
{
  "_id": "chat_abc123",
  "app_id": "ent_001",
  "workflow_name": "Generator",
  "user_id": "user_xyz",
  "created_at": "2025-10-02T14:30:00Z",
  "last_updated_at": "2025-10-02T14:35:00Z",
  "last_sequence": 42,
  "cache_seed": 2847561923,
  "messages": [
    {
      "role": "user",
      "name": "user",
      "content": "Create a social media workflow",
      "timestamp": "2025-10-02T14:30:05Z",
      "sequence": 1,
      "event_type": "message.created"
    },
    {
      "role": "assistant",
      "name": "ContextAgent",
      "content": "...",
      "timestamp": "2025-10-02T14:30:12Z",
      "sequence": 2,
      "event_type": "message.created"
    }
  ],
  "context_snapshot": {
    "interview_complete": true,
    "api_key_received": false
  }
}
```

**Collection:** `workflow_stats_{app}_{workflow}` (runtime metrics rollup)

```json
{
  "_id": "stat_001",
  "chat_id": "chat_abc123",
  "total_tokens": 15420,
  "total_cost": 0.0231,
  "agent_stats": {
    "ContextAgent": {"tokens": 8200, "cost": 0.0123, "duration_ms": 4500}
  }
}
```

**Collection:** `app_themes` (UI theming config)

```json
{
  "_id": "ent_001",
  "colors": {"primary": {"main": "#6366f1"}},
  "typography": {"fontFamily": "Inter"},
  "metadata": {"name": "App Theme"}
}
```

**Resume Logic:**
1. Fetch `chat_sessions` document by `_id`
2. Replay `messages` array into AG2 `GroupChat.messages`
3. Restore `context_snapshot` into `ConversableContext`
4. Continue orchestration from last checkpoint

**Module Reference:** `core/data/persistence_manager.py` (class `AG2PersistenceManager`)

---

### 5. Observability & Performance (`core/observability/performance_manager.py`)

**Purpose:** Real-time metrics collection and Prometheus-compatible exposition.

**Metrics Collected:**
- **Aggregate:** Total turns, tool calls, tokens, cost across all chats
- **Per-Chat:** Tokens/cost/duration per agent, workflow metadata
- **Per-Agent:** Response times, token efficiency

**Endpoints:**
- `GET /metrics/perf/aggregate` → JSON aggregate counters
- `GET /metrics/perf/chats` → Array of per-chat snapshots
- `GET /metrics/perf/chats/{chat_id}` → Single chat detail
- `GET /metrics/prometheus` → Prometheus text exposition

**Module Reference:** `core/observability/performance_manager.py` (class `PerformanceManager`)

---

## Workflow Composition Model

Workflows are self-contained folders under `workflows/{WorkflowName}/` with the following structure:

```
workflows/Generator/
├── workflow.json          # Orchestration config (agents, handoffs, context vars)
├── agents.json            # Agent system messages & config
├── tools.json             # Tool manifest (Agent_Tool + UI_Tool entries)
├── structured_outputs.json # Pydantic schema registry
├── context_variables.json  # Context var definitions
├── handoffs.json          # Handoff rules
└── tools/                 # Python tool implementations
    ├── generate_workflow.py
    └── download_bundle.py
```

**Key Files:**

- **`workflow.json`:** Defines `visual_agents`, `max_turns`, `human_in_the_loop`, startup mode
- **`agents.json`:** System messages with `[ROLE]`, `[OBJECTIVE]`, `[CONTEXT]`, `[GUIDELINES]`, `[INSTRUCTIONS]` sections
- **`tools.json`:** Registers both backend tools (`Agent_Tool`) and UI components (`UI_Tool`)
- **`structured_outputs.json`:** Maps agents to Pydantic models for validated output
- **`context_variables.json`:** Declares database, environment, declarative, and derived variables
- **`handoffs.json`:** Routes agents via conditional or unconditional transitions

**Hot-Reload:** Tool modules and workflow configs can be updated without restarting the server (controlled via `CLEAR_TOOL_CACHE_ON_START` env var).

---

## Multi-Tenancy & Isolation

**App ID:** Top-level tenant identifier. All MongoDB queries include `app_id` filter. Chat IDs are scoped per app.

**Workspace Separation:** Each app can have isolated:
- Theme configurations (`app_themes` collection)
- Workflow stat rollups (`workflow_stats_{app}_{workflow}`)
- Context variable namespaces (app-specific database queries)

**Cache Seed:** Deterministic per-chat seed ensures:
- Reproducible LLM responses on resume (same seed → same pseudo-random behavior)
- UI component cache isolation (key = `{chatId}:{cache_seed}:{workflow}:{component}`)

---

## Security & Secrets Management

**Secrets Handling:**
- API keys are NEVER logged in plaintext
- UI components mask secrets by default with manual reveal toggle
- Backend tools validate presence but only log key length/type metadata
- Theme data is sanitized before storage (no script injection)

**Environment Variables:**
- Sensitive config (MongoDB URIs, LLM keys) live in `.env` (not committed)
- Runtime toggles (logging format, cache behavior) are documented in `docs/runtime/configuration_reference.md`

---

## Next Steps

- **Runtime Deep Dive:** Explore transport, events, and persistence in `docs/runtime/`
- **Workflow Authoring:** Learn manifest patterns in `docs/workflows/`
- **Frontend Integration:** Understand component lifecycle in `docs/frontend/`
- **Operations:** Deploy and monitor via guides in `docs/operations/`

---

**Module Index:**
- Transport: `core/transport/simple_transport.py`
- Events: `core/events/unified_event_dispatcher.py`
- Orchestration: `core/workflow/orchestration_patterns.py`
- Persistence: `core/data/persistence_manager.py`
- Observability: `core/observability/performance_manager.py`
- Workflow Manager: `core/workflow/workflow_manager.py`
