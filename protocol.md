# WebSocket Protocol (AG2 Aligned)

Progress Snapshot 2025-08-25 (post B8):
Backend now emits namespaced `chat.*` event types AND (while `emit_legacy_types=True`) legacy un-namespaced duplicates for migration. `input_request` events include `corr=request_id` (partial correlation rollout). Legacy emission will be disabled after UI fully adopts namespaced types.

Legend of backlog cross refs: B8 (namespace alignment), B9 (full event set), B10 (corr propagation), B11 (resume handshake), P3/P4 (spec update pass). See `analysis.md` progress table.

Authoritative, minimal message contract between backend and ChatUI.

## Outbound (Server -> Client)

| Type | When | Core Fields |
|------|------|-------------|
| chat.resume_boundary | After `GroupChatResumeEvent` (only on resume) | {type, chat_id} |
| chat.select_speaker | On `SelectSpeakerEvent` | {type, chat_id, agent, seq} |
| chat.print | On `PrintEvent` token/partial text | {type, chat_id, agent, content, seq, corr?} | 
| chat.text | On `TextEvent` finalized agent turn | {type, chat_id, agent, content, seq} |
| chat.input_request | On `InputRequestEvent` | {type, chat_id, request_id, prompt, seq, corr} |
| chat.input_timeout | Synthetic (timeout) | {type, chat_id, request_id, timeout_seconds, seq, corr} |
| chat.input_ack | After user reply accepted | {type, chat_id, request_id, seq, corr} |
| chat.tool_call | On `FunctionCallEvent`/`ToolCallEvent` requiring UI | {type, chat_id, tool_name, component_type, awaiting_response, payload, seq, corr} |
| chat.tool_response | On `FunctionResponseEvent`/`ToolResponseEvent` | {type, chat_id, tool_name, content, success, seq, corr} |
| chat.tool_progress | For long-running tools | {type, chat_id, tool_name, progress_percent, status_message, seq, corr} |
| chat.usage_summary | On `UsageSummaryEvent` | {type, chat_id, total_tokens, prompt_tokens, completion_tokens, cost? , seq} |
| chat.run_complete | On `RunCompletionEvent` | {type, chat_id, reason, seq} |
| chat.error | On `ErrorEvent` | {type, chat_id, message, seq} |

Notes:
- `seq` starts at 1 AFTER resume boundary for live events.
- `corr` used when a message responds to a prior request/tool call.
- Stream chunks do not increment conversation turn logically; client may group by contiguous same agent before a `chat.text`.

## Inbound (Client -> Server)

| Type | Purpose | Payload |
|------|---------|---------|
| user.input.submit | Provide text for an `InputRequestEvent` | {type, chat_id, request_id, text, last_client_seq} |
| inline_component.result | Return inline UI tool interaction | {type, chat_id, corr, data} |
| artifact_patch | Patch artifact component (optional progressive update) | {type, chat_id, corr, patch[]} |
| client.resume | Reconnect & request replay | {type, chat_id, lastClientIndex} |

## Correlation Rules
- `request_id` (input) or tool event id (UI tool) becomes `corr` on subsequent responses.
- Client must echo latest received `seq` in submissions for optional at-least-once replay safety.

## Replay
1. Client sends `client.resume` with `lastClientIndex` (the 0-based index of the last fully received/persisted message; send 0 or omit if none).
2. Server replays any persisted envelopes with sequence index > lastClientIndex as their original outbound types (mark each with `replay:true`).
3. Server emits `chat.resume_boundary` (if applicable) then resumes live event emission.

## Error Handling
- Malformed inbound → send `chat.error` (no termination unless fatal).
- Unknown `request_id` → `chat.error` with code `UNKNOWN_REQUEST`.

## Backpressure & Ordering
- Events are sent FIFO per chat session.
- No guarantee of strict ordering across different chat sessions (isolation required client-side by `chat_id`).
- Client should treat out-of-order seq as trigger to request replay (`client.resume`).

## Extension Points
- ✅ `chat.tool_progress` for long-running tools (X1: implemented).
- Future: `chat.metrics` summary events (latency, tokens) per turn.

## Production Status (2025-08-26)
✅ **PRODUCTION READY** - Complete implementation aligned with AG2 `a_run_group_chat`:

**Core Protocol:**
- All chat.* namespace events with proper correlation IDs
- WebSocket resume handshake with sequence tracking  
- Client-side sequence gap detection and recovery
- Schema validation with structured error responses
- Agent message flow: tool print() → chat.text → chat display

**Frontend-Aware Agents:**
- UI tool events integrated with React component chain
- WebSocket-first input submission with REST fallback
- Tool call/response events with correlation tracking  
- Workflow-agnostic component routing via WorkflowUIRouter
- Complete message flow: agent message + UI component rendering

**Interactive Tool Integration:**
- Generator workflow tools (`request_api_key`, `generate_and_download`) production-ready
- React components (`AgentAPIKeyInput`, `FileDownloadCenter`) aligned with chat.* protocol
- Agent prints message → chat.text → UI component renders → user response flows back
- Tool correlation IDs maintain request-response relationships

**Persistence & Resume:**
- Full AG2 event replay on reconnection with chat.resume_boundary
- Sequence-based gap detection with localStorage persistence
- Chat state preservation across disconnects
- Agent messages persisted, streaming chunks filtered

**Clean Architecture:**
- Only AG2 `a_run_group_chat` as runtime entry point
- Legacy paths completely removed (ag2_iostream, MessageFilter, future-based inputs)
- Production chat.* namespace events only
- Workflow-agnostic core with YAML-driven configuration

This protocol intentionally mirrors AG2 official events; no private hooks used.

## Complete Workflow Integration Example

**Generator Workflow Tools → UI Components Flow:**

1. **APIKey Agent** calls `request_api_key(service="openai", description="I need your API key...")`
   - Tool executes: `print("I need your OpenAI API key to proceed...")` 
   - Emits: `PrintEvent` → `chat.text` → Agent message displays in chat
  - Tool executes: `await use_ui_tool(tool_id="AgentAPIKeyInput", payload={...}, chat_id=..., workflow_name=...)`
   - Emits: `ToolCallEvent` → `chat.tool_call` → UI component renders below message
   - User interacts → Component calls `onResponse()` → Tool receives via `wait_for_ui_tool_response()`

2. **UserFeedback Agent** calls `generate_and_download(description="Files are ready...")`
   - Tool executes: `print("I'm creating your workflow files. Please use the download center below.")`
   - Emits: `PrintEvent` → `chat.text` → Agent message displays in chat  
  - Tool executes: `await use_ui_tool(tool_id="FileDownloadCenter", payload={files: [...]}, chat_id=..., workflow_name=..., display="artifact")`
   - Emits: `ToolCallEvent` → `chat.tool_call` → Download center renders below message
   - User downloads → Component provides completion signal → Tool finishes

**Result:** Agent messages appear in chat alongside interactive UI components, creating seamless conversational experience with rich interactions.

## Error Codes Table

**chat.error Event Error Codes:**

| Code | Description | Recovery Action | Typical Cause |
|------|-------------|----------------|---------------|
| `SCHEMA_VALIDATION_FAILED` | Inbound message failed validation | Send properly formatted message | Invalid WebSocket message structure |
| `INPUT_REQUEST_NOT_FOUND` | Input request ID not found | Check request ID or start new request | Stale/expired input request |
| `TOOL_EXECUTION_ERROR` | Tool execution failed | Retry or check tool parameters | Tool runtime error or invalid parameters |
| `UI_TOOL_TIMEOUT` | UI interaction timed out | Retry or use different approach | User didn't respond within timeout |
| `RESUME_FAILED` | Resume operation failed | Reconnect or start fresh session | Invalid sequence or corrupted state |
| `PERSISTENCE_ERROR` | Database operation failed | Retry operation | MongoDB connection or write failure |
| `WORKFLOW_NOT_FOUND` | Specified workflow doesn't exist | Check workflow name or use default | Typo in workflow name |
| `AGENT_INITIALIZATION_FAILED` | Agent creation failed | Check configuration | Invalid agent config or missing dependencies |
| `TRANSPORT_ERROR` | WebSocket/transport failure | Reconnect | Network issues or server restart |
| `RATE_LIMIT_EXCEEDED` | Too many requests | Wait and retry | Client sending requests too quickly |

**Usage in chat.error events:**
```json
{
  "type": "chat.error",
  "data": {
    "message": "Human readable error description",
    "error_code": "SCHEMA_VALIDATION_FAILED",
    "details": { "field": "type", "expected": "string" },
    "recoverable": true
  }
}
```
