# Workflow-Specific UI Components Developer Guide

## 🎯 Overview

This guide shows developers how to create custom UI components for specific workflows. Each workflow can have its own UI tools and frontend components while sharing the same robust core infrastructure.

## 🏗️ Architecture

```
Core System (Shared)           Workflow-Specific (Custom)
├── WorkflowUITool            ←→ MyWorkflow/tools/my_tool.py
├── UIEventRouter             ←→ MyWorkflow/components/MyComponent.js
├── SimpleTransport           ←→ tools.yaml registration
└── Event Management          ←→ Agent usage
```

## 🚀 Quick Start: Create a Workflow UI Tool

### Step 1: Create the Backend Tool

Create your tool in `workflows/{WorkflowName}/tools/my_custom_tool.py`:

```python
# workflows/MyWorkflow/tools/my_custom_tool.py
from core.ui_tools import WorkflowUITool
from typing import Dict, Any

class CustomFormTool(WorkflowUITool):
    def __init__(self):
        super().__init__(
            workflow_name="MyWorkflow",           # Your workflow name
            tool_name="custom_form",              # Tool identifier
            ui_tool_id="custom_form_component"    # Frontend component ID
        )
    
    def get_component_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Define what data gets sent to your frontend component"""
        return {
            'component_type': 'CustomFormComponent',  # React component name
            'title': data.get('title', 'Custom Form'),
            'fields': data.get('fields', []),
            'description': data.get('description', 'Please fill out this form'),
            'required': data.get('required', True),
            'workflow_specific_data': {
                'theme': 'MyWorkflow',
                'validation_rules': data.get('validation', {})
            }
        }
    
    def process_ui_response(self, response: Dict[str, Any], original_data: Dict[str, Any]) -> str:
        """Process the user's response from the frontend"""
        status = response.get('status', 'unknown')
        
        if status == 'success':
            form_data = response.get('data', {}).get('form_data', {})
            # Process the form data as needed
            return f"✅ Form submitted successfully with {len(form_data)} fields"
        elif status == 'cancelled':
            return "❌ Form was cancelled by user"
        else:
            return f"❌ Form failed with status: {status}"

# Export the function for tools.yaml registration
custom_form_tool = CustomFormTool()

def get_custom_form(data: Dict[str, Any]) -> str:
    """Function that agents can call to show custom form"""
    return custom_form_tool(data)
```

### Step 2: Create the Frontend Component

Create your React component in `ChatUI/src/workflows/{WorkflowName}/components/CustomFormComponent.js`:

```javascript
// ChatUI/src/workflows/MyWorkflow/components/CustomFormComponent.js
import React, { useState } from 'react';

const CustomFormComponent = ({ 
  payload, 
  onResponse, 
  onCancel,
  ui_tool_id,
  eventId,
  workflowName 
}) => {
  const [formData, setFormData] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    title = "Custom Form",
    description = "",
    fields = [],
    workflow_specific_data = {}
  } = payload || {};

  const handleFieldChange = (fieldName, value) => {
    setFormData(prev => ({
      ...prev,
      [fieldName]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (isSubmitting) return;
    setIsSubmitting(true);

    try {
      // Send response to backend
      const response = await fetch('/api/ui-tool/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: eventId,
          ui_tool_id,
          status: 'success',
          data: { form_data: formData }
        })
      });

      if (response.ok) {
        // Notify parent component
        onResponse?.({
          status: 'success',
          data: { form_data: formData }
        });
      } else {
        throw new Error('Failed to submit form');
      }
    } catch (error) {
      console.error('Form submission error:', error);
      onResponse?.({
        status: 'error',
        error: error.message
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    onCancel?.({ status: 'cancelled' });
  };

  return (
    <div className={`custom-form ${workflow_specific_data.theme || ''}`}>
      <div className="form-header">
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>

      <form onSubmit={handleSubmit}>
        {fields.map((field, index) => (
          <div key={index} className="form-field">
            <label htmlFor={field.name}>
              {field.label}
              {field.required && <span className="required">*</span>}
            </label>
            
            {field.type === 'text' && (
              <input
                id={field.name}
                type="text"
                value={formData[field.name] || ''}
                onChange={(e) => handleFieldChange(field.name, e.target.value)}
                placeholder={field.placeholder}
                required={field.required}
              />
            )}
            
            {field.type === 'select' && (
              <select
                id={field.name}
                value={formData[field.name] || ''}
                onChange={(e) => handleFieldChange(field.name, e.target.value)}
                required={field.required}
              >
                <option value="">Select...</option>
                {field.options?.map((option, idx) => (
                  <option key={idx} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
            
            {field.type === 'textarea' && (
              <textarea
                id={field.name}
                value={formData[field.name] || ''}
                onChange={(e) => handleFieldChange(field.name, e.target.value)}
                placeholder={field.placeholder}
                required={field.required}
                rows={field.rows || 3}
              />
            )}
          </div>
        ))}

        <div className="form-actions">
          <button 
            type="submit" 
            disabled={isSubmitting}
            className="submit-btn"
          >
            {isSubmitting ? 'Submitting...' : 'Submit'}
          </button>
          <button 
            type="button" 
            onClick={handleCancel}
            className="cancel-btn"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
};

CustomFormComponent.displayName = 'CustomFormComponent';

export default CustomFormComponent;
```

### Step 3: Register the Tool

Add to your workflow's `tools.yaml`:

```yaml
# workflows/MyWorkflow/tools.yaml
get_custom_form:
  description: "Show custom form UI to collect user input"
  enabled: true
```

### Step 4: Use in Your Workflow

Your agents can now call this tool:

```python
# In your agent's system message or workflow logic
result = get_custom_form({
    'title': 'Project Details',
    'description': 'Please provide project information',
    'fields': [
        {
            'name': 'project_name',
            'label': 'Project Name',
            'type': 'text',
            'required': True,
            'placeholder': 'Enter project name...'
        },
        {
            'name': 'project_type',
            'label': 'Project Type',
            'type': 'select',
            'required': True,
            'options': [
                {'value': 'web', 'label': 'Web Application'},
                {'value': 'mobile', 'label': 'Mobile App'},
                {'value': 'api', 'label': 'API Service'}
            ]
        },
        {
            'name': 'description',
            'label': 'Description',
            'type': 'textarea',
            'placeholder': 'Describe your project...',
            'rows': 4
        }
    ],
    'chat_id': current_chat_id
})
```

## 🎨 Real-World Examples

### Example 1: File Upload Tool

```python
# workflows/Generator/tools/file_upload.py
class FileUploadTool(WorkflowUITool):
    def __init__(self):
        super().__init__("Generator", "file_upload", "file_upload_component")
    
    def get_component_config(self, data):
        return {
            'component_type': 'FileUploadComponent',
            'title': 'Upload Files for Processing',
            'accepted_types': ['.py', '.js', '.json', '.md'],
            'max_files': data.get('max_files', 5),
            'max_size_mb': 10
        }
    
    def process_ui_response(self, response, data):
        if response.get('status') == 'success':
            files = response.get('data', {}).get('uploaded_files', [])
            return f"✅ Uploaded {len(files)} files for processing"
        return "❌ File upload cancelled"
```

### Example 2: Code Preview Tool

```python
# workflows/Generator/tools/code_preview.py
class CodePreviewTool(WorkflowUITool):
    def __init__(self):
        super().__init__("Generator", "code_preview", "code_preview_component")
    
    def get_component_config(self, data):
        return {
            'component_type': 'CodePreviewComponent',
            'title': 'Generated Code Preview',
            'code_files': data.get('code_files', []),
            'language': data.get('language', 'python'),
            'editable': data.get('editable', True)
        }
    
    def process_ui_response(self, response, data):
        if response.get('status') == 'approved':
            return "✅ Code approved by user - proceeding with execution"
        elif response.get('status') == 'modified':
            changes = response.get('data', {}).get('modifications', {})
            return f"✅ Code modified by user - {len(changes)} files changed"
        return "❌ Code preview cancelled"
```

### Example 3: Workflow Dashboard

```python
# workflows/Analytics/tools/dashboard.py
class DashboardTool(WorkflowUITool):
    def __init__(self):
        super().__init__("Analytics", "dashboard", "analytics_dashboard")
    
    def get_component_config(self, data):
        return {
            'component_type': 'AnalyticsDashboard',
            'title': 'Analytics Dashboard',
            'charts': data.get('charts', []),
            'filters': data.get('filters', {}),
            'real_time': data.get('real_time', False)
        }
    
    def process_ui_response(self, response, data):
        if response.get('status') == 'filter_changed':
            filters = response.get('data', {}).get('filters')
            return f"✅ Dashboard filters updated: {filters}"
        return "📊 Dashboard interaction complete"
```

## 🔧 Advanced Patterns

### Multi-Step Workflows

```python
class MultiStepWizardTool(WorkflowUITool):
    def get_component_config(self, data):
        return {
            'component_type': 'MultiStepWizard',
            'steps': [
                {'id': 'basic', 'title': 'Basic Info', 'fields': ['name', 'email']},
                {'id': 'details', 'title': 'Details', 'fields': ['bio', 'skills']},
                {'id': 'review', 'title': 'Review', 'fields': []}
            ],
            'current_step': data.get('current_step', 0)
        }
    
    def process_ui_response(self, response, data):
        step_data = response.get('data', {})
        current_step = step_data.get('current_step', 0)
        
        if response.get('status') == 'step_completed':
            return f"✅ Step {current_step + 1} completed"
        elif response.get('status') == 'wizard_completed':
            return "✅ Wizard completed successfully"
        return "❌ Wizard cancelled"
```

### Dynamic Component Loading

```python
class DynamicUITool(WorkflowUITool):
    def get_component_config(self, data):
        ui_type = data.get('ui_type', 'form')
        
        component_map = {
            'form': 'DynamicFormComponent',
            'chart': 'DynamicChartComponent',
            'table': 'DynamicTableComponent',
            'editor': 'DynamicEditorComponent'
        }
        
        return {
            'component_type': component_map.get(ui_type, 'GenericComponent'),
            'dynamic_config': data.get('config', {}),
            'ui_type': ui_type
        }
```

### Conditional UI Logic

```python
class ConditionalUITool(WorkflowUITool):
    def get_component_config(self, data):
        user_role = data.get('user_role', 'user')
        
        if user_role == 'admin':
            return {
                'component_type': 'AdminPanel',
                'permissions': ['create', 'update', 'delete'],
                'advanced_features': True
            }
        else:
            return {
                'component_type': 'UserPanel',
                'permissions': ['view'],
                'advanced_features': False
            }
```

## 🎯 Frontend Component Patterns

### Standard Props Every Component Gets

```javascript
const MyComponent = ({ 
  payload,          // Your tool's component config
  onResponse,       // Function to send response back
  onCancel,         // Function to cancel interaction
  ui_tool_id,       // Unique identifier for this tool
  eventId,          // Unique identifier for this interaction
  workflowName      // Name of the workflow this belongs to
}) => {
  // Your component logic here
};
```

### Standard Response Pattern

```javascript
const handleSuccess = (data) => {
  onResponse({
    status: 'success',
    data: data
  });
};

const handleError = (error) => {
  onResponse({
    status: 'error',
    error: error.message
  });
};

const handleCancel = () => {
  onResponse({
    status: 'cancelled'
  });
};
```

### Loading States

```javascript
const [isProcessing, setIsProcessing] = useState(false);

const handleSubmit = async (data) => {
  setIsProcessing(true);
  try {
    // Process data
    onResponse({ status: 'success', data });
  } catch (error) {
    onResponse({ status: 'error', error: error.message });
  } finally {
    setIsProcessing(false);
  }
};
```

## 🚀 Testing Your UI Tools

### Backend Testing

```python
# Test your tool directly
from workflows.MyWorkflow.tools.my_tool import get_custom_form

test_data = {
    'title': 'Test Form',
    'fields': [{'name': 'test', 'type': 'text', 'required': True}],
    'chat_id': 'test_123'
}

result = get_custom_form(test_data)
print(f"Result: {result}")
```

### Frontend Testing

```javascript
// Test your component in isolation
import MyComponent from './MyComponent';

const testPayload = {
  title: 'Test Component',
  custom_data: 'test_value'
};

const TestWrapper = () => (
  <MyComponent
    payload={testPayload}
    onResponse={(response) => console.log('Response:', response)}
    onCancel={() => console.log('Cancelled')}
    ui_tool_id="test_component"
    eventId="test_event_123"
    workflowName="TestWorkflow"
  />
);
```

## 📁 File Structure

```
Your Workflow Structure:
workflows/
└── MyWorkflow/
    ├── tools/
    │   ├── __init__.py
    │   ├── tools.yaml
    │   ├── my_ui_tool.py
    │   └── another_tool.py
    └── agents.yaml

Your Frontend Structure:
ChatUI/src/workflows/
└── MyWorkflow/
    ├── components/
    │   ├── MyComponent.js
    │   ├── AnotherComponent.js
    │   └── index.js (exports all components)
    └── styles/
        └── MyWorkflow.css
```

## 🔒 Best Practices

### Security
- Always validate user input in `process_ui_response`
- Sanitize data before processing
- Use HTTPS for all API calls
- Implement proper error boundaries

### Performance  
- Lazy load components when possible
- Use React.memo for expensive components
- Debounce user input for real-time features
- Cache component configurations

### UX/UI
- Always show loading states
- Provide clear error messages
- Make cancel buttons easily accessible
- Use consistent styling across workflow components

### Testing
- Test tools independently before integration
- Create test payloads for all component variations
- Test timeout scenarios
- Test error handling paths

This modular system gives you **unlimited possibilities** for creating workflow-specific UI tools while maintaining a clean, scalable architecture! 🎯
