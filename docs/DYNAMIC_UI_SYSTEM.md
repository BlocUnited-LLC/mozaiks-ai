# Dynamic UI Component System - Technical Architecture

## Overview

The MozaiksAI Dynamic UI System enables AG2 (AutoGen) agents to dynamically request and control React components in the frontend without hardcoding. This document explains the complete technical architecture, component interaction patterns, and response handling mechanisms.

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DYNAMIC UI SYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│  AG2 Agents    │  Transport    │  Frontend     │  Components │
│  ┌─────────┐   │  ┌─────────┐  │  ┌─────────┐  │  ┌─────────┐ │
│  │ Agent   │◄──┤  │WebSocket│◄─┤  │Event    │◄─┤  │Component│ │
│  │Tools    │   │  │   SSE   │  │  │Processor│  │  │Registry │ │
│  └─────────┘   │  └─────────┘  │  └─────────┘  │  └─────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

1. **Component Discovery System**: Scans workflow directories for UI components
2. **AG2 Tool Integration**: Agents request UI via tool calls
3. **Event Transport Layer**: WebSocket/SSE for real-time communication
4. **Dynamic Component Loader**: Frontend resolves and renders components
5. **Response Handling System**: Captures user interactions and sends back to AG2

## 📁 Directory Structure

```
workflows/
├── Generator/                          # Workflow name
│   ├── workflow.json                   # Workflow configuration
│   ├── components.json                 # Auto-generated manifest
│   ├── Components/
│   │   ├── Artifacts/                  # Full-featured components
│   │   │   └── FileDownloadCenter.js   # Artifact component
│   │   └── Inline/                     # Lightweight components
│   │       └── AgentAPIKeyInput.js     # Inline component
│   └── GroupchatTools/                 # Backend tools for this workflow
│       ├── db_manager.py               # API key storage
│       └── file_manager.py             # File operations
```

## 🔧 Component Types

### 1. Inline Components
**Purpose**: Lightweight UI elements embedded in chat flow
**Location**: `workflows/{workflow}/Components/Inline/`
**Use Case**: Forms, inputs, simple interactions

```javascript
// Example: AgentAPIKeyInput.js
const AgentAPIKeyInput = ({ 
  agentId, 
  service,
  onAction,    // ← Key: Response handler
  // ... other props
}) => {
  const handleSubmit = async (e) => {
    await onAction?.({
      type: 'api_key_submit',
      agentId,
      data: { service, apiKey, maskedKey }
    });
  };
  // ... component logic
};
```

### 2. Artifact Components
**Purpose**: Full-featured components in right panel
**Location**: `workflows/{workflow}/Components/Artifacts/`
**Use Case**: File downloads, code editors, complex interactions

```javascript
// Example: FileDownloadCenter.js
const FileDownloadCenter = ({ 
  files,
  onDownload,  // ← Key: Response handler
  title
}) => {
  const handleDownloadFile = async (file) => {
    await onDownload?.(file);
  };
  // ... component logic
};
```

## 🎯 How AG2 Agents Request UI Components

### 1. Tool Registration

AG2 agents get UI tools registered automatically:

```python
# In groupchat setup
from core.ui.simple_ui_tools import route_to_inline_component, route_to_artifact_component

# Tools available to agents
tools = [
    route_to_inline_component,
    route_to_artifact_component,
    # ... other tools
]
```

### 2. Agent Tool Call Example

```python
# Agent requests API key input (inline component)
await route_to_inline_component(
    content="I need your OpenAI API key to continue",
    component_name="AgentAPIKeyInput",
    component_data={
        "service": "OpenAI",
        "agentId": "ContentGeneratorAgent",
        "description": "Required for generating content with GPT models"
    }
)

# Agent creates file download artifact
await route_to_artifact_component(
    title="Generated Files Ready",
    content="Your files have been generated and are ready for download",
    component_name="FileDownloadCenter",
    component_data={
        "files": [
            {"name": "app.py", "size": 1024, "content": "..."},
            {"name": "config.json", "size": 512, "content": "..."}
        ]
    }
)
```

### 3. Event Flow

```python
# 1. AG2 agent calls tool
agent_reply = await agent.a_generate_reply(messages)

# 2. Tool creates Simple Event
event = create_inline_component_route(content, component_name, component_data)

# 3. Event sent via transport
await communication_channel.send_event(
    event_type="route_to_chat",
    data=event.data
)

# 4. Frontend receives and processes
{
  "type": "route_to_chat",
  "data": {
    "content": "I need your OpenAI API key",
    "component_name": "AgentAPIKeyInput",
    "component_data": {...}
  }
}
```

## 🎮 Component Response Handling System

### 1. Frontend Response Flow

When users interact with components, responses flow back to AG2:

```javascript
// Component interaction triggers response
const onAction = async (action) => {
  // Send response back to AG2 via transport
  await transport.send({
    type: "ui_tool_action",
    data: {
      tool_id: componentId,
      action_type: action.type,
      payload: action.data
    }
  });
};
```

### 2. Backend Response Processing

The backend processes component responses and makes them available to AG2:

```python
# In GroupchatTools - backend handlers
class SimpleAPIKeyManager:
    async def store_api_key(self, enterprise_id: str, service_name: str, api_key: str):
        """Store API key when component submits data"""
        # Store securely in database
        await self.api_keys_collection.update_one(...)
        return True

class FileManager:
    async def handle_download_request(self, file_data: dict):
        """Handle file download from artifact component"""
        # Process file download
        # Log business event
        # Return download URL
```

### 3. Component-to-AG2 Integration

**Key Pattern**: Components don't directly call AG2 - they use workflow-specific tools:

```python
# In workflows/Generator/GroupchatTools/db_manager.py
async def handle_api_key_submission(enterprise_id: str, service: str, api_key: str):
    """
    Called when AgentAPIKeyInput component submits API key.
    This is workflow-specific logic.
    """
    manager = SimpleAPIKeyManager()
    success = await manager.store_api_key(enterprise_id, service, api_key)
    
    if success:
        # API key stored, agent can continue
        return {"status": "success", "message": "API key stored securely"}
    else:
        return {"status": "error", "message": "Failed to store API key"}
```

## 🔄 Complete Interaction Flow Example

### Scenario: Agent needs API key, user provides it

1. **AG2 Agent Requests Component**:
```python
await route_to_inline_component(
    content="I need your OpenAI API key",
    component_name="AgentAPIKeyInput",
    component_data={"service": "OpenAI", "agentId": "ContentGeneratorAgent"}
)
```

2. **Frontend Renders Component**:
```javascript
// Dynamic component loading
const ComponentClass = await loadWorkflowComponent(
    "Generator", 
    "AgentAPIKeyInput", 
    "inline"
);

// Render with response handler
<ComponentClass 
    {...componentData} 
    onAction={handleComponentResponse}
/>
```

3. **User Interacts**:
```javascript
// User submits API key
const handleSubmit = async () => {
    await onAction({
        type: 'api_key_submit',
        agentId: 'ContentGeneratorAgent',
        data: { service: 'OpenAI', apiKey: userInput }
    });
};
```

4. **Response Flows Back**:
```javascript
// Frontend sends to backend
transport.send({
    type: "ui_tool_action",
    data: {
        tool_id: "AgentAPIKeyInput_123",
        action_type: "api_key_submit",
        payload: { service: "OpenAI", apiKey: "sk-..." }
    }
});
```

5. **Backend Processes**:
```python
# Workflow-specific handler processes
await handle_api_key_submission(
    enterprise_id="ent_123",
    service="OpenAI", 
    api_key="sk-..."
)
```

6. **AG2 Agent Continues**:
```python
# Agent can now access stored API key and continue workflow
api_key = await get_stored_api_key("ent_123", "OpenAI")
# Continue with content generation...
```

## 🔗 Workflow Configuration

### workflow.json Structure

```json
{
  "human_in_the_loop": true,
  "transport": "sse",
  "visible_agents": ["user", "ConversationAgent", "ContentGeneratorAgent"],
  "component_capable_agents": {
    "chatpane": ["ConversationAgent"],           // Can use inline components
    "artifact": ["ContentGeneratorAgent"]       // Can create artifacts
  }
}
```

### Component Discovery

The system automatically discovers components at startup:

```python
# Component manifest generation
{
  "artifacts": ["FileDownloadCenter"],
  "inline": ["AgentAPIKeyInput"],
  "tool_mappings": {
    "api_key_input": "AgentAPIKeyInput",
    "file_download": "FileDownloadCenter"
  }
}
```

## 🔒 Security & Data Flow

### 1. Component Isolation
- Each workflow has isolated component namespace
- Components cannot access other workflow's tools
- Secure data passing via encrypted transport

### 2. Response Validation
- All component responses validated before processing
- Workflow-specific handlers ensure proper data handling
- API keys encrypted before storage

### 3. Permission Model
- Only authorized agents can request specific component types
- User interactions logged for audit trail
- Component access controlled by workflow configuration

## 🚀 Why This Works

### 1. **Convention Over Configuration**
- Predictable file structure enables automatic discovery
- Naming conventions eliminate hardcoding needs
- Workflow isolation prevents conflicts

### 2. **Event-Driven Architecture**
- Loose coupling between AG2 and frontend
- Transport abstraction (WebSocket/SSE)
- Asynchronous response handling

### 3. **Dynamic Component Loading**
- React dynamic imports enable runtime component resolution
- Component registry built at startup
- Lazy loading for performance

### 4. **Workflow-Scoped Tools**
- Each workflow defines its own response handlers
- Components use workflow-specific backend tools
- Clear separation of concerns

## 📈 Performance Considerations

1. **Component Caching**: Components loaded once and cached
2. **Event Batching**: Multiple UI events can be batched
3. **Lazy Loading**: Components loaded only when needed
4. **Transport Optimization**: Efficient WebSocket/SSE usage

## 🔧 Adding New Components

### 1. Create Component File
```javascript
// workflows/MyWorkflow/Components/Inline/MyComponent.js
const MyComponent = ({ onAction, ...props }) => {
  const handleUserAction = async (data) => {
    await onAction({
      type: 'my_action',
      data: data
    });
  };
  // ... component logic
};
```

### 2. Create Backend Handler
```python
# workflows/MyWorkflow/GroupchatTools/my_handler.py
async def handle_my_action(data: dict):
    # Process component response
    return {"status": "success"}
```

### 3. Register with AG2
```python
# In workflow setup
tools = [
    route_to_inline_component,  # Already available
    handle_my_action           # Your custom handler
]
```

The system automatically discovers and integrates the new component!

## 🎯 Key Advantages

1. **Zero Hardcoding**: All components discovered dynamically
2. **Workflow Isolation**: Each workflow has its own component ecosystem
3. **Type Safety**: Transport layer ensures consistent data flow
4. **Scalability**: Easy to add new components and workflows
5. **Maintainability**: Clear separation between UI and business logic

This architecture enables AG2 agents to dynamically control sophisticated React UIs while maintaining clean separation of concerns and complete workflow flexibility.
