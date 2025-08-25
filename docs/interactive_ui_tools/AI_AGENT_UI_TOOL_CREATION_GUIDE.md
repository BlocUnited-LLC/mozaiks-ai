# AI Agent UI Tool Creation Guide

## 🎯 MISSION: Create Interactive UI Tools for MozaiksAI

You are an AI agent tasked with creating interactive UI tools for the MozaiksAI platform. Your job is to analyze user requirements and create **two files** that work together to provide interactive agent capabilities.

## 📋 REQUIREMENTS ANALYSIS

### Step 1: Determine if UI Component is Needed

Ask yourself these questions:
- **Does this require user input?** (API keys, text, selections, confirmations)
- **Does this involve user decision-making?** (approvals, choices, reviews)
- **Does this benefit from visual interaction?** (code editing, data visualization, file selection)
- **Would this be better than just text?** (forms vs chat messages)

If YES to any: Create a UI component. If NO: Suggest a regular function instead.

### Step 2: Choose Component Type

**INLINE Components** (display="inline"):
- ✅ Simple inputs (text, passwords, numbers)
- ✅ Confirmations and dialogs
- ✅ Quick selections (dropdowns, radio buttons)
- ✅ File uploads (single files)
- ✅ Forms (5 fields or less)

**ARTIFACT Components** (display="artifact"):
- ✅ Code editors
- ✅ Document viewers/editors
- ✅ Data tables
- ✅ Image viewers
- ✅ Complex forms (6+ fields)
- ✅ Multi-step workflows

### Step 3: Generate Tool Name

**CRITICAL**: Tool name must contain UI trigger words for automatic detection:

**Inline triggers**: `input`, `confirm`, `select`, `upload`, `download`, `form`
**Artifact triggers**: `editor`, `viewer`, `artifact`, `document`

**Examples**:
- ✅ `api_key_input` (detected as UI tool)
- ✅ `file_selector` (detected as UI tool)
- ✅ `code_editor_artifact` (detected as UI tool + artifact)
- ❌ `get_data` (NOT detected as UI tool)

## 🐍 PYTHON FILE TEMPLATE

```python
# ==============================================================================
# FILE: tools/ui_tools/{TOOL_NAME}.py
# DESCRIPTION: {Brief description of what this tool does}
# ==============================================================================

from typing import Dict, Any, Optional, List, Union
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response


async def {FUNCTION_NAME}(
    # Core parameters (what the tool needs to work)
    {REQUIRED_PARAM}: {TYPE},
    {OPTIONAL_PARAM}: Optional[{TYPE}] = None,
    
    # Standard UI parameters (always include these)
    chat_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None
) -> {RETURN_TYPE}:
    \"\"\"
    {Detailed description of what this tool does}
    
    This tool creates an interactive UI component that allows users to {specific action}.
    
    Args:
        {PARAM}: {Description}
        chat_id: Current chat session ID
        title: Optional title for the UI component
        description: Optional description text
        
    Returns:
        {Description of return value}
        
    Raises:
        ValueError: If required inputs are missing or invalid
    \"\"\"
    
    # Prepare the UI component payload
    payload = {
        # Core data that the UI component needs
        "{DATA_KEY}": {REQUIRED_PARAM},
        
        # UI configuration
        "title": title or "{Default Title}",
        "description": description or "{Default description}",
        
        # Component-specific props
        "component_props": {
            "type": "{COMPONENT_TYPE}",  # e.g., "input", "confirmation", "editor"
            "validation": {
                # Add validation rules if needed
                "required": True,
                "min_length": 1,
                # "pattern": r"regex_pattern",
                # "max_value": 100,
            },
            "ui_options": {
                # UI customization options
                "placeholder": "{Placeholder text}",
                "theme": "default",
                # Add component-specific options
            }
        },
        
        # Metadata for debugging/tracking
        "metadata": {
            "tool_name": "{FUNCTION_NAME}",
            "created_by": "ai_agent",
            "component_category": "{CATEGORY}"  # input, dialog, editor, viewer, etc.
        }
    }
    
    # Determine component type based on complexity
    display_type = "inline"  # Default
    if "{ARTIFACT_INDICATOR}" in "{FUNCTION_NAME}":  # editor, viewer, document, artifact
        display_type = "artifact"
    
    # Emit the UI tool event
    event_id = await emit_ui_tool_event(
        tool_id="{FUNCTION_NAME}",
        payload=payload,
        display=display_type,
        chat_id=chat_id,
        workflow_name="interactive_tools"
    )
    
    # Wait for user response
    response = await wait_for_ui_tool_response(event_id)
    
    # Process and validate response
    if response.get("cancelled", False):
        # Handle cancellation appropriately
        raise ValueError("User cancelled the operation")
    
    # Extract and validate the main result
    result = response.get("{EXPECTED_RESPONSE_KEY}")
    
    if not result and "{IS_REQUIRED}":
        raise ValueError("{Error message for missing required data}")
    
    # Return structured result
    return {RETURN_VALUE}


# AG2 tool registration helper
def get_tool_config() -> Dict[str, Any]:
    \"\"\"Return tool configuration for AG2 registration\"\"\"
    return {
        "function": {FUNCTION_NAME},
        "description": "{Brief description for AG2}",
        "parameters": {
            "type": "object",
            "properties": {
                "{PARAM_NAME}": {
                    "type": "{JSON_SCHEMA_TYPE}",
                    "description": "{Parameter description}"
                },
                # Add more parameters as needed
            },
            "required": ["{REQUIRED_PARAMS}"]
        }
    }
```

## ⚛️ REACT COMPONENT TEMPLATE

```javascript
// ==============================================================================
// FILE: tools/ui_tools/{TOOL_NAME}.js
// DESCRIPTION: React component for {TOOL_NAME} (pairs with {TOOL_NAME}.py)
// ==============================================================================

import React, { useState, useEffect } from 'react';

/**
 * {Component Description}
 * 
 * This component pairs with tools/ui_tools/{TOOL_NAME}.py to provide
 * interactive {functionality description}.
 * 
 * Props:
 * - payload: Data from the Python tool
 * - onResponse: Callback to send data back to agent
 * - onCancel: Callback for cancellation
 */
const {ComponentName} = ({ 
  payload = {}, 
  onResponse = () => {},
  onCancel = () => {} 
}) => {
  // Extract data from payload
  const {
    {DATA_KEY} = '{DEFAULT_VALUE}',
    title = '{Default Title}',
    description = '',
    component_props = {},
    metadata = {}
  } = payload;

  const { 
    validation = {},
    ui_options = {},
    type = '{COMPONENT_TYPE}'
  } = component_props;

  // Component state
  const [userInput, setUserInput] = useState('{INITIAL_STATE}');
  const [isValid, setIsValid] = useState(false);
  const [error, setError] = useState('');

  // Validation logic
  useEffect(() => {
    validateInput(userInput);
  }, [userInput]);

  const validateInput = (value) => {
    setError('');
    
    // Required validation
    if (validation.required && !value.trim()) {
      setError('{Field} is required');
      setIsValid(false);
      return;
    }
    
    // Length validation
    if (validation.min_length && value.length < validation.min_length) {
      setError(`Minimum length is ${validation.min_length} characters`);
      setIsValid(false);
      return;
    }
    
    // Pattern validation
    if (validation.pattern && !new RegExp(validation.pattern).test(value)) {
      setError('Invalid format');
      setIsValid(false);
      return;
    }
    
    // Add more validation as needed
    
    setIsValid(true);
  };

  const handleSubmit = () => {
    if (!isValid) return;
    
    // Send response back to Python tool
    onResponse({
      {RESPONSE_KEY}: userInput,
      valid: true,
      cancelled: false,
      metadata: {
        interaction_time: Date.now(),
        component_type: type
      }
    });
  };

  const handleCancel = () => {
    onResponse({
      cancelled: true,
      reason: 'user_cancelled'
    });
  };

  // Render inline component
  if ('{DISPLAY_TYPE}' === 'inline') {
    return (
      <div className="{TOOL_NAME}-container p-4 border rounded-lg bg-gray-50 max-w-md">
        <h3 className="text-lg font-semibold mb-2 text-gray-800">
          {title}
        </h3>
        
        {description && (
          <p className="text-sm text-gray-600 mb-4">
            {description}
          </p>
        )}

        <div className="mb-4">
          {/* Main input/interaction element */}
          <input
            type="{INPUT_TYPE}"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            placeholder={ui_options.placeholder}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          
          {error && (
            <p className="text-red-500 text-sm mt-1">{error}</p>
          )}
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleSubmit}
            disabled={!isValid}
            className="flex-1 bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Submit
          </button>
          
          <button
            onClick={handleCancel}
            className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-100"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // Render artifact component
  return (
    <div className="{TOOL_NAME}-artifact bg-white border rounded-lg shadow-lg overflow-hidden max-w-4xl">
      {/* Header */}
      <div className="bg-gray-50 border-b px-4 py-3">
        <h3 className="text-lg font-semibold text-gray-800">{title}</h3>
        {description && (
          <p className="text-sm text-gray-600 mt-1">{description}</p>
        )}
      </div>

      {/* Main content area */}
      <div className="p-4">
        {/* Add your artifact content here */}
        {/* For editors: <textarea>, for viewers: <div>, etc. */}
      </div>

      {/* Footer with actions */}
      <div className="bg-gray-50 border-t px-4 py-3">
        <div className="flex gap-2 justify-end">
          <button
            onClick={handleSubmit}
            disabled={!isValid}
            className="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600 disabled:bg-gray-300"
          >
            Save
          </button>
          <button
            onClick={handleCancel}
            className="border border-gray-300 px-4 py-2 rounded-md hover:bg-gray-100"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default {ComponentName};

// Component metadata for the dynamic UI system
export const componentMetadata = {
  name: '{TOOL_NAME}',
  type: '{DISPLAY_TYPE}',  // 'inline' or 'artifact'
  description: '{Component description}',
  pythonTool: 'tools.ui_tools.{TOOL_NAME}.{FUNCTION_NAME}',
  category: '{CATEGORY}',  // input, dialog, editor, viewer, form, etc.
};
```

## 🔧 REPLACEMENT RULES

When creating files, replace these placeholders:

**{TOOL_NAME}**: snake_case name (e.g., `api_key_input`)
**{FUNCTION_NAME}**: Python function name (usually same as tool name)
**{ComponentName}**: PascalCase component name (e.g., `ApiKeyInput`)
**{DISPLAY_TYPE}**: "inline" or "artifact"
**{COMPONENT_TYPE}**: "input", "confirmation", "editor", "viewer", "form", etc.
**{CATEGORY}**: Functional category
**{DATA_KEY}**: Main data field name
**{RESPONSE_KEY}**: Expected response field name
**{INPUT_TYPE}**: HTML input type ("text", "password", "email", etc.)

## 📝 COMMON PATTERNS

### Simple Text Input
```python
# Python
result = response.get("user_input", "").strip()
```
```javascript
// JavaScript  
const [userInput, setUserInput] = useState('');
onResponse({ user_input: userInput, cancelled: false });
```

### Confirmation Dialog
```python
# Python
return response.get("confirmed", False)
```
```javascript
// JavaScript
const handleConfirm = () => onResponse({ confirmed: true });
const handleCancel = () => onResponse({ confirmed: false });
```

### File Upload
```python
# Python
file_data = response.get("file_data")
filename = response.get("filename")
```
```javascript
// JavaScript
const handleFileSelect = (file) => {
  const reader = new FileReader();
  reader.onload = (e) => onResponse({ 
    file_data: e.target.result, 
    filename: file.name 
  });
  reader.readAsText(file);
};
```

### Multi-Step Form
```python
# Python
form_data = response.get("form_data", {})
step_completed = response.get("step", 1)
```
```javascript
// JavaScript
const [currentStep, setCurrentStep] = useState(1);
const [formData, setFormData] = useState({});
onResponse({ form_data: formData, step: currentStep });
```

## ✅ VALIDATION CHECKLIST

Before creating files, verify:

- [ ] Tool name contains UI trigger words
- [ ] Python file imports from `core.workflow.ui_tools`
- [ ] Uses `emit_ui_tool_event` and `wait_for_ui_tool_response`
- [ ] Includes proper error handling and cancellation
- [ ] JavaScript component handles `payload`, `onResponse`, `onCancel`
- [ ] Component exports metadata with correct structure
- [ ] Return types match between Python and JavaScript
- [ ] Validation logic is consistent
- [ ] Component type (inline/artifact) is appropriate

## 🎯 DECISION FRAMEWORK

**When to use INLINE**:
- Quick, focused interactions
- Single purpose (one input, one decision)
- Doesn't require much screen space
- User can complete in <30 seconds

**When to use ARTIFACT**:
- Complex content that benefits from dedicated space
- Multi-step or multi-field interactions
- Content that users might want to reference later
- Editing or viewing substantial data

**Examples by Type**:

| Tool Type | Component Type | Example |
|-----------|----------------|---------|
| API Key Input | Inline | `api_key_input` |
| Simple Confirmation | Inline | `confirm_action` |
| File Upload | Inline | `file_upload_input` |
| Code Editor | Artifact | `code_editor_artifact` |
| Document Viewer | Artifact | `document_viewer_artifact` |
| Data Table | Artifact | `data_table_artifact` |
| Multi-Step Form | Artifact | `complex_form_artifact` |

## 🚀 SUCCESS CRITERIA

Your UI tool is successful if:
1. **Agent Integration**: Works with standard AG2 tool registration
2. **User Experience**: Intuitive and responsive interface
3. **Error Handling**: Graceful handling of cancellations and invalid inputs
4. **Consistent**: Follows the established patterns and naming conventions
5. **Tested**: Can be imported and the metadata is correct

Remember: You're creating tools that make chat interactions more powerful and user-friendly. Focus on solving real user problems with clean, intuitive interfaces.
