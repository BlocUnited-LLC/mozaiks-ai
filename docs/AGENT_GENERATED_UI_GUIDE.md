# Agent-Generated UI Components Developer Guide

## 🎯 Overview

This system enables **agents to dynamically generate UI components** during workflow execution. It provides a clean, workflow-agnostic architecture that separates AG2's tool system from custom UI events.

## 🏗️ Architecture

```
Agent calls tool → AG2 registers tool → Tool emits UI event → Frontend renders component → User interacts → Response returns to agent
```

### Key Components:

1. **AG2 Tool Registration**: Standard tool registration via `tools.json` (legacy `tools.yaml` supported during migration)
2. **Sync/Async Bridge**: Clean separation between AG2's sync expectations and async UI
3. **UI Event System**: Custom events that route to your frontend components
4. **Workflow Agnostic**: Works across any workflow, not tied to specific implementations

## 🚀 Quick Start

### 1. Create a Custom UI Tool

```python
from core.ui_tools import BaseUITool

class MyCustomTool(BaseUITool):
    def __init__(self):
        super().__init__("my_tool", "my_ui_component")
    
    def get_component_config(self, data):
        return {
            'component_type': 'MyCustomComponent',
            'title': data.get('title', 'Default Title'),
            'required': True
        }
    
    def process_ui_response(self, response, data):
        if response.get('status') == 'success':
            return f"✅ Success: {response.get('data', {}).get('value')}"
        return "❌ Operation cancelled"

# Export for registration
my_tool = MyCustomTool()
def my_custom_function(data):
    return my_tool(data)
```

### 2. Register in tools.json

```yaml
my_custom_function:
  description: "Generate custom UI component"
  enabled: true
```

### 3. Create Frontend Component

```javascript
// MyCustomComponent.js
import React, { useState } from 'react';

const MyCustomComponent = ({ payload, onResponse, onCancel }) => {
  const [value, setValue] = useState('');
  
  const handleSubmit = async () => {
    await fetch('/api/ui-tool/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ui_tool_id: 'my_ui_component',
        status: 'success',
        data: { value }
      })
    });
    
    if (onResponse) onResponse({ status: 'success', data: { value } });
  };
  
  return (
    <div className="custom-component">
      <h3>{payload.title}</h3>
      <input 
        value={value} 
        onChange={(e) => setValue(e.target.value)}
        placeholder="Enter value..."
      />
      <button onClick={handleSubmit}>Submit</button>
      <button onClick={() => onCancel?.({ status: 'cancelled' })}>
        Cancel
      </button>
    </div>
  );
};

export default MyCustomComponent;
```

### 4. Agent Uses the Tool

```python
# In your agent's system message or workflow logic
"To collect custom input, use: my_custom_function({'title': 'Enter Details', 'chat_id': current_chat_id})"
```

## 📚 Available Example Tools

### Text Input Tool
```python
get_text_input({
    'title': 'Enter Your Name',
    'description': 'Please provide your full name',
    'placeholder': 'John Doe',
    'required': True
})
```

### File Upload Tool
```python
upload_file({
    'title': 'Upload Document',
    'accepted_types': ['.pdf', '.doc'],
    'max_size_mb': 5
})
```

### Confirmation Tool
```python
get_confirmation({
    'title': 'Delete File?',
    'message': 'Are you sure you want to delete this file?',
    'danger': True
})
```

### Choice Selection Tool
```python
get_choice({
    'title': 'Select Option',
    'choices': ['Option A', 'Option B', 'Option C'],
    'multiple': False
})
```

## 🎨 Creating Advanced UI Components

### Multi-Step Component

```python
class MultiStepTool(BaseUITool):
    def get_component_config(self, data):
        return {
            'component_type': 'MultiStepWizard',
            'steps': [
                {'title': 'Basic Info', 'fields': ['name', 'email']},
                {'title': 'Preferences', 'fields': ['theme', 'notifications']},
                {'title': 'Confirmation', 'fields': []}
            ],
            'current_step': 0
        }
    
    def process_ui_response(self, response, data):
        if response.get('status') == 'completed':
            collected_data = response.get('data', {})
            return f"✅ Multi-step form completed: {collected_data}"
        return "❌ Multi-step form cancelled"
```

### Data Visualization Component

```python
class ChartTool(BaseUITool):
    def get_component_config(self, data):
        return {
            'component_type': 'AgentChart',
            'chart_type': data.get('chart_type', 'bar'),
            'data': data.get('data', []),
            'title': data.get('title', 'Generated Chart'),
            'interactive': True
        }
    
    def process_ui_response(self, response, data):
        if response.get('status') == 'interaction':
            clicked_data = response.get('data', {}).get('clicked_point')
            return f"✅ User clicked on data point: {clicked_data}"
        return "📊 Chart displayed successfully"
```

## 🔧 Advanced Patterns

### Conditional Component Rendering

```python
def smart_input_tool(data):
    input_type = data.get('input_type', 'text')
    
    if input_type == 'file':
        return file_upload_tool(data)
    elif input_type == 'choice':
        return choice_tool(data)
    else:
        return text_input_tool(data)
```

### Chained UI Interactions

```python
class ChainedTool(BaseUITool):
    async def _handle_ui_async(self, data):
        # Step 1: Get initial input
        step1_response = await self._get_step_response('step1', {
            'component_type': 'TextInput',
            'title': 'Step 1: Enter Name'
        })
        
        if step1_response.get('status') != 'success':
            return "❌ Step 1 cancelled"
        
        name = step1_response.get('data', {}).get('text')
        
        # Step 2: Confirmation with personalized message
        step2_response = await self._get_step_response('step2', {
            'component_type': 'Confirmation',
            'title': f'Welcome {name}!',
            'message': f'Continue with setup for {name}?'
        })
        
        if step2_response.get('status') == 'confirmed':
            return f"✅ Setup completed for {name}"
        return "❌ Setup cancelled"
```

## 🔒 Security & Validation

### Input Validation

```python
def process_ui_response(self, response, data):
    if response.get('status') == 'success':
        value = response.get('data', {}).get('value', '')
        
        # Validate input
        if len(value) < 3:
            return "❌ Input too short (minimum 3 characters)"
        
        if not value.isalnum():
            return "❌ Only alphanumeric characters allowed"
        
        return f"✅ Valid input: {value}"
    return "❌ Input cancelled"
```

### Sanitization

```python
import html
import re

def sanitize_input(self, raw_input):
    # HTML escape
    sanitized = html.escape(raw_input)
    
    # Remove potential script tags
    sanitized = re.sub(r'<script.*?</script>', '', sanitized, flags=re.IGNORECASE)
    
    # Limit length
    sanitized = sanitized[:1000]
    
    return sanitized.strip()
```

## 🐛 Debugging & Troubleshooting

### Enable Debug Logging

Use a context-aware logger for your component or tool:

```python
from logs.logging_config import get_workflow_logger

logger = get_workflow_logger("my_ui_tool")
logger.info("Debug logging enabled for my_ui_tool")
```

### Common Issues

1. **Tool not appearing**: Check `tools.json` (or legacy `tools.yaml`) registration
2. **UI not rendering**: Verify component name matches frontend
3. **Async errors**: Ensure proper sync/async bridge usage
4. **Response timeout**: Increase timeout in `wait_for_ui_tool_response`

### Debugging Output

```python
def get_component_config(self, data):
    config = {
        'component_type': 'MyComponent',
        'debug': True,  # Enable debug mode in frontend
        'data': data
    }
    
    self.logger.debug(f"Component config: {config}")
    return config
```

## 🚀 Deployment Tips

1. **Frontend Registration**: Ensure all UI components are registered in your frontend router
2. **Error Boundaries**: Wrap UI components in error boundaries for graceful failures
3. **Loading States**: Show loading indicators while waiting for responses
4. **Timeout Handling**: Provide clear feedback when interactions timeout
5. **Mobile Responsive**: Ensure components work on mobile devices

## 📈 Performance Optimization

1. **Lazy Loading**: Load UI components only when needed
2. **Caching**: Cache component configurations for repeated use
3. **Batch Operations**: Combine multiple UI interactions when possible
4. **Async Non-Blocking**: Never block the main thread

This architecture gives you **unlimited possibilities** for agent-generated UI components while maintaining clean separation between AG2 and your custom frontend logic! 🎯
