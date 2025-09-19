## WebSocket Payload Contract (Backend ↔ ChatUI)

This document enumerates the events currently emitted by `SimpleTransport.send_event_to_ui` and how the ChatUI expects to consume them, enabling schema validation without a running browser UI.

### Core Event Namespace Mapping

Backend internal `kind` values are mapped to external `type` fields:

| kind            | type                | Purpose                                |
|-----------------|---------------------|----------------------------------------|
| text            | chat.text           | Standard agent/user message            |
| print           | chat.print          | Low-importance logging / debug line    |
| input_request   | chat.input_request  | Frontend should render input widget    |
| input_ack       | chat.input_ack      | Ack that input was accepted            |
| input_timeout   | chat.input_timeout  | Indicates request window expired       |
| select_speaker  | chat.select_speaker | Agent turn change notification         |
| resume_boundary | chat.resume_boundary| Marker during resume reconstruction    |
| usage_summary   | chat.usage_summary  | Aggregate token + cost summary         |
| run_complete    | chat.run_complete   | Conversation/pattern finished          |
| error           | chat.error          | Recoverable transport/workflow errors  |
| tool_call       | chat.tool_call      | UI tool invocation (interactive)       |
| tool_response   | chat.tool_response  | UI tool response (echoed / persisted)  |

### chat.text (from `send_chat_message` or forwarded TextEvent)
```jsonc
{
  "type": "chat.text",
  "data": {
    "chat_id": "<string>",
    "agent": "<AgentName>",
    "content": "<message string>",
    "timestamp": "ISO-8601",
    "metadata": { "sequence": <int>, "source": "ag2_textevent" } // optional
  }
}
```
ChatUI maps this to a `ChatMessage` component. `agent` becomes `agentName`; user messages originate from WS client path or persisted replay.

### chat.tool_call
Emitted by `send_ui_tool_event`.
```jsonc
{
  "type": "chat.tool_call",
  "data": {
    "kind": "tool_call",            // Original kind preserved inside data
    "tool_name": "<registered tool>",
    "component_type": "<UI component>",
    "awaiting_response": true,
    "payload": {                      // Arbitrary workflow payload
       "workflow_name": "Generator",
       "component_type": "ActionPlan", // Redundant but UI falls back
       // ... other tool-specific fields
    },
    "corr": "<event id>",            // Correlation id for response
    "sequence": <int>
  },
  "timestamp": "ISO-8601"
}
```
UI Logic:
1. Transport layer (not shown here) should wrap event into an object passed to `UIToolRenderer` like:
```js
{
  ui_tool_id: data.tool_name,
  eventId: data.corr,
  workflow_name: data.payload?.workflow_name,
  payload: data.payload
}
```
2. `EventDispatcher.handleEvent()` extracts `workflowName` and `componentType = payload.component_type || ui_tool_id`.
3. `WorkflowUIRouter` dynamically imports: `../workflows/${workflowName}/components/index.js` and expects the named export matching `componentType`.

### chat.tool_response
Echoed back when UI responds (future usage). Must include:
```jsonc
{
  "type": "chat.tool_response",
  "data": {
    "corr": "<event id>",
    "tool_name": "<tool>",
    "status": "ok|error",
    "payload": { /* response data */ }
  }
}
```

### chat.input_request
```jsonc
{
  "type": "chat.input_request",
  "data": {
    "request_id": "<uuid>",
    "chat_id": "<chat>",
    "agent": "<requesting agent>",
    "prompt": "<text shown to user>",
    "fields": [ {"name":"value","type":"string"} ], // optional structured form
    "timeout_sec": 300
  }
}
```
Frontend should map this to F5 `UserInputRequest` (core fallback) via the same dynamic mechanism: treat as a UI tool with `component_type: 'UserInputRequest'` when no specific workflow component exists.

### Contract Gaps / TODO
1. Explicit wrapper that converts raw WebSocket JSON into the structure expected by `UIToolRenderer` (currently implied). A thin adapter layer should live near the WebSocket client.
2. Standard error envelope for tool failures (e.g. `chat.tool_call_error`). Not yet implemented.
3. Structured output flag: backend adds `has_structured_outputs` to `text/print` events, UI could surface a toggle or badge (currently only renderer-level detection).

### Validation Strategy (Headless)
Create a pytest that:
1. Opens WebSocket
2. Triggers a minimal workflow producing one `chat.tool_call` and one `chat.text`
3. Validates each JSON frame against the required keys above.

---
Generated automatically to align ChatUI expectations with backend transport as of current refactor.