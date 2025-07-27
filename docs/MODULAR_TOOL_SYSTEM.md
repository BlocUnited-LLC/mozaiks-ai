# Modular Tool System: JSON-Driven Agent Tools with Single-Function Architecture

## Overview

This document outlines our modular tool system that centralizes all tool configuration in `workflow.json` with a clean single-function-per-module architecture. Each tool is an individual async function in its own Python file, making the system highly modular, maintainable, and easy to understand.

**🎯 For detailed Dynamic UI implementation, see [DYNAMIC_UI_COMPLETE_GUIDE.md](./DYNAMIC_UI_COMPLETE_GUIDE.md)**

## Goals

1. **Single Source of Truth**: All tool configuration lives in `workflow.json`
2. **One Function Per File**: Each Python module exports exactly one async tool function
3. **Clear Categorization**: Tools are organized by purpose (backend, UI, lifecycle)
4. **Event-Driven UI Integration**: UI tools emit events that render React components via transport layer
5. **Lifecycle Hook System**: System hooks execute at specific workflow moments

## Architecture Overview

```
workflow.json (Configuration)
    ↓
WorkflowToolRegistry (Parser & Registry)
    ↓
Individual Tool Modules (One function each)
    ↓
Backend Tools → Agents (Direct Function Calls)
UI Tools → Transport Layer → Frontend Components
Lifecycle Tools → System Hooks
```

## Tool Categories

### 1. Backend Tools (`backend_tools`)
Regular tools that agents can call for computation, processing, or business logic.

**Execution:**
- Agent calls function directly when needed
- No UI interaction required

### 2. UI Tools (`ui_tools`)
Tools that interact with the frontend through UI components via the transport layer.

**📖 Complete UI implementation details in [DYNAMIC_UI_COMPLETE_GUIDE.md](./DYNAMIC_UI_COMPLETE_GUIDE.md)**

**Execution:**
- Tool calls `send_tool_event()` to emit UI event
- Frontend renders React component based on `tool_id` 
- User interacts with component
- Response sent back via `/api/ui-tool/submit` endpoint
- Original tool function receives response through `wait_for_ui_tool_response()`

**Display Options:**
- `"inline"`: Display in chat interface
- `"artifact"`: Display in side panel/artifact view

**Required Fields:**
- `path`: Python function path
- `tool_id`: Maps to React component in frontend
- `display`: Where to render the UI component
- `description`: Tool purpose and usage

### 3. Lifecycle Tools (`lifecycle_tools`) 
System hooks that execute at specific workflow moments.

**Lifecycle Events:**
- `"before_agent_speaks"`: Before any agent generates a reply
- `"after_agent_speaks"`: After any agent sends a message
- `"on_user_input"`: When user sends a message
- `"lifecycle_event"`: Specifies when the hook should execute

## Tool Module Structure

Each tool is a single async function in its own Python file:

### Backend Tool Example
```python
# workflows/Generator/tools/echo_all.py
from typing import Annotated

async def echo(message: Annotated[str, "The message to echo back to the user"]) -> str:
    """Simple echo tool that returns the input message with an 'Echo:' prefix."""
    return f"Echo: {message}"
```

### UI Tool Example  
```python
# workflows/Generator/tools/request_api_key.py
import asyncio
import uuid
from typing import Dict, Any, Optional

async def request_api_key(
    service: str,
    description: Optional[str] = None,
    required: bool = True,
    workflow_name: str = "generator"
) -> Dict[str, Any]:
    """Request an API key from the user via UI component.
    
    See DYNAMIC_UI_COMPLETE_GUIDE.md for complete implementation details.
    """
    from core.transport.simple_transport import SimpleTransport
    transport = SimpleTransport()
    
    event_id = f"api_key_input_{str(uuid.uuid4())[:8]}"
    
    # Emit UI tool event to frontend
    await transport.send_tool_event({
        "type": "ui_tool_event",
        "toolId": "api_key_input",
        "eventId": event_id,
        "workflowname": workflow_name,
        "payload": {
            "service": service,
            "label": f"{service.replace('_', ' ').title()} API Key",
            "description": description or f"Enter your {service} API key",
            "required": required
        }
    })
    
    # Wait for user response from frontend
    response = await transport.wait_for_ui_tool_response(event_id)
    return response
```

### Lifecycle Tool Example
```python  
# workflows/Generator/tools/agent_state_logger.py
from typing import Any

async def log_agent_state_update(agent, messages) -> Any:
    """Log when any agent updates its state before generating a reply."""
    agent_name = getattr(agent, 'name', 'Unknown') if agent else 'Unknown'
    message_count = len(messages) if messages else 0
    
    print(f"🔄 STATE LOGGER: {agent_name} updating state before reply (messages: {message_count})")
    
    return messages
```

## Tool Registry Implementation

```python
# core/workflow/tool_registry.py  
import json
import importlib
from pathlib import Path
from typing import Dict, List, Any

class WorkflowToolRegistry:
    """Central registry for workflow tools with single-function architecture"""
    
    def __init__(self, workflow_name: str):
        self.workflow_name = workflow_name
        self.backend_tools: Dict[str, List[Dict]] = {}
        self.ui_tools: Dict[str, List[Dict]] = {} 
        self.lifecycle_tools: Dict[str, Dict] = {}
        self.config_path = Path("workflows") / workflow_name / "workflow.json"
        
    def load_configuration(self):
        """Load tool configuration from workflow.json"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"No workflow.json found at '{self.config_path}'")
            
        with open(self.config_path, 'r') as f:
            config = json.load(f)
            
        self.backend_tools = config.get("backend_tools", {})
        self.ui_tools = config.get("ui_tools", {})
        self.lifecycle_tools = config.get("lifecycle_tools", {})
        
    def import_tool_function(self, tool_path: str):
        """Dynamically import a single tool function"""
        module_path, function_name = tool_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, function_name)
```

## Implementation Benefits

### 1. **Clean Architecture**
- One function per file eliminates confusion
- Easy to locate and modify specific tools
- Clear separation of concerns

### 2. **JSON-Driven Configuration**  
- All tool logic lives in declarative JSON
- No need to modify Python for new tools
- Version control friendly

### 3. **Event-Driven Architecture**
- Backend tools execute directly when called by agents
- UI tools use event emission pattern via transport layer
- Lifecycle tools hook into specific system moments
- `tool_id` field maps UI events to React components

### 4. **Transport-Layer Integration**
- UI tools emit events through `send_tool_event()`
- Frontend renders components based on `tool_id` mapping
- User responses handled via `/api/ui-tool/submit` endpoint
- Async response collection through `wait_for_ui_tool_response()`

### 5. **Maintainable & Scalable**
- Adding new tools requires only new Python file + JSON config
- Tool functions are reusable across workflows
- Easy testing of individual functions

## Directory Structure

```
workflows/Generator/
├── workflow.json           # Complete tool configuration
├── tools/                  # Individual tool modules
│   ├── __init__.py        # Tool imports
│   ├── echo_all.py        # Backend: echo function
│   ├── echo_ctx_only.py   # Backend: echo_context function
│   ├── request_api_key.py # UI: request_api_key function
│   ├── store_api_key.py   # UI: store_api_key function
│   ├── request_file_download.py    # UI: request_file_download
│   ├── handle_file_download.py     # UI: handle_file_download  
│   ├── agent_state_logger.py       # Lifecycle: log_agent_state_update
│   ├── conversation_analyzer.py    # Lifecycle: analyze_full_conversation
│   ├── message_sender_tracker.py   # Lifecycle: track_message_sending
│   └── latest_message_inspector.py # Lifecycle: inspect_latest_message
└── initializer.py         # Workflow initialization
```

## Migration Complete ✅

The system has been successfully implemented with:

1. ✅ **Single-function architecture**: Each tool module exports exactly one async function  
2. ✅ **Updated workflow.json**: Clear categorization with backend_tools, ui_tools, lifecycle_tools
3. ✅ **Tool registry integration**: WorkflowToolRegistry parses JSON configuration
4. ✅ **Clean imports**: All tools importable via individual modules
5. ✅ **Event-driven UI system**: UI tools emit events via transport layer with `tool_id` mapping
6. ✅ **Display options**: `"inline"` and `"artifact"` rendering locations
7. ✅ **Lifecycle events**: System hooks with precise timing control via `lifecycle_event` field

## Conclusion

This modular tool system provides a clean, maintainable approach to agent tool management. The single-function-per-module architecture makes the system highly understandable and maintainable, while the JSON configuration provides flexibility without requiring code changes.

The event-driven UI integration, combined with clear categorization of backend, UI, and lifecycle tools, creates a powerful foundation for building complex conversational workflows.
    """Central registry for workflow tools with timing control"""
    
## Directory Structure

```
workflows/Generator/
├── workflow.json           # Complete tool configuration
├── Agents.py              # Agent definitions (no tool imports needed)
└── tools/                 # Individual tool modules
    ├── echo_all.py        # Backend: Simple echo tool
    ├── echo_ctx_only.py   # Backend: Context-specific echo
    ├── request_api_key.py # UI: API key request via transport
    ├── store_api_key.py   # UI: API key storage handler
    ├── request_file_download.py    # UI: File download request
    ├── handle_file_download.py     # UI: File download handler
    ├── agent_state_logger.py       # Lifecycle: State logging hook
    ├── conversation_analyzer.py    # Lifecycle: Conversation analysis
    ├── message_sender_tracker.py   # Lifecycle: Message tracking
    └── latest_message_inspector.py # Lifecycle: Message inspection
```

## Key Changes Made

1. **Removed Trigger System**: No more `trigger` field in tool configuration
2. **Added `tool_id` Field**: UI tools now map to React components via `tool_id`
3. **Replaced `ui_routing` with `display`**: Display location specified as `"inline"` or `"artifact"`
4. **Event-Driven UI**: UI tools use transport layer's `send_tool_event()` and `wait_for_ui_tool_response()`
5. **Simplified Backend Tools**: No trigger needed - agents call when needed
6. **Enhanced Lifecycle Tools**: Use `lifecycle_event` field instead of trigger enumeration

## Related Documentation

- **[DYNAMIC_UI_COMPLETE_GUIDE.md](./DYNAMIC_UI_COMPLETE_GUIDE.md)** - Comprehensive guide to the dynamic UI system, including:
  - Complete event flow breakdown
  - Agent system message best practices
  - Frontend component implementation patterns
  - Error handling strategies
  - Testing and debugging approaches
  - Advanced multi-step UI workflows

- **[TOOL_MANIFEST_SYSTEM.md](./TOOL_MANIFEST_SYSTEM.md)** - Tool discovery and manifest system
- **[WORKFLOW_CONFIG.md](./WORKFLOW_CONFIG.md)** - Workflow configuration patterns

This architecture provides a clean, maintainable foundation for building complex agent workflows with sophisticated UI interactions and precise lifecycle control.
