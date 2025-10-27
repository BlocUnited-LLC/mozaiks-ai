# Event Reference

Complete catalog of all WebSocket events emitted by the MozaiksAI runtime during workflow execution. This reference documents event types, payload schemas, sequencing patterns, and frontend integration.

---

## Table of Contents

1. [Event Architecture](#event-architecture)
2. [Event Envelope Format](#event-envelope-format)
3. [Core Chat Events](#core-chat-events)
4. [Tool Execution Events](#tool-execution-events)
5. [User Input Events](#user-input-events)
6. [UI Tool Events](#ui-tool-events)
7. [Workflow Lifecycle Events](#workflow-lifecycle-events)
8. [Error & System Events](#error--system-events)
9. [Event Sequences](#event-sequences)
10. [Frontend Integration](#frontend-integration)

---

## Event Architecture

### Event Flow

```
AG2 Runtime Event → UnifiedEventDispatcher → SimpleTransport → WebSocket → React ChatUI
                         (transform)           (broadcast)      (emit)     (handle)
```

### Event Processing Pipeline

1. **AG2 Event Generation**: Workflow agents emit native AG2 events (TextEvent, ToolCallEvent, etc.)
2. **Event Serialization**: `event_serialization.py` converts AG2 events to dict format with `kind` field
3. **Event Dispatching**: `UnifiedEventDispatcher.build_outbound_event_envelope()` transforms `kind` → `type` namespace and adds metadata (sequence, agent flags, suppression)
4. **Transport Broadcasting**: `SimpleTransport._broadcast_to_websockets()` emits to connected clients
5. **Frontend Handling**: `ChatPage.js` processes events by `type` field and updates UI state

### Namespace Mapping

Internal `kind` field → External `type` field for WebSocket transport:

```python
{
  'text': 'chat.text',
  'print': 'chat.print',
  'tool_call': 'chat.tool_call',
  'tool_response': 'chat.tool_response',
  'input_request': 'chat.input_request',
  'input_ack': 'chat.input_ack',
  'input_timeout': 'chat.input_timeout',
  'select_speaker': 'chat.select_speaker',
  'usage_summary': 'chat.usage_summary',
  'run_complete': 'chat.run_complete',
  'run_start': 'chat.run_start',
  'error': 'chat.error',
  'resume_boundary': 'chat.resume_boundary',
  'structured_output_ready': 'chat.structured_output_ready'
}
```

### Event Suppression

Certain events are flagged with `_mozaiks_hide: true` to prevent UI rendering:

- **UI_HIDDEN Triggers**: Exact-match content strings defined in workflow config `ui_hidden` map
- **AUTO_TOOL Deduplication**: Text messages from auto-tool agents (followed by tool_call with same content)
- **Hidden Agent Messages**: Messages from agents not in `visual_agents` list (filtered by `should_show_to_user()`)

---

## Event Envelope Format

All events follow a standard envelope structure:

```json
{
  "type": "chat.text",
  "data": {
    // Event-specific payload fields
  },
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "chat_id": "abc123xyz"
}
```

### Standard Envelope Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Event type (always prefixed with `chat.`) |
| `data` | object | Yes | Event-specific payload |
| `timestamp` | string | Yes | ISO 8601 UTC timestamp |
| `chat_id` | string | No | Associated chat session ID |

### Common Data Fields

Most events include these fields in the `data` payload:

| Field | Type | Description |
|-------|------|-------------|
| `sequence` | integer | Message sequence number (zero-based, incremented per event) |
| `agent` | string | Agent name that generated the event (e.g., "user", "assistant", "planner") |
| `content` | string | Primary message/output content |
| `is_visual` | boolean | True if agent is in workflow `visual_agents` list |
| `is_structured_capable` | boolean | True if agent supports structured outputs |
| `is_tool_agent` | boolean | True if agent has registered UI tools |
| `_mozaiks_hide` | boolean | If true, frontend should suppress rendering |

---

## Core Chat Events

### chat.text

Standard text message from an agent or user.

**Payload:**

```json
{
  "type": "chat.text",
  "data": {
    "kind": "text",
    "agent": "assistant",
    "content": "Here is the analysis you requested.",
    "sequence": 12,
    "is_visual": true,
    "is_structured_capable": false,
    "is_tool_agent": false
  },
  "timestamp": "2024-01-15T10:30:45.123Z",
  "chat_id": "chat_abc123"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `kind` | string | Always "text" |
| `agent` | string | Sender agent name (e.g., "user", "assistant", "planner") |
| `content` | string | Message text |
| `sequence` | integer | Message index for ordering |
| `is_visual` | boolean | Agent visibility flag |
| `is_structured_capable` | boolean | Structured output capability |
| `is_tool_agent` | boolean | UI tool registration flag |
| `_mozaiks_hide` | boolean | Suppression flag (optional) |

**Frontend Handling:**

- Append to message list
- Apply agent name normalization (lowercase, remove "agent" suffix)
- Filter based on `visual_agents` config
- Suppress if `_mozaiks_hide: true`
- Deduplicate fuzzy echoes of user input

---

### chat.print

Print/console output from agent execution (similar to `chat.text` but distinct semantic intent).

**Payload:**

```json
{
  "type": "chat.print",
  "data": {
    "kind": "print",
    "agent": "debugger",
    "content": "Variable x = 42",
    "sequence": 8
  },
  "timestamp": "2024-01-15T10:29:30.456Z"
}
```

**Fields:** Same as `chat.text`

**Frontend Handling:** Typically rendered as system/debug messages with distinct styling.

---

### chat.resume_boundary

Emitted after reconnection to indicate message replay completion.

**Payload:**

```json
{
  "type": "chat.resume_boundary",
  "data": {
    "kind": "resume_boundary",
    "total_messages": 45,
    "replayed_count": 12,
    "client_had": 33,
    "persisted_had": 45,
    "summary": "Replayed 12 messages (client had 33, server had 45)"
  },
  "timestamp": "2024-01-15T10:32:00.789Z",
  "chat_id": "chat_abc123"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `total_messages` | integer | Total persisted messages |
| `replayed_count` | integer | Number of messages re-emitted |
| `client_had` | integer | Client's last_sequence value |
| `persisted_had` | integer | Server's highest sequence |
| `summary` | string | Human-readable summary |

**Frontend Handling:**

- Display summary notification (optional)
- Clear reconnection spinner
- Resume normal message flow

---

## Tool Execution Events

### chat.tool_call

Agent invokes a tool (native AG2 or UI tool).

**Payload (Native Tool):**

```json
{
  "type": "chat.tool_call",
  "data": {
    "kind": "tool_call",
    "tool_name": "fetch_user_profile",
    "tool_call_id": "call_xyz789",
    "agent": "assistant",
    "arguments": {
      "user_id": "12345"
    },
    "awaiting_response": false,
    "sequence": 15
  },
  "timestamp": "2024-01-15T10:31:00.123Z"
}
```

**Payload (UI Tool with auto_tool mode):**

```json
{
  "type": "chat.tool_call",
  "data": {
    "kind": "tool_call",
    "tool_name": "WorkflowDAGEditor",
    "tool_call_id": "call_abc456",
    "component_type": "WorkflowDAGEditor",
    "agent": "workflow_builder",
    "payload": {
      "interaction_type": "auto_tool",
      "tool_args": {
        "WorkflowDAGEditor": {
          "workflow": {
            "name": "CustomerOnboarding",
            "agents": [...]
          }
        },
        "agent_message": "I've created a workflow for you."
      }
    },
    "display": "artifact",
    "awaiting_response": true,
    "sequence": 18
  },
  "timestamp": "2024-01-15T10:31:15.456Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Tool identifier |
| `tool_call_id` | string | Unique call ID for correlation |
| `agent` | string | Agent invoking the tool |
| `arguments` | object | Tool parameters (native tools) |
| `component_type` | string | UI component type (UI tools only) |
| `payload` | object | UI tool payload with `interaction_type`, `tool_args` |
| `display` | string | Display mode: "inline", "artifact", "modal" |
| `awaiting_response` | boolean | True if expecting user interaction |
| `sequence` | integer | Event sequence |

**Frontend Handling:**

- **Native Tools**: Display tool call indicator (e.g., "🔧 Fetching user profile...")
- **UI Tools**: Extract payload, flatten nested structures (e.g., `tool_args.WorkflowDAGEditor` → top-level), render component via `DynamicUIHandler`
- **Auto-tool mode**: Display `agent_message` + component in artifact panel

**Payload Flattening & Nested Extraction (UI Tools):**

When `interaction_type: "auto_tool"`, the frontend performs **two-stage payload processing**:

**Stage 1: Flatten `tool_args`**

The backend sends UI tool payloads with arguments nested under `tool_args`:

```javascript
// Backend payload structure:
{
  interaction_type: "auto_tool",
  tool_args: {
    // All tool parameters here
  },
  agent_message: "...",
  // other metadata
}
```

The frontend first extracts `tool_args` and spreads it to the top level:

```javascript
const { tool_args, ...restPayload } = basePayload;
basePayload = { ...restPayload, ...tool_args };
```

**Stage 2: Extract Nested Pydantic Models**

For Pydantic structured outputs, the model name often becomes a key in `tool_args`. The frontend detects this pattern and promotes the nested content:

```javascript
// Before flattening (from backend):
{
  interaction_type: "auto_tool",
  tool_args: {
    WorkflowDAGEditor: {           // ← Pydantic model name
      workflow: { name: "...", agents: [...] }
    },
    agent_message: "Here's your workflow."
  }
}

// After Stage 1 (tool_args flattened):
{
  WorkflowDAGEditor: {
    workflow: { name: "...", agents: [...] }
  },
  agent_message: "Here's your workflow.",
  interaction_type: "auto_tool"
}

// After Stage 2 (nested model extracted):
{
  workflow: { name: "...", agents: [...] },  // ← Promoted to top level
  agent_message: "Here's your workflow.",
  interaction_type: "auto_tool"
}
```

**Implementation** (`ChatPage.js`):

```javascript
if (basePayload.interaction_type === 'auto_tool' && basePayload.tool_args) {
  const { tool_args, ...restPayload } = basePayload;
  
  // Check for nested Pydantic model (key matching component_type)
  const nestedKey = Object.keys(tool_args).find(key => 
    key === componentType && typeof tool_args[key] === 'object'
  );
  
  if (nestedKey) {
    // Extract nested model content
    const { [nestedKey]: nestedContent, ...otherToolArgs } = tool_args;
    basePayload = {
      ...restPayload,
      ...nestedContent,      // Spread nested model fields
      ...otherToolArgs       // Preserve siblings (agent_message, etc.)
    };
  } else {
    // Standard flattening (no nested model)
    basePayload = { ...restPayload, ...tool_args };
  }
}
```

---

### chat.tool_response

Result of tool execution (success or failure).

**Payload:**

```json
{
  "type": "chat.tool_response",
  "data": {
    "kind": "tool_response",
    "tool_call_id": "call_xyz789",
    "tool_name": "fetch_user_profile",
    "content": "{\"user_id\": \"12345\", \"name\": \"Alice\", \"email\": \"alice@example.com\"}",
    "success": true,
    "sequence": 16
  },
  "timestamp": "2024-01-15T10:31:02.789Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `tool_call_id` | string | Correlation ID from `chat.tool_call` |
| `tool_name` | string | Tool identifier |
| `content` | string | Response data (often JSON-serialized) |
| `success` | boolean | True if execution succeeded |
| `sequence` | integer | Event sequence |

**Frontend Handling:**

- Match `tool_call_id` with prior `chat.tool_call` message
- Display success/failure indicator
- Parse `content` if JSON
- Update in-place or append as new message

---

### chat.structured_output_ready

Agent produced structured output (Pydantic model result).

**Payload:**

```json
{
  "type": "chat.structured_output_ready",
  "data": {
    "kind": "structured_output_ready",
    "agent": "data_analyzer",
    "structured_data": {
      "report_title": "Q4 Revenue Analysis",
      "key_metrics": {
        "total_revenue": 1500000,
        "growth_rate": 0.23
      }
    },
    "auto_tool_mode": false,
    "sequence": 20
  },
  "timestamp": "2024-01-15T10:32:10.123Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent` | string | Agent that produced the output |
| `structured_data` | object | Serialized Pydantic model result |
| `auto_tool_mode` | boolean | True if auto-tool invocation |
| `sequence` | integer | Event sequence |

**Frontend Handling:**

- Render structured data with appropriate UI (tables, cards, JSON viewers)
- If `auto_tool_mode: true`, correlate with `chat.tool_call` for UI tool invocation

---

## User Input Events

### chat.input_request

Request user input (simple prompt or UI component).

**Payload (Simple Input):**

```json
{
  "type": "chat.input_request",
  "data": {
    "kind": "input_request",
    "request_id": "input_req_123",
    "prompt": "Please enter your API key:",
    "chat_id": "chat_abc123"
  },
  "timestamp": "2024-01-15T10:33:00.456Z"
}
```

**Payload (UI Component Input):**

```json
{
  "type": "chat.input_request",
  "data": {
    "kind": "input_request",
    "request_id": "input_req_456",
    "prompt": "Configure API credentials",
    "component_type": "AgentAPIKeyInput",
    "ui_tool_id": "agent_api_key_input",
    "chat_id": "chat_abc123"
  },
  "timestamp": "2024-01-15T10:33:15.789Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Unique request ID for response correlation |
| `prompt` | string | Input prompt/question |
| `component_type` | string | UI component type (if applicable) |
| `ui_tool_id` | string | UI tool identifier (if applicable) |
| `chat_id` | string | Associated chat session |

**Frontend Handling:**

- **Simple Input**: Display input dialog/form with `prompt` text
- **UI Component**: Render custom component via `DynamicUIHandler.processUIEvent()`
- Store `request_id` for response correlation
- Submit response via `POST /api/user-input/submit` or WebSocket `user_input_response` message

---

### chat.input_ack

Acknowledgment that user input was received.

**Payload:**

```json
{
  "type": "chat.input_ack",
  "data": {
    "kind": "input_ack",
    "request_id": "input_req_123",
    "corr": "input_req_123"
  },
  "timestamp": "2024-01-15T10:33:05.123Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Correlation ID from `chat.input_request` |
| `corr` | string | Correlation ID (duplicate of `request_id`) |

**Frontend Handling:**

- Clear input dialog/spinner
- Resume normal message flow

---

### chat.input_timeout

User input request timed out.

**Payload:**

```json
{
  "type": "chat.input_timeout",
  "data": {
    "kind": "input_timeout",
    "request_id": "input_req_789",
    "message": "Input request timed out after 60 seconds."
  },
  "timestamp": "2024-01-15T10:34:00.456Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Correlation ID |
| `message` | string | Timeout reason |

**Frontend Handling:**

- Display timeout notification
- Clear input dialog
- Optionally allow retry

---

## UI Tool Events

### ui_tool_event

High-level event for UI component invocations (processed via `DynamicUIHandler`).

**Payload:**

```json
{
  "type": "ui_tool_event",
  "ui_tool_id": "WorkflowDAGEditor",
  "eventId": "evt_abc123",
  "workflow_name": "Generator",
  "display": "artifact",
  "payload": {
    "workflow": {
      "name": "CustomerOnboarding",
      "agents": [...]
    },
    "agent_message": "I've created a workflow for you.",
    "awaiting_response": true,
    "component_type": "WorkflowDAGEditor",
    "tool_name": "WorkflowDAGEditor"
  }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `ui_tool_id` | string | Component identifier |
| `eventId` | string | Event ID for response correlation |
| `workflow_name` | string | Workflow context |
| `display` | string | Display mode: "inline", "artifact", "modal" |
| `payload` | object | Component-specific data |

**Frontend Handling:**

- Lookup component in `DynamicUIHandler.componentRegistry`
- Render component with `payload` props
- If `awaiting_response: true`, provide submit callback
- Submit response via `POST /api/ui-tool/submit` with `event_id` and `response_data`

---

### component_action_ack

Acknowledgment of component action submission.

**Payload:**

```json
{
  "type": "chat.component_action_ack",
  "data": {
    "kind": "component_action_ack",
    "component_id": "workflow_selector",
    "action_type": "select",
    "applied": {
      "selected_workflow": "CustomerOnboarding"
    },
    "chat_id": "chat_abc123"
  },
  "timestamp": "2024-01-15T10:35:00.123Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `component_id` | string | Component identifier |
| `action_type` | string | Action performed (e.g., "select", "update") |
| `applied` | object | Context variable changes applied |
| `chat_id` | string | Associated chat session |

**Frontend Handling:**

- Update local component state
- Display success notification (optional)

---

## Workflow Lifecycle Events

### chat.run_start

Workflow execution started.

**Payload:**

```json
{
  "type": "chat.run_start",
  "data": {
    "kind": "run_start",
    "workflow_name": "Generator",
    "chat_id": "chat_abc123",
    "user_id": "user_456"
  },
  "timestamp": "2024-01-15T10:25:00.000Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | string | Workflow being executed |
| `chat_id` | string | Chat session ID |
| `user_id` | string | User initiating the workflow |

**Frontend Handling:**

- Display workflow start indicator
- Initialize message list
- Start initialization spinner (if configured)

---

### chat.run_complete

Workflow execution completed successfully.

**Payload:**

```json
{
  "type": "chat.run_complete",
  "data": {
    "kind": "run_complete",
    "workflow_name": "Generator",
    "chat_id": "chat_abc123",
    "result": "success",
    "total_turns": 8,
    "total_tokens": 4500
  },
  "timestamp": "2024-01-15T10:40:00.123Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | string | Completed workflow |
| `result` | string | Execution result ("success", "stopped", "error") |
| `total_turns` | integer | Number of agent turns |
| `total_tokens` | integer | Total token usage |

**Frontend Handling:**

- Display completion message
- Hide initialization spinner
- Enable new session button

---

### chat.select_speaker

AG2 group chat speaker selection event (indicates turn boundary). This event signals that a new agent has been selected to speak next, triggering thinking bubble UI in the frontend.

**Event Sources:**

1. **Native AG2 Events**: Emitted by AG2's `GroupChat` during normal speaker selection
2. **Synthetic Events**: Generated by runtime when AG2 doesn't emit `SelectSpeakerEvent` after resuming from paused state (e.g., after lifecycle tool execution)

**Payload (Native AG2):**

```json
{
  "type": "chat.select_speaker",
  "data": {
    "kind": "select_speaker",
    "agent": "planner",
    "selected_speaker": "planner",
    "sequence": 42
  },
  "timestamp": "2024-01-15T10:32:30.456Z"
}
```

**Payload (Synthetic):**

```json
{
  "type": "chat.select_speaker",
  "data": {
    "kind": "select_speaker",
    "agent": "planner",
    "source": "synthetic",
    "_synthetic": true,
    "sequence": 43
  },
  "timestamp": "2024-01-15T10:32:31.123Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent` | string | Agent selected to speak next |
| `selected_speaker` | string | (Deprecated, use `agent`) Legacy field for agent name |
| `source` | string | "synthetic" if runtime-generated, absent for AG2 native events |
| `_synthetic` | boolean | `true` if runtime-generated, absent for AG2 native events |
| `sequence` | integer | Event sequence number |

**Frontend Handling:**

- Display thinking bubble for `agent` (same logic for native and synthetic events)
- Mark turn boundary
- Remove previous thinking bubbles
- Collapse artifact panel (if open)

**Important**: Frontend should **not distinguish** between native and synthetic events. Both represent the same logical state transition (agent turn start) and should trigger identical UI behavior.

**See**: [Synthetic Events Documentation](../runtime/synthetic_events.md) for technical details on when and why the runtime generates synthetic speaker events.

---

## Error & System Events

### chat.error

Runtime error during workflow execution.

**Payload:**

```json
{
  "type": "chat.error",
  "data": {
    "kind": "error",
    "error_type": "ToolExecutionError",
    "message": "API rate limit exceeded",
    "details": {
      "tool_name": "fetch_user_profile",
      "retry_after": 60
    },
    "chat_id": "chat_abc123"
  },
  "timestamp": "2024-01-15T10:35:30.789Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `error_type` | string | Error classification |
| `message` | string | Human-readable error message |
| `details` | object | Additional error context |
| `chat_id` | string | Associated chat session |

**Frontend Handling:**

- Display error notification
- Append error message to chat
- Optionally provide retry action

---

### chat.usage_summary

Token usage summary for LLM calls.

**Payload:**

```json
{
  "type": "chat.usage_summary",
  "data": {
    "kind": "usage_summary",
    "total_tokens": 1250,
    "prompt_tokens": 800,
    "completion_tokens": 450,
    "cost": 0.025,
    "model": "gpt-4"
  },
  "timestamp": "2024-01-15T10:36:00.123Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `total_tokens` | integer | Total tokens consumed |
| `prompt_tokens` | integer | Prompt tokens |
| `completion_tokens` | integer | Completion tokens |
| `cost` | number | Estimated cost in USD (optional) |
| `model` | string | LLM model used |

**Frontend Handling:**

- Display token usage indicator (optional)
- Update wallet balance display
- Trigger low-balance warnings

---

### tool_progress

Progress update for long-running tool execution.

**Payload:**

```json
{
  "type": "tool_progress",
  "data": {
    "kind": "tool_progress",
    "tool_name": "generate_report",
    "tool_call_id": "call_xyz123",
    "progress_percent": 65,
    "status_message": "Processing data (step 3 of 5)"
  },
  "timestamp": "2024-01-15T10:37:00.456Z"
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Tool identifier |
| `tool_call_id` | string | Correlation ID |
| `progress_percent` | integer | Progress percentage (0-100) |
| `status_message` | string | Status description |

**Frontend Handling:**

- Update progress bar for matching `tool_call_id`
- Display status message
- Clear on completion (`progress_percent: 100`)

---

### token_warning

Token balance warning.

**Payload:**

```json
{
  "type": "token_warning",
  "data": {
    "kind": "token_warning",
    "remaining_tokens": 500,
    "threshold": 1000,
    "message": "Approaching token limit"
  },
  "timestamp": "2024-01-15T10:38:00.789Z"
}
```

**Frontend Handling:**

- Display warning banner
- Suggest upgrade or token purchase

---

### token_exhausted

Token balance exhausted.

**Payload:**

```json
{
  "type": "token_exhausted",
  "data": {
    "kind": "token_exhausted",
    "remaining_tokens": 0,
    "message": "Token limit reached. Upgrade or start a new session."
  },
  "timestamp": "2024-01-15T10:39:00.123Z"
}
```

**Frontend Handling:**

- Set `tokensExhausted` state to `true`
- Display upgrade prompt
- Disable message input

---

## Event Sequences

### Typical Workflow Execution Sequence

```
1. chat.run_start
   ↓
2. chat.text (agent: "planner")
   ↓
3. chat.select_speaker (selected: "analyst")
   ↓
4. chat.tool_call (tool: "fetch_data")
   ↓
5. tool_progress (progress: 50%)
   ↓
6. tool_progress (progress: 100%)
   ↓
7. chat.tool_response (success: true)
   ↓
8. chat.text (agent: "analyst")
   ↓
9. chat.select_speaker (selected: "presenter")
   ↓
10. chat.structured_output_ready (structured_data: {...})
    ↓
11. chat.usage_summary (total_tokens: 1250)
    ↓
12. chat.run_complete (result: "success")
```

---

### User Input Request Flow

```
1. chat.input_request (request_id: "req_123", prompt: "Enter API key")
   ↓
2. [User submits input via WebSocket or HTTP]
   ↓
3. chat.input_ack (request_id: "req_123")
   ↓
4. [Workflow resumes]
```

---

### UI Tool Auto-Tool Flow

```
1. chat.tool_call (tool: "WorkflowDAGEditor", interaction_type: "auto_tool")
   ↓
2. [Frontend renders component in artifact panel]
   ↓
3. [User interacts with component]
   ↓
4. [Frontend submits response via POST /api/ui-tool/submit]
   ↓
5. [Workflow processes response]
```

---

### Reconnection & Resume Flow

```
1. WebSocket connection established
   ↓
2. Client sends last_sequence (e.g., 33)
   ↓
3. chat.text (index: 34) [Replay begins]
   ↓
4. chat.text (index: 35)
   ↓
5. ...
   ↓
6. chat.text (index: 45)
   ↓
7. chat.resume_boundary (replayed_count: 12, client_had: 33, persisted_had: 45)
   ↓
8. [New real-time messages follow]
```

---

### Error Handling Flow

```
1. chat.tool_call (tool: "external_api")
   ↓
2. [Tool execution fails]
   ↓
3. chat.error (error_type: "ToolExecutionError", message: "API timeout")
   ↓
4. [Workflow handles error, may retry or stop]
   ↓
5. chat.run_complete (result: "error") [If unrecoverable]
```

---

## Frontend Integration

### ChatPage.js Event Handling

The `ChatPage.js` component processes WebSocket events via `handleWebSocketMessage()`:

```javascript
const handleWebSocketMessage = (event) => {
  const { type, data } = event;
  
  switch (type) {
    case 'chat.text':
      // Append message to chat
      setMessages(prev => [...prev, {
        id: `msg-${Date.now()}`,
        sender: data.agent === 'user' ? 'user' : 'agent',
        content: data.content,
        agentName: extractAgentName(data)
      }]);
      break;
      
    case 'chat.tool_call':
      if (data.component_type) {
        // UI tool - render component
        dynamicUIHandler.processUIEvent({
          type: 'ui_tool_event',
          ui_tool_id: data.tool_name,
          eventId: data.tool_call_id,
          payload: data.payload
        });
      } else {
        // Native tool - display indicator
        setMessages(prev => [...prev, {
          id: data.tool_call_id,
          sender: 'system',
          content: `🔧 Tool Call: ${data.tool_name}`
        }]);
      }
      break;
      
    case 'chat.input_request':
      if (data.component_type) {
        // UI component input
        dynamicUIHandler.processUIEvent({
          type: 'user_input_request',
          data: {
            input_request_id: data.request_id,
            payload: {
              prompt: data.prompt,
              ui_tool_id: data.component_type
            }
          }
        });
      } else {
        // Simple input - show dialog
        setInputRequestId(data.request_id);
        setInputPrompt(data.prompt);
        setShowInputDialog(true);
      }
      break;
      
    case 'chat.error':
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        sender: 'system',
        content: `❌ Error: ${data.message}`
      }]);
      break;
      
    case 'chat.run_complete':
      setShowInitSpinner(false);
      setMessages(prev => [...prev, {
        id: `complete-${Date.now()}`,
        sender: 'system',
        content: '✅ Workflow completed'
      }]);
      break;
      
    // ... additional event handlers
  }
};
```

---

### DynamicUIHandler Integration

UI tool events are processed via `DynamicUIHandler.processUIEvent()`:

```javascript
// Event dispatched from ChatPage
dynamicUIHandler.processUIEvent({
  type: 'ui_tool_event',
  ui_tool_id: 'WorkflowDAGEditor',
  eventId: 'evt_abc123',
  workflow_name: 'Generator',
  display: 'artifact',
  payload: {
    workflow: { name: 'CustomerOnboarding', agents: [...] },
    agent_message: 'I created this workflow for you.',
    awaiting_response: true
  }
});

// DynamicUIHandler rendering
const Component = componentRegistry['WorkflowDAGEditor'];
return (
  <Component
    {...payload}
    onSubmit={(responseData) => {
      // Submit response
      fetch('/api/ui-tool/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: eventId,
          response_data: responseData
        })
      });
    }}
  />
);
```

---

### Agent Name Normalization

Frontend normalizes agent names for `visual_agents` filtering:

```javascript
function normalizeAgentName(name) {
  if (!name) return '';
  return name.toLowerCase()
    .replace('agent', '')
    .replace(/\s/g, '')
    .trim();
}

// Example:
// "PlannerAgent" → "planner"
// "Data Analyzer" → "dataanalyzer"
```

Backend applies same normalization in `should_show_to_user()`:

```python
def normalize_agent(name):
    if not name:
        return ''
    return str(name).lower().replace('agent', '').replace(' ', '').strip()
```

---

### Message Suppression Logic

Frontend suppresses messages based on:

1. **_mozaiks_hide flag**: If `data._mozaiks_hide === true`, skip rendering
2. **visual_agents filtering**: Only show messages from agents in workflow `visual_agents` list
3. **Fuzzy echo detection**: Suppress assistant messages that closely match recent user input

Example fuzzy echo check:

```javascript
const normUser = lastUserMsg.content.toLowerCase().trim();
const normContent = content.toLowerCase().trim();
const lengthDiff = Math.abs(normUser.length - normContent.length);
const containsRel = normUser.includes(normContent) || normContent.includes(normUser);
const smallDiff = lengthDiff <= 3; // Allow small typos

if (normUser === normContent || (containsRel && smallDiff)) {
  console.log('[PIPELINE] suppressing assistant echo');
  return; // Skip rendering
}
```

---

### Artifact Panel Lifecycle

The artifact panel displays UI components in a side panel. Lifecycle:

1. **Open**: On `chat.tool_call` with `display: "artifact"`, set `isSidePanelOpen: true`
2. **Update**: On subsequent artifact events, update `currentArtifactMessages`
3. **Collapse**: On `chat.select_speaker` (turn boundary), close panel and clear cache
4. **Restore**: On reconnection, fetch `last_artifact` from session metadata and restore panel state

Artifact persistence:

```javascript
// Save to localStorage
localStorage.setItem(
  `mozaiks.current_artifact.${chatId}`,
  JSON.stringify({ eventId, component, payload })
);

// Restore on reconnection
const savedArtifact = JSON.parse(
  localStorage.getItem(`mozaiks.current_artifact.${chatId}`) || 'null'
);
if (savedArtifact) {
  dynamicUIHandler.processUIEvent(savedArtifact);
  setIsSidePanelOpen(true);
}
```

---

### Heartbeat & Connection Health

WebSocket connection health maintained via heartbeat:

**Backend** (`SimpleTransport`):
- Heartbeat task started on connection: `_heartbeat_interval = 120` seconds
- Sends periodic ping frames to keep connection alive
- Terminates heartbeat on disconnect

**Frontend** (`useChatSession` hook):
- Monitors `readyState` for CLOSED (3) or CLOSING (2)
- Attempts reconnection with exponential backoff
- Sends `last_sequence` on reconnect to trigger message replay

---

### Token Balance Integration

Token events trigger wallet UI updates:

```javascript
// On token_warning
useEffect(() => {
  if (event.type === 'token_warning') {
    setShowLowBalanceWarning(true);
    setRemainingTokens(event.data.remaining_tokens);
  }
}, [event]);

// On token_exhausted
useEffect(() => {
  if (event.type === 'token_exhausted') {
    setTokensExhausted(true);
    setMessageInputDisabled(true);
    setMessages(prev => [...prev, {
      id: `exhaust-${Date.now()}`,
      sender: 'system',
      content: '⛽ Token limit reached. Upgrade or start a new session.'
    }]);
  }
}, [event]);
```

---

## Related Documentation

- **[Transport & Streaming Guide](../runtime/transport_streaming.md)**: WebSocket transport implementation, connection lifecycle, message queuing
- **[API Reference](./api_reference.md)**: REST endpoints for event submission, chat management, workflow discovery
- **[Persistence & Resume](../runtime/persistence_resume.md)**: Message persistence, session recovery, resume boundary logic
- **[AG2 WebSocket Streaming](../AG2_WEBSOCKET_STREAMING_GUIDE.md)**: AG2-native event streaming, event type mapping
- **[Dynamic UI Guide](../DYNAMIC_UI_COMPLETE_GUIDE.md)**: UI tool system, component registration, payload schemas
- **[Agent-Generated UI](../AGENT_GENERATED_UI_GUIDE.md)**: Structured output processing, auto-tool mode, artifact rendering

---

## Implementation Files

- **Event Dispatcher**: `core/events/unified_event_dispatcher.py` - Event transformation, namespace mapping, suppression logic
- **Event Serialization**: `core/events/event_serialization.py` - AG2 event → dict conversion
- **Transport**: `core/transport/simple_transport.py` - WebSocket broadcasting, message queuing, heartbeat
- **Frontend Handler**: `ChatUI/src/pages/ChatPage.js` - Event routing, message rendering, UI updates
- **Dynamic UI**: `ChatUI/src/core/DynamicUIHandler.js` - UI tool event processing, component rendering

---

**Last Updated**: 2024-01-15  
**Version**: 1.0  
**Maintainer**: MozaiksAI Runtime Team
