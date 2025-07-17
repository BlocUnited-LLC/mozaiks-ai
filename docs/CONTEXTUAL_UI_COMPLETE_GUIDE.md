# 🚀 **MozaiksAI Contextual UI System Guide**

**The complete guide to integrating UI components with AG2 agent context awareness**

---

## **📋 Table of Contents**
- [Quick Start](#quick-start) 
- [How It Works](#how-it-works)
- [Component Integration](#component-integration)
- [Agent Access](#agent-access)
- [Architecture](#architecture)
- [Testing](#testing)
- [Migration](#migration)

---

## **🚀 Quick Start**

### **For Component Developers** 
Add contextual awareness to ANY component in 3 lines:

```javascript
import { simpleTransport } from '../core/simpleTransport';

// On user action (submit, download, click, etc.)
simpleTransport.sendComponentAction(
    'YourComponent_uniqueId',    // Component identifier
    'submit',                    // Action type
    { userInput: value }         // Action data
);
```

### **For Agent Developers**
Access UI context in any agent:

```python
# Get overall UI activity summary
context_summary = get_ui_context_summary()

# Check specific component state  
component_state = check_component_state('APIKeyInput_openai')
```

**✅ Zero configuration required - it just works!**

---

## **🔧 How It Works**

```
UI Component → simpleTransport → AG2 ContextVariables → Agent Tools
     ↓              ↓                   ↓                  ↓
  User clicks   WebSocket/HTTP      Context updated    Agents aware
```

### **Key Features**
- ✅ **Dynamic**: Works with ANY component automatically
- ✅ **Modular**: No hardcoding or configuration needed  
- ✅ **Scalable**: Handles unlimited components and data types
- ✅ **AG2-Native**: Uses official AG2 ContextVariables patterns
- ✅ **Zero-Config**: No workflow.json setup required
- ✅ **Dual Transport**: Supports both WebSocket and SSE connections

### **🔄 Transport Compatibility**
The system automatically works with both connection types:
- **WebSocket**: Real-time bidirectional communication (preferred for interactive workflows)
- **SSE (Server-Sent Events)**: HTTP-based streaming (fallback for streaming workflows)

Components use the **same API** regardless of connection type - `simpleTransport.sendComponentAction()` automatically detects and handles both!

---

## **🎯 Component Integration**

### **1. Import Transport**
```javascript
import { simpleTransport } from '../core/simpleTransport';
```

### **2. Send Action on User Interaction**
```javascript
// Example: API Key Input Component
const handleSubmit = () => {
    simpleTransport.sendComponentAction(
        'APIKeyInput_openai',           // Unique component ID
        'submit',                       // Action type
        {                              // Action data
            service: 'openai',
            hasApiKey: true,
            submissionTime: new Date().toISOString()
        }
    );
};

// Example: File Download Component  
const handleDownload = (fileId) => {
    simpleTransport.sendComponentAction(
        'FileDownloadCenter_main',
        'download', 
        {
            fileId: fileId,
            filename: 'generated_code.py',
            downloadTime: new Date().toISOString()
        }
    );
};

// Example: Custom Settings Component
const handlePreferenceChange = (setting, value) => {
    simpleTransport.sendComponentAction(
        'SettingsPanel_preferences',
        'change_setting',
        {
            setting: setting,
            value: value,
            timestamp: new Date().toISOString()
        }
    );
};
```

### **3. Component ID Best Practices**
- **Format**: `ComponentType_identifier` 
- **Examples**: 
  - `APIKeyInput_openai`
  - `FileDownloadCenter_main` 
  - `ChatInterface_primary`
  - `SettingsPanel_preferences`

### **4. Action Types**
Use descriptive action names:
- `submit`, `download`, `upload`, `click`, `change`, `select`, `save`, `delete`

### **5. Action Data**
Include any relevant context:
```javascript
{
    // User inputs
    userInput: "some value",
    
    // State information  
    isEnabled: true,
    
    // Metadata
    timestamp: new Date().toISOString(),
    sessionId: "session_123"
}
```

---

## **🤖 Agent Access**

Agents automatically get access to these AG2 tools:

### **1. Get UI Context Summary**
```python
def some_agent_function():
    # Get overview of all UI activity
    summary = get_ui_context_summary()
    print(summary)
    # Output: "UI Context Summary:
    #         - Total interactions: 5
    #         - Active components: 3  
    #         - Recent actions:
    #           • APIKeyInput_openai: submit
    #           • FileDownloadCenter_main: download"
```

### **2. Check Specific Component State**
```python
def check_api_key_status():
    # Check if user has submitted API keys
    state = check_component_state('APIKeyInput_openai')
    print(state)
    # Output: "Component 'APIKeyInput_openai' last action: submit 
    #          with data: {'service': 'openai', 'hasApiKey': True}"
```

### **3. Use in Agent Logic**
```python
class CodeGeneratorAgent:
    def generate_code(self, request):
        # Check if user has API keys configured
        api_state = check_component_state('APIKeyInput_openai')
        
        if 'submit' in api_state and 'hasApiKey' in api_state:
            # User has API keys, proceed with generation
            return self.generate_with_ai(request)
        else:
            # Ask user to configure API keys first
            return "Please configure your API keys first"
    
    def create_download_link(self, code):
        # Get current UI activity to understand context
        ui_summary = get_ui_context_summary()
        
        # Create download with contextual filename
        if 'python' in ui_summary.lower():
            filename = 'generated_script.py'
        elif 'javascript' in ui_summary.lower():  
            filename = 'generated_script.js'
        else:
            filename = 'generated_code.txt'
            
        return self.create_file_download(code, filename)
```

---

## **🏗️ Architecture**

### **Backend Flow**
```python
# 1. Transport receives message (WebSocket or HTTP)
def handle_component_action(component_id, action_type, action_data):
    
    # 2. Calls AG2 tool directly (same for both connection types)
    result = update_context_from_ui(component_id, action_type, action_data, context_vars)
    
    # 3. Context updated, agents can access via tools
```

### **Frontend Flow**  
```javascript
// 1. User interacts with component
handleUserAction() {
    
    // 2. Component sends action (auto-detects WebSocket vs SSE)
    simpleTransport.sendComponentAction(id, type, data);
    
    // 3. Transport sends via WebSocket OR HTTP POST
}
```

### **AG2 Integration**
```python
# ContextVariables structure:
{
    "ui_interactions": [        # All interactions
        {
            "timestamp": 1234567890,
            "component_id": "APIKeyInput_openai", 
            "action_type": "submit",
            "action_data": {"service": "openai"}
        }
    ],
    "component_states": {       # Current state per component
        "APIKeyInput_openai": {
            "last_action": "submit",
            "last_action_time": 1234567890,
            "action_data": {"service": "openai"}
        }
    },
    "session_metadata": {       # Session tracking
        "interaction_count": 1
    }
}
```

---

## **❓ FAQ**

### **Q: Do I need to configure anything in workflow.json?**
**A:** No! The system works automatically with zero configuration.

### **Q: Can I use any component ID format?**  
**A:** Yes! Use any unique string. Recommended: `ComponentType_identifier`

### **Q: What action types can I use?**
**A:** Any string! Use descriptive names like `submit`, `download`, `click`, etc.

### **Q: How do agents access the context?**
**A:** Via two AG2 tools: `get_ui_context_summary()` and `check_component_state(componentId)`

### **Q: Is this system scalable?**
**A:** Yes! It handles unlimited components and data types dynamically.

### **Q: Do I need to restart anything after adding a component?**
**A:** No! Components work immediately when they start sending actions.

---