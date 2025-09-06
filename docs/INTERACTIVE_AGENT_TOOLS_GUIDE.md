# Interactive Agent Tools Developer Guide

## 🎯 Overview

This guide demonstrates the **Interactive Agent System** implementation in MozaiksAI. The system enables agents to trigger UI components during workflow execution and wait for user responses before continuing.

## 🏗️ Architecture

```
Agent Tool Call → AG2 Event → UI Event → WebSocket → Frontend Component → User Interaction → Response → Agent Continues
```

### Key Components

1. **AG2 Integration**: Uses native `FunctionCallEvent`/`ToolCallEvent` detection
2. **UI Tool Detection**: Automatic detection based on tool naming patterns
3. **Component Types**: "inline" (small UI elements) and "artifact" (large persistent areas)
4. **Response Handling**: Async waiting mechanism with structured responses
5. **Single WebSocket**: All interactions flow through existing transport layer

## 📝 Tool Component Examples

### 1. API Key Input (Inline Component)

**Python Tool**: `tools/ui_tools/api_key_input.py`
```python
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response

async def api_key_input(service_name: str, required: bool = True) -> str:
    """Request API key through interactive UI component"""
    
    payload = {
        "service_name": service_name,
        "required": required,
        "component_props": {
            "input_type": "password",
            "validation": {"min_length": 10}
        }
    }
    
    event_id = await emit_ui_tool_event(
        tool_id="api_key_input",
        payload=payload,
        display="inline",
        chat_id=chat_id
    )
    
    response = await wait_for_ui_tool_response(event_id)
    return response.get("api_key", "")
```

**Frontend Component**: `tools/ui_tools/api_key_input.js`
```javascript
const ApiKeyInput = ({ payload, onResponse }) => {
  const [apiKey, setApiKey] = useState('');
  
  const handleSubmit = () => {
    onResponse({
      api_key: apiKey,
      cancelled: false
    });
  };
  
  return (
    <div className="api-key-input-container">
      <input 
        type="password" 
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={payload.placeholder}
      />
      <button onClick={handleSubmit}>Submit</button>
    </div>
  );
};
```

### 2. Confirmation Dialog (Inline Modal)

**Python Tool**: `tools/ui_tools/confirmation_dialog.py`
```python
async def confirmation_dialog(message: str, severity: str = "info") -> bool:
    """Display confirmation dialog and wait for user response"""
    
    payload = {
        "message": message,
        "severity": severity,
        "component_props": {"modal": True}
    }
    
    event_id = await emit_ui_tool_event(
        tool_id="confirmation_dialog",
        payload=payload,
        display="inline"
    )
    
    response = await wait_for_ui_tool_response(event_id)
    return response.get("confirmed", False)

# Convenient wrappers
async def confirm_action(action: str) -> bool:
    return await confirmation_dialog(f"Are you sure you want to {action}?", "warning")

async def confirm_destructive_action(action: str) -> bool:
    return await confirmation_dialog(f"⚠️ This cannot be undone!\n\n{action}", "error")
```

### 3. Code Editor Artifact (Large Persistent Component)

**Python Tool**: `tools/ui_tools/code_editor_artifact.py`
```python
async def code_editor_artifact(code: str, language: str = "python", editable: bool = True) -> Dict[str, Any]:
    """Display code in interactive editor artifact"""
    
    payload = {
        "code": code,
        "language": language,
        "editable": editable,
        "component_props": {
            "syntax_highlighting": True,
            "line_numbers": True,
            "actions": [
                {"id": "save", "label": "Save Changes", "primary": True},
                {"id": "download", "label": "Download"},
                {"id": "copy", "label": "Copy to Clipboard"}
            ]
        }
    }
    
    event_id = await emit_ui_tool_event(
        tool_id="code_editor_artifact",
        payload=payload,
        display="artifact",  # Large persistent component
        chat_id=chat_id
    )
    
    response = await wait_for_ui_tool_response(event_id)
    return {
        "code": response.get("code", code),
        "modified": response.get("modified", False),
        "action": response.get("action", "unknown")
    }
```

## 🔧 How It Works

### 1. Automatic Tool Detection

The system automatically detects UI tools based on naming patterns:

```python
# In core/workflow/ui_tools.py - event_to_payload()
is_ui_tool = any(pattern in str(tool_name).lower() for pattern in [
    "input", "confirm", "select", "upload", "download", 
    "edit", "api_key", "form", "artifact"
])
```

### 2. Component Type Classification

```python
# Automatic classification
component_type = "inline"  # Default
if any(pattern in str(tool_name).lower() for pattern in ["editor", "viewer", "document", "artifact"]):
    component_type = "artifact"
```

### 3. Event Processing Flow

1. **Agent calls tool** → AG2 emits `FunctionCallEvent`/`ToolCallEvent`
2. **Orchestrator intercepts** → `handle_tool_call_for_ui_interaction()` processes event
3. **UI Event emission** → `emit_ui_tool_event()` sends to WebSocket transport
4. **Frontend renders** → Component appears in chat interface
5. **User interacts** → Response sent back via WebSocket
6. **Agent continues** → Tool returns with user's response

### 4. AG2 Tool Registration

Tools can be registered with AG2 using standard patterns:

```python
# In your agent configuration
tools = [
    {
        "function": api_key_input,
        "description": "Request API key from user",
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string"},
                "required": {"type": "boolean", "default": True}
            },
            "required": ["service_name"]
        }
    }
]

agent = ConversableAgent(
    name="assistant",
    tools=tools,
    # ... other config
)
```

## 🎨 Frontend Integration

### Component Registration

Frontend components should export metadata for discovery:

```javascript
export const componentMetadata = {
  name: 'api_key_input',
  type: 'inline',  // or 'artifact'
  description: 'Interactive API key input component',
  pythonTool: 'tools.ui_tools.api_key_input.api_key_input',
  category: 'input'
};
```

### Dynamic Component Loading

The frontend's `DynamicUIHandler` automatically routes UI tool events to the appropriate components based on the `ui_tool_id`.

## 🚀 Usage Examples

### Simple Confirmation

```python
# In your agent tool
if await confirm_action("delete all files"):
    # Proceed with deletion
    delete_files()
else:
    return "Operation cancelled by user"
```

### API Key Collection

```python
# In your agent tool
try:
    openai_key = await api_key_input("OpenAI", "Needed to access GPT-4")
    client = OpenAI(api_key=openai_key)
    # Use the API...
except ValueError as e:
    return f"Cannot proceed: {e}"
```

### Code Generation & Editing

```python
# In your agent tool  
generated_code = generate_python_function(requirements)

result = await code_editor_artifact(
    code=generated_code,
    language="python",
    title="Generated Function",
    description="Review and edit the generated code"
)

if result["modified"]:
    final_code = result["code"]
    return f"Code updated by user: {final_code}"
else:
    return f"User approved original code: {generated_code}"
```

## 🎯 Best Practices

### 1. Tool Naming

Use descriptive names that include interaction patterns:
- `api_key_input` → Automatically detected as UI tool
- `file_selector` → Inline component
- `document_editor_artifact` → Artifact component

### 2. Error Handling

Always handle cancellations and timeouts:

```python
try:
    response = await ui_tool_function()
    # Process response
except ValueError:
    # Handle user cancellation
    return "Operation cancelled"
```

### 3. Component Design

- **Inline**: Keep small, focused, quick interactions
- **Artifact**: Use for substantial content that benefits from dedicated space

### 4. Payload Structure

Structure payloads consistently:

```python
payload = {
    # Core data
    "primary_data": "...",
    
    # UI configuration
    "component_props": {
        "title": "...",
        "validation": {...},
        "actions": [...]
    },
    
    # Metadata
    "metadata": {
        "created_by": "agent",
        "context": "..."
    }
}
```

## 🔍 Debugging

### Enable Logging

```python
import logging
logging.getLogger("core.workflow.ui_tools").setLevel(logging.DEBUG)
```

### Check Event Flow

1. **Agent logs**: Look for tool call detection
2. **Transport logs**: Verify WebSocket events
3. **Frontend console**: Check component rendering
4. **Response logs**: Confirm response flow

## 🚦 Production Considerations

### Performance

- Tool interactions add latency - use judiciously
- Consider timeout handling for user interactions
- Monitor component render performance

### Security

- Validate all user inputs from UI components
- Sanitize code content in editor components
- Implement proper error boundaries

### User Experience

- Provide clear interaction guidance
- Handle cancellations gracefully
- Show progress indicators for long operations

---

This interactive agent system provides a foundation for building sophisticated human-in-the-loop workflows while maintaining clean separation between agent logic and UI components.
