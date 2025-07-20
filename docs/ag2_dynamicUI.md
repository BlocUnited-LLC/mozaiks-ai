---

# AG2 Dynamic UI: Workflow-Agnostic Agent Tools and Events

## Overview
In modern agent-based applications (like AG2), **tool calls** and **events** work together to enable dynamic, interactive workflows. To maximize modularity and flexibility, use workflow-agnostic event handling, allowing each workflow to register its own React components for the frontend.

---

## What is a Tool Call?
- A **tool call** is a backend function invoked by an agent (LLM) to perform an action (e.g., request API key, run a query).
- Tool calls are logic-only—they do not directly affect the frontend UI.

---

## What is an Event?
- An **event** is a standardized message sent from the backend to the frontend to trigger UI updates or collect user input.
- Events include a `toolId` (or `componentId`), a `payloadSchema`, and a `workflowType`.
- The backend does not need to know about specific React components—just the event type and payload.

---

## How Do They Work Together?
1. **Agent calls a tool** to request an action (e.g., needs an API key).
2. **Backend processes the tool call** and emits a workflow-agnostic event with `toolId` and payload.
3. **Frontend receives the event** and uses the registry to render the correct React component.
4. **User interacts with the UI**, and the frontend sends the result back to the backend.
5. **Backend stores the result** and continues the workflow.

## Visual Diagram
```
Agent (LLM)
   |
   |-- tool call --> Backend Logic
   |                    |
   |                    |-- workflow-agnostic event --> Frontend UI Dispatcher
   |                                              |
   |<-- user input/result -- event ----------------|
   |
Workflow continues...
```

---

## 1. Frontend: UI Tool Registry & Event Dispatcher

**Registry Setup:**
```js
// src/uiToolRegistry.js
const registry = {};
export function registerUiTool(toolId, component) {
  registry[toolId] = component;
}
export function getUiToolComponent(toolId) {
  return registry[toolId];
}
export default registry;
```

**Event Dispatcher:**
```js
// src/eventDispatcher.js
import React from 'react';
import { getUiToolComponent } from './uiToolRegistry';
export function handleEvent(event) {
  const { toolId, payload } = event;
  const Component = getUiToolComponent(toolId);
  if (Component) {
    return <Component {...payload} />;
  }
  return null;
}
```

**Workflow Component Example:**
```js
// src/workflows/payment_workflow/PaymentApiKeyInput.js
import React from 'react';
export default function PaymentApiKeyInput({ application }) {
  return (
    <div>
      <h3>Enter API Key for {application}</h3>
      <input type="text" placeholder="API Key" />
      {/* Add submit logic as needed */}
    </div>
  );
}
```

**Workflow Registration:**
```js
// src/workflows/payment_workflow/index.js
import PaymentApiKeyInput from './PaymentApiKeyInput';
import { registerUiTool } from '../../uiToolRegistry';
registerUiTool('api_key_input', PaymentApiKeyInput);
```

**How it works:**
- Each workflow registers its React components with the central registry.
- The event dispatcher receives backend events, looks up the correct component by `toolId`, and renders it with the event payload.
- This pattern is workflow-agnostic and supports dynamic, modular UI integration for any workflow.

---

## 2. Backend: AG2 Agent/Event Emission Logic

### Tool Registration
- In AG2, tools are registered with the agent at startup or workflow initialization.
- Each tool is defined as a Python function/class and added to the agent’s tool registry.
- Example:
  ```python
  from ag2.agent import ConversableAgent
  from my_tools import request_api_key

  agent = ConversableAgent(...)
  agent.register_tool(request_api_key)
  # Optionally register more tools
  ```

### Prompt Engineering (System Message)
- The agent’s system prompt should describe available tools and their purpose, so the LLM knows when to call them.
- Example system prompt:
  > "You can call the `request_api_key` tool whenever you need the user to provide an API key for a service."
- This prompt is set when initializing the agent or workflow.

---

### How Does a Tool Trigger an Event?
1. **Agent (LLM) decides to call a tool** (e.g., `request_api_key`) based on the system prompt and user input.
2. **Tool function executes** and, as part of its logic, emits an event to the frontend (see Backend Template section below).
   - The event emission typically happens inside the tool function using the agent’s channel/transport.
   - Example:
     ```python
     async def request_api_key(channel, application, description=None, workflow_type=None):
         event = {
             "type": "ui_tool",
             "toolId": "api_key_input",  # Must match frontend registry
             "payload": {
                 "application": application,
                 "description": description or f"Enter your {application} API key to continue."
             },
             "workflowType": workflow_type or "default"
         }
         await channel.send_event(event)  # Send event to frontend via transport (WebSocket)
     ```
3. **Frontend receives the event** and renders the appropriate UI component.
4. **User input is sent back to the backend**, which resumes the workflow.

**Where Does the Event Emission Happen?**
- The event emission happens inside the tool function itself, after it is called by the agent.
- The agent’s channel (or IOStream) is used to send the event to the frontend via the transport layer (WebSocket).
- This pattern keeps the tool logic modular and workflow-agnostic.

---

## End-to-End Flow

1. **Agent calls a tool** to request an action (e.g., needs an API key).
2. **Backend processes the tool call** and emits a workflow-agnostic event with `toolId` and payload.
3. **Frontend receives the event** and uses the registry to render the correct React component.
4. **User interacts with the UI**, and the frontend sends the result back to the backend.
5. **Backend stores the result** and continues the workflow.

---

## Example Directory Structure

Here’s a sample project structure illustrating workflow-agnostic event handling and dynamic UI component registration:

```
src/
  uiToolRegistry.js         # Central registry for UI tools/components
  eventDispatcher.js        # Handles incoming events and renders components
  workflows/
    payment_workflow/
      PaymentApiKeyInput.js # React component for API key input
      index.js              # Registers PaymentApiKeyInput with uiToolRegistry
    file_manager_workflow/
      FileManagerComponent.js # React component for file manager
      index.js                # Registers FileManagerComponent with uiToolRegistry
  agents/
    ...                     # Agent logic and tool calls
  core/
    ...                     # Backend event emission logic
  ...
```

---

## Why Use This Pattern?
- **Modular:** Workflows can add/remove their own components without touching the core event system.
- **Scalable:** New workflows just register their components; the event system remains unchanged.
- **Workflow-Agnostic:** The event dispatcher is generic and only cares about `toolId`.

---

## Summary
- Tool calls = backend logic
- Events = workflow-agnostic triggers for UI components
- React components are registered per workflow and mapped by `toolId`
- This pattern enables scalable, interactive agent workflows with maximum modularity and flexibility
