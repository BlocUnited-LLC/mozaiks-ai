#!/usr/bin/env python3
"""
Fix UIFileGenerator [OUTPUT FORMAT] section to prevent py_content/js_content confusion.

PROBLEM:
Agent is concatenating both Python and React code into py_content with '---' separator:
{
  "tools": [{
    "tool_name": "my_tool",
    "py_content": "...Python code...\n\n---\n\n...React code..."
  }]
}

SOLUTION:
Add explicit JSON example showing SEPARATE fields:
{
  "tools": [{
    "tool_name": "my_tool",
    "py_content": "...Python code ONLY...",
    "js_content": "...React code ONLY..."
  }]
}
"""
import json
from pathlib import Path

def main():
    agents_json_path = Path("workflows/Generator/agents.json")
    
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    # Find UIFileGenerator (agents.json is a dict keyed by agent name)
    agents_dict = agents_data.get('agents', {})
    if 'UIFileGenerator' not in agents_dict:
        print("❌ UIFileGenerator not found in agents.json")
        return
    
    ui_file_gen = agents_dict['UIFileGenerator']
    print("✓ Found UIFileGenerator")
    
    # Current [OUTPUT FORMAT] section to replace
    old_output_format = """[OUTPUT FORMAT]
Emit exactly one JSON object with the following structure:
- tools: array of objects, each with
  - tool_name: str (snake_case name only, NO path prefix - e.g., "action_plan" not "tools/action_plan.py")
  - py_content: str (complete Python code - runtime constructs path as workflows/{workflow}/tools/{tool_name}.py)
  - js_content: str (complete React code - runtime constructs path as ChatUI/src/workflows/{workflow}/components/{ComponentName}.jsx)

CRITICAL: Do NOT include file paths in tool_name. The runtime automatically determines:
- Backend path: workflows/{workflow_name}/tools/{tool_name}.py
- Frontend path: ChatUI/src/workflows/{workflow_name}/components/{ComponentName}.jsx

You provide ONLY the base name and content. Path construction is handled by workflow_converter.py."""
    
    # New [OUTPUT FORMAT] section with explicit JSON example
    new_output_format = """[OUTPUT FORMAT]
Emit exactly one JSON object with the following structure:
- tools: array of objects, each with
  - tool_name: str (snake_case name only, NO path prefix - e.g., "action_plan" not "tools/action_plan.py")
  - py_content: str (complete Python code ONLY - runtime constructs path as workflows/{workflow}/tools/{tool_name}.py)
  - js_content: str (complete React code ONLY - runtime constructs path as ChatUI/src/workflows/{workflow}/components/{ComponentName}.jsx)

CRITICAL: Do NOT include file paths in tool_name. The runtime automatically determines:
- Backend path: workflows/{workflow_name}/tools/{tool_name}.py
- Frontend path: ChatUI/src/workflows/{workflow_name}/components/{ComponentName}.jsx

You provide ONLY the base name and content. Path construction is handled by workflow_converter.py.

EXAMPLE OUTPUT (shows SEPARATE fields - DO NOT concatenate):
{
  "tools": [
    {
      "tool_name": "my_tool",
      "py_content": "import sys\\nfrom pathlib import Path\\n_tools_dir = Path(__file__).parent\\nif str(_tools_dir) not in sys.path:\\n    sys.path.insert(0, str(_tools_dir))\\nfrom other_tool import helper\\n\\nasync def my_tool(*, param: str, **runtime) -> dict:\\n    payload = {...}\\n    return await use_ui_tool('MyComponent', payload, chat_id=runtime['chat_id'], workflow_name='MyWorkflow')",
      "js_content": "import React from 'react';\\nimport { typography, components } from '../../../styles/artifactDesignSystem';\\n\\nconst MyComponent = ({ payload, onResponse }) => {\\n  return <div>{payload.data}</div>;\\n};\\n\\nexport default MyComponent;"
    }
  ]
}

WRONG (DO NOT DO THIS - concatenating both codes in py_content):
{
  "tools": [{
    "tool_name": "my_tool",
    "py_content": "...Python code...\\n\\n---\\n\\nimport React from 'react'...React code..."
  }]
}"""
    
    # Replace in system message
    if old_output_format in ui_file_gen['system_message']:
        ui_file_gen['system_message'] = ui_file_gen['system_message'].replace(
            old_output_format,
            new_output_format
        )
        print("✓ Updated [OUTPUT FORMAT] section with explicit JSON example")
    else:
        print("❌ Old [OUTPUT FORMAT] section not found - manual fix needed")
        return
    
    # Write back
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print("✅ Updated UIFileGenerator system message in agents.json")
    print("\nKey changes:")
    print("  - Added 'ONLY' emphasis to py_content and js_content descriptions")
    print("  - Added EXAMPLE OUTPUT section showing correct separate fields")
    print("  - Added WRONG section showing what NOT to do (concatenation with ---)")

if __name__ == "__main__":
    main()
