# Dynamic UI Component System

## Visual System Flow

```mermaid
flowchart TD
    subgraph Backend["🔧 Backend"]
        A[AI Agent] 
        T[SimpleTransport]
        H[Backend Handler]
        CV[Context Variables]
    end
    
    subgraph Frontend["🖥️ Frontend UI"]
        subgraph ChatPane["Chat Pane"]
            IC[Inline Components<br/>• Forms<br/>• Buttons<br/>• Quick Actions]
        end
        
        subgraph ArtifactPane["Artifact Panel"]
            AC[Artifact Components<br/>• Code Editors<br/>• File Downloads<br/>• Visualizations]
        end
    end
    
    A -->|route_to_chat()| T
    A -->|route_to_artifact()| T
    T -->|ROUTE_TO_CHAT event| IC
    T -->|ROUTE_TO_ARTIFACT event| AC
    IC -->|onAction(payload)| T
    AC -->|onAction(payload)| T
    T -->|component_action| H
    H -->|updates| CV
    CV -->|read by| A
```

## How It Actually Works (The Simple Version)

Here's the core concept: **AG2 agents can request UI components, and users interact with those components to send data back to the agents.**

### The 3-Step Process:

1. **Define UI capabilities in `workflow.json`** - Tell the system which agents can use which components
2. **Agent calls a UI tool** - Agent says "I need component X with data Y"  
3. **Component renders and handles responses** - User interacts, data flows back to agent

## 🎯 The Key Question: How Do Components Talk to Backend?

**Answer: They don't make API calls directly.** Instead, they use a **callback system**:

```javascript
// In your component file (e.g., AgentAPIKeyInput.js)
const AgentAPIKeyInput = ({ onAction, service, ...props }) => {
  const handleSubmit = async (e) => {
    // This callback sends data back through the transport layer
    await onAction({
      type: 'api_key_submit',
      data: { service, apiKey: userInput }
    });
  };
  
  return (
    <form onSubmit={handleSubmit}>
      <input type="password" placeholder={`Enter ${service} API key...`} />
      <button type="submit">Submit</button>
    </form>
  );
};
```

**The system automatically provides the `onAction` callback** - you don't need to create API endpoints or make fetch calls. The callback routes through the WebSocket/SSE transport back to your backend handler.

## 🚨 IMPORTANT: Who Handles User Selections?

**When components need user selections (clicks, choices, inputs), the COMPONENT handles it - NOT the core transport layer.**

### ❌ What Core Transport Does NOT Handle:
- User clicks within your component
- Form submissions from your component  
- Selection choices (dropdowns, radio buttons, etc.)
- Component-specific user interactions

### ✅ What YOUR Component Must Handle:
```javascript
// Your component handles ALL its own user interactions
const ImageSelector = ({ onAction, images, ...props }) => {
  const [selectedImage, setSelectedImage] = useState(null);
  
  // Component handles the user click/selection
  const handleImageClick = (imageId) => {
    setSelectedImage(imageId);
    // Component sends selection back to agent via onAction
    onAction({
      type: 'image_selected',
      data: { selectedImage: imageId }
    });
  };
  
  return (
    <div>
      {images.map(img => (
        <img 
          key={img.id}
          onClick={() => handleImageClick(img.id)} // Component handles click
          src={img.url}
          className={selectedImage === img.id ? 'selected' : ''}
        />
      ))}
    </div>
  );
};
```

### 🔄 The Correct Flow:
```
1. Agent: "Show user 3 image options"
   └── Generates ImageSelector component

2. Component: Renders 3 clickable images
   └── User sees UI with image choices

3. User: Clicks on image #2
   └── Component's handleImageClick() runs

4. Component: Calls onAction({ type: 'image_selected', data: { selectedImage: 2 }})
   └── Data flows to backend handler

5. Backend Handler: Processes selection
   └── Agent continues with user's choice
```

**Key Point**: The core system provides the **transport mechanism** (onAction callback), but your **component provides the interaction logic** (what happens when user clicks/selects).

Think of it like this:
- **Core System**: "Here's a phone line to talk to the backend" (onAction)
- **Your Component**: "Here's what the user can click and what message to send" (UI + interaction logic)

## ⚙️ Complete Setup (Step by Step)

### 1. Define in workflow.json

```json
{
  "ui_capable_agents": [
    {
      "name": "APIKeyAgent",
      "capabilities": ["chat", "inline_components"], 
      "components": [
        {
          "name": "AgentAPIKeyInput",           # Must match .js filename
          "type": "inline",
          "actions": ["submit", "cancel"],
          "backend_handler": "api_manager.store_api_key"  # Python function to handle responses
        }
      ]
    }
  ]
}
```

### 2. Create Component File

```javascript
// workflows/YourWorkflow/Components/Inline/AgentAPIKeyInput.js
const AgentAPIKeyInput = ({ onAction, service, agentId, ...props }) => {
  const [apiKey, setApiKey] = useState('');
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    // This automatically routes to your backend_handler
    await onAction({
      type: 'api_key_submit',
      agentId,
      data: { service, apiKey }
    });
  };
  
  return (
    <form onSubmit={handleSubmit}>
      <input 
        type="password" 
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={`Enter ${service} API key...`} 
      />
      <button type="submit">Submit</button>
    </form>
  );
};

export default AgentAPIKeyInput;
```

### 3. Create Backend Handler

+> **Python Handler Placement & Import Path**
+> - Place your `.py` handler file under `workflows/YourWorkflow/tools`.
+> - In `workflow.json`, set `backend_handler` to the module path and function name (e.g., `api_manager.store_api_key`).
+> - The system uses this path to import and invoke your async handler at runtime.

```python
# workflows/YourWorkflow/tools/api_manager.py
async def store_api_key(data):
    """This function gets called when user submits the form"""
    service = data['service']
    api_key = data['apiKey'] 
    agent_id = data['agentId']
    
    # Store the API key securely
    await db.store_api_key(agent_id, service, api_key)
    
    # Return response (optional)
    return {"status": "success", "message": "API key stored"}
```

### 4. Agent Uses It

```python
# In your AG2 agent
class APIKeyAgent:
    async def generate_reply(self, messages):
        if self.needs_api_key():
            # This triggers the component to render
            await route_to_inline_component(
                content="I need your OpenAI API key to continue",
                component_name="AgentAPIKeyInput",
                component_data={
                    "service": "OpenAI",
                    "agentId": self.name
                }
            )
            # Agent waits for user to submit the form
            # Then continues with the stored API key
```

## 🔄 The Flow In Action

```
1. Agent: "I need an API key" 
   └── Calls route_to_inline_component()

2. Frontend: Component renders with onAction callback
   └── User sees API key input form

3. User: Enters API key and clicks submit
   └── onAction() called with data

4. Backend: Handler processes the data  
   └── api_manager.store_api_key() runs

5. Agent: Can now access stored API key
   └── Continues workflow
```

## 🎯 Key Points for Non-Developers

- ✅ **No API calls needed** - Components use callbacks provided by the system
- ✅ **No endpoints to create** - The transport layer handles everything  
- ✅ **Simple file structure** - Just create `.js` files in the right folders
- ✅ **Automatic discovery** - System finds components from workflow.json
- ✅ **Type safety** - Data flows cleanly between frontend and backend

The beauty is that **you don't need to understand the plumbing** - just define your components in workflow.json, create the .js files with onAction callbacks, and create Python handlers. The system connects everything automatically!
│## 📁 Directory Structure

```
workflows/
├── YourWorkflow/
│   ├── workflow.json                   # Define UI capabilities here
│   ├── Components/
│   │   ├── Artifacts/                  # Full-screen components (right panel)
│   │   │   └── FileDownloadCenter.js   
│   │   └── Inline/                     # Chat-embedded components
│   │       └── AgentAPIKeyInput.js     
│   └── tools/                          # Backend response handlers
│       └── api_manager.py              # Handles component responses
```

## 🛠️ Technical Details (For Developers)

### Component Types

**Inline Components**: Embedded in chat (forms, inputs, simple interactions)
**Artifact Components**: Full-screen in right panel (file downloads, editors, complex UIs)

### The Transport Layer

The system uses both WebSocket and SSE transports via a unified transport manager and component bridge. The `onAction` callback sends a `component_action` message to the backend, which the core `component_bridge.route_component_action` function handles and dispatches to your specified `backend_handler`.

- Supports WebSocket and SSE transports.
- Unified handling via `route_component_action` in `core/ui/component_bridge.py`.
- Payload includes `type`, `data`, `agentId`, and workflow `context_variables`.

When you call `onAction(data)`, it automatically routes through this transport to your specified `backend_handler` function.

### Backend Handler Integration with AG2 ContextVariables

When your handler is invoked, it receives a `context_variables` object. You can use `context_variables.set(key, value)` to persist state across the conversation and `context_variables.get(key)` to retrieve it later. Updating these variables directly changes the groupchat state, enabling branching logic, conditional prompts, or dynamic UI based on prior interactions. This mechanism lets you drive the flow of the chat by storing flags, counters, or user choices in `context_variables`.

**🔗 Complete Integration Flow:**
```
1. Component Action (React)
   └── onAction({ type: 'submit', data: {...} })

2. Transport Layer  
   └── Routes to component_bridge.route_component_action()

3. Backend Handler (Python)
   └── async def store_api_key(data, context_variables)
   └── Updates AG2 ContextVariables with user interaction data

4. AG2 Agents
   └── Use tools to access context_variables
   └── Continue workflow with user's input/choices
```

**🐍 Backend Handler Structure:**
```python
# workflows/YourWorkflow/tools/api_manager.py
async def store_api_key(data: Dict[str, Any], context_variables: ContextVariables) -> Dict[str, Any]:
    api_key = data.get('apiKey')
    service = data.get('service')
    
    # Store in AG2 ContextVariables for agents to access
    secure_keys = context_variables.get('secure_api_keys', {})
    secure_keys[service] = api_key
    context_variables.set('secure_api_keys', secure_keys)
    context_variables.set('api_key_ready', True)
    
    return {"status": "success", "service": service}
```

**🤖 Agent Tool Access:**
```python
# workflows/YourWorkflow/tools/component_context_tool.py
def check_api_key_for_service(service: str, context_variables: ContextVariables) -> str:
    secure_keys = context_variables.get('secure_api_keys', {})
    if service in secure_keys:
        return f"✅ API key for {service} is available"
    return f"❌ No API key configured for {service}"
```

**📋 Required Files for Full Integration:**
```
workflows/YourWorkflow/
├── workflow.json                           # Define components + backend_handlers
├── Components/
│   ├── Inline/AgentAPIKeyInput.js         # React component with onAction
│   └── Artifacts/FileDownloadCenter.js    # React component with onAction  
└── tools/
    ├── api_manager.py                     # Backend handler for API keys
    ├── file_manager.py                    # Backend handler for downloads
    ├── component_bridge.py                # Routes actions to handlers
    └── component_context_tool.py          # Agent tools to access state
```

### Error Handling

If your backend handler throws an error, it's automatically caught and can be displayed in the component. The system provides built-in error boundaries and validation.

### Security

**Current Transport Security**: The WebSocket/SSE transport layer has **minimal built-in security**:

- ✅ **Basic Transport**: Uses standard WebSocket/SSE protocols
- ❌ **No Authentication**: No auth tokens or user verification in transport layer
- ❌ **No Input Validation**: Raw data passes through to handlers
- ❌ **No Encryption**: Data sent as plain JSON (unless HTTPS/WSS is configured at server level)

**What You Need to Implement:**
- **API Key Security**: Encrypt sensitive data in your backend handlers
- **Input Validation**: Add validation in both React components and Python handlers  
- **Authentication**: Implement user verification at the FastAPI/server level
- **Data Sanitization**: Clean user inputs before processing

**Recommendation**: The transport layer is a "dumb pipe" - all security must be implemented in your components and handlers.

## 🎯 Common Use Cases

### API Key Collection
Agent needs credentials → Renders secure input → User enters key → Stored for workflow

### File Download
Agent generates files → Renders download center → User downloads → Workflow complete

### Form Data Collection  
Agent needs user info → Renders form → User fills out → Data processed by workflow

### Progress Tracking
Long-running task → Renders progress bar → Updates in real-time → Completion notification

### User Selection/Choice Components
Agent needs user decision → Renders choice component → **Component handles user clicks** → Selection sent to agent

**Example: Image Selection Component**
```javascript
// Agent requests: "Let user pick their favorite image"
// Component renders: 3 clickable images
// User clicks: Image #2
// Component handles: onClick → onAction({ type: 'choice', data: { selection: 2 }})
// Agent receives: User chose image #2, continues workflow
```

**Remember**: Your component = Your interaction logic. The core just provides the communication channel (onAction).

## 🔄 Workflow-Agnostic Context Variable Integration

**NEW: The system now supports automatic AG2 ContextVariables updates from component actions!**

### How It Works:

1. **Enable in workflow.json**: Add `"context_adjustment": true` to ui_capable_agents
2. **Component sends action**: Use `onAction()` with proper action data structure  
3. **Core system routes**: Automatically updates AG2 ContextVariables
4. **Agents access**: Use tools to access updated context and continue workflow

### Example Configuration:

```json
// workflow.json
{
  "ui_capable_agents": [
    {
      "name": "APIKeyAgent",
      "capabilities": ["chat", "inline_components"],
      "context_adjustment": true,
      "components": [
        {
          "name": "AgentAPIKeyInput",
          "type": "inline",
          "actions": ["submit", "cancel"]
        }
      ]
    }
  ]
}
```

### Component Implementation:

```javascript
// Component MUST include action type and data
const AgentAPIKeyInput = ({ onAction, service, ...props }) => {
  const handleSubmit = async (apiKey) => {
    await onAction({
      type: 'api_key_submit',    // Required: action type
      apiKey: apiKey,            // Component data
      service: service,          // Component data
      agentId: 'APIKeyAgent'     // Optional: agent context
    });
  };
  
  const handleCancel = async () => {
    await onAction({
      type: 'cancel',            // Required: action type
      service: service           // Component data
    });
  };
  
  return (
    <form onSubmit={handleSubmit}>
      {/* Component UI */}
    </form>
  );
};
```

### Workflow Context Handler (Optional):

```python
# workflows/YourWorkflow/ContextVariables.py
async def context_update(agent_name, component_name, action_data, context_variables):
    """Custom context update function - called automatically by core system"""
    
    action_type = action_data.get('type')
    
    if component_name == 'AgentAPIKeyInput' and action_type == 'api_key_submit':
        # Store API key in ContextVariables
        api_key = action_data.get('apiKey')
        service = action_data.get('service')
        
        # Store securely
        secure_keys = context_variables.get('secure_api_keys', {}) or {}
        secure_keys[service] = api_key
        context_variables.set('secure_api_keys', secure_keys)
        
        # Store public metadata
        api_keys = context_variables.get('api_keys', {}) or {}
        api_keys[service] = {
            'masked_key': f"{api_key[:6]}...{api_key[-4:]}",
            'status': 'active',
            'submitted_at': str(time.time())
        }
        context_variables.set('api_keys', api_keys)
        context_variables.set('api_key_ready', True)
        
        return {"status": "success", "service": service}
    
    # Handle other components...
    return {"status": "unhandled"}
```

### Agent Access:

```python
# Agent tool to access component context
def check_api_status(context_variables):
    """Agent can check if user provided API keys"""
    return context_variables.get('api_key_ready', False)

def get_secure_api_key(service: str, context_variables):
    """Agent can retrieve stored API keys"""
    secure_keys = context_variables.get('secure_api_keys', {})
    return secure_keys.get(service)
```

**Key Benefits:**
- ✅ **Workflow-agnostic**: Works with any workflow type
- ✅ **No backend endpoints needed**: Core handles routing automatically  
- ✅ **AG2 native**: Uses standard ContextVariables for seamless integration
- ✅ **Fallback support**: Generic updates if no custom function provided
- ✅ **Optional**: Only enabled with `"context_adjustment": true`
