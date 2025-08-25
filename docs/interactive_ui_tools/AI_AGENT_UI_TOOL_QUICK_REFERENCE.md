# AI Agent UI Tool Quick Reference

## 🚨 CRITICAL RULES

1. **Tool name MUST contain trigger words**: `input`, `confirm`, `select`, `upload`, `download`, `edit`, `form`, `editor`, `viewer`, `artifact`
2. **Always create TWO files**: `{tool_name}.py` + `{tool_name}.js`
3. **Python imports**: `from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response`
4. **JavaScript props**: `{ payload, onResponse, onCancel }`

## 📋 QUICK DECISION TREE

```
Need UI component?
├─ YES: User input/interaction needed
│  ├─ Simple/Quick? → INLINE component
│  └─ Complex/Large? → ARTIFACT component
└─ NO: Use regular function
```

## 🐍 PYTHON SKELETON

```python
from core.workflow.ui_tools import emit_ui_tool_event, wait_for_ui_tool_response

async def {tool_name}(main_param: str, chat_id: Optional[str] = None) -> {ReturnType}:
    payload = {
        "main_data": main_param,
        "component_props": {"type": "{type}", "validation": {}},
        "metadata": {"tool_name": "{tool_name}"}
    }
    
    display_type = "inline"  # or "artifact" for large components
    event_id = await emit_ui_tool_event("{tool_name}", payload, display_type, chat_id)
    response = await wait_for_ui_tool_response(event_id)
    
    if response.get("cancelled"):
        raise ValueError("User cancelled")
    
    return response.get("result")

def get_tool_config():
    return {"function": {tool_name}, "description": "...", "parameters": {...}}
```

## ⚛️ REACT SKELETON

```javascript
import React, { useState } from 'react';

const {ComponentName} = ({ payload = {}, onResponse = () => {}, onCancel = () => {} }) => {
  const { main_data, component_props = {} } = payload;
  const [userInput, setUserInput] = useState('');

  const handleSubmit = () => {
    onResponse({ result: userInput, cancelled: false });
  };

  return (
    <div className="{tool_name}-container p-4 border rounded-lg">
      {/* UI elements */}
      <button onClick={handleSubmit}>Submit</button>
      <button onClick={() => onResponse({ cancelled: true })}>Cancel</button>
    </div>
  );
};

export default {ComponentName};
export const componentMetadata = {
  name: '{tool_name}',
  type: 'inline', // or 'artifact'
  pythonTool: 'tools.ui_tools.{tool_name}.{tool_name}'
};
```

## 🎯 COMPONENT TYPE SELECTOR

**INLINE** (display="inline"):
- API keys, passwords, simple text
- Yes/No confirmations  
- Dropdowns, radio buttons
- Single file uploads
- Forms with 1-5 fields

**ARTIFACT** (display="artifact"):
- Code/text editors
- Document viewers
- Data tables/grids
- Image/media viewers  
- Complex multi-step forms
- Anything requiring significant screen space

## 🔧 COMMON PATTERNS

### Text Input
```python
# Python
result = response.get("text_input", "").strip()
```
```javascript
// JS
<input value={text} onChange={(e) => setText(e.target.value)} />
onResponse({ text_input: text });
```

### Confirmation
```python
# Python  
return response.get("confirmed", False)
```
```javascript
// JS
<button onClick={() => onResponse({ confirmed: true })}>Yes</button>
<button onClick={() => onResponse({ confirmed: false })}>No</button>
```

### Selection
```python
# Python
selected = response.get("selected_option")
```
```javascript
// JS
<select onChange={(e) => onResponse({ selected_option: e.target.value })}>
```

## 💡 NAMING EXAMPLES

✅ **Good Names** (auto-detected):
- `api_key_input` → input component
- `confirm_delete` → confirmation dialog
- `file_selector` → file picker
- `code_editor_artifact` → code editing artifact
- `data_viewer_artifact` → data display artifact

❌ **Bad Names** (NOT detected):
- `get_user_data` → no trigger words
- `process_file` → regular function
- `analyze_content` → regular function

## 🚀 VALIDATION

Before submitting, check:
- [ ] Tool name has trigger words
- [ ] Python file uses correct imports
- [ ] JavaScript exports componentMetadata
- [ ] Both files handle cancellation
- [ ] Return types match between Python/JS
- [ ] Component type (inline/artifact) is appropriate
