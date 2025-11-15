#!/usr/bin/env python3
"""
Add explicit Python docstring escaping instructions to file generator compliance contracts.

The issue: LLMs are double-escaping Python docstrings inside JSON:
- WRONG: "\\"\\"\\"docstring\\"\\"\\"" (double-escaped)
- RIGHT: "\"\"\"docstring\"\"\"" (single-escaped)

This script adds explicit examples showing correct docstring escaping.
"""
import json
from pathlib import Path

def main():
    agents_json_path = Path("workflows/Generator/agents.json")
    
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    agents_dict = agents_data.get('agents', {})
    
    # New compliance section with explicit docstring examples
    docstring_compliance = """
**Python Docstring Escaping (CRITICAL)**:
When outputting Python code with docstrings inside JSON strings:
- Use SINGLE backslash before quotes: `\\\"\\\"\\\"docstring\\\"\\\"\\\"` → becomes `\"\"\"docstring\"\"\"`
- NOT double backslash: `\\\\\\"\\\\\\"\\\\\\"` (this breaks JSON parsing)
- Example CORRECT JSON:
  ```
  {"py_content": "def func():\\n    \\\"\\\"\\\"This is a docstring\\\"\\\"\\\"\\n    pass"}
  ```
- Example WRONG JSON:
  ```
  {"py_content": "def func():\\n    \\\\\\"\\\\\\"\\\\\\"This is a docstring\\\\\\"\\\\\\"\\\\\\"\\n    pass"}
  ```
"""
    
    # Update all three file generators
    for agent_name in ['UIFileGenerator', 'AgentToolsFileGenerator', 'HookAgent']:
        agent = agents_dict.get(agent_name)
        if not agent:
            print(f"⚠️  {agent_name} not found")
            continue
            
        system_message = agent['system_message']
        
        # Find the compliance section
        compliance_marker = "**Critical Output Compliance Requirements:**"
        compliance_idx = system_message.find(compliance_marker)
        
        if compliance_idx == -1:
            print(f"⚠️  Compliance section not found in {agent_name}")
            continue
        
        # Find the end of the compliance section (next section starts with [)
        end_idx = system_message.find("\n[", compliance_idx + len(compliance_marker))
        
        if end_idx == -1:
            print(f"⚠️  Could not find end of compliance section in {agent_name}")
            continue
        
        # Insert docstring compliance BEFORE the next section
        before = system_message[:end_idx]
        after = system_message[end_idx:]
        agent['system_message'] = before + docstring_compliance + after
        
        print(f"✅ Added docstring escaping instructions to {agent_name}")
    
    # Write back
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print("\n✅ Updated all file generators with docstring escaping guidance")
    print("This should fix the 'Expecting ,, delimiter' JSON parse errors")

if __name__ == "__main__":
    main()
