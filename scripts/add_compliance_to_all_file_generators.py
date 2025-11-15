#!/usr/bin/env python3
"""
Add comprehensive compliance contract to ALL file generator agents.

Applies the proven pattern to:
- AgentToolsFileGenerator
- HookAgent
"""
import json
from pathlib import Path

def main():
    agents_json_path = Path("workflows/Generator/agents.json")
    
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    agents_dict = agents_data.get('agents', {})
    
    # Compliance contract to add (same for all file generators)
    compliance_contract = """**Critical Output Compliance Requirements:**
- **Output Format**: Provide **only** a valid JSON object matching the schema. **No additional text, markdown, or commentary** is allowed.
- **Real Line Breaks**: Ensure all code in content fields is properly formatted with real line breaks (`\\n`).
- **No Markdown**: Do **not** wrap JSON output in code block markers (e.g., ```json).
- **Escaped Characters**: Only escape necessary characters as per JSON standards:
    - Use `\\"` for double quotes within strings.
    - Use `\\\\` for backslashes.
    - Use valid escape sequences like `\\n`, `\\t`, etc.
    - **Do not** use invalid escape sequences like `\\'`.
- **Exact Formatting**: Generated files must be formatted for disk, without unnecessary modifications.
- **Code Documentation Formatting**: At the top of every class, function, or method, include concise documentation (e.g., docstrings, JSDoc, or equivalent) describing its purpose, parameters, and return values where applicable.
- **Programmatic Parsing**: Output a valid JSON object that can be parsed without modification.
- **No Trailing Garbage**: Output must end immediately after the final closing brace `}`. No additional text, notes, or commentary after the JSON.

"""
    
    # Update AgentToolsFileGenerator
    agent_tools_gen = agents_dict.get('AgentToolsFileGenerator')
    if agent_tools_gen:
        system_message = agent_tools_gen['system_message']
        
        # Find [GUIDELINES] section
        guidelines_idx = system_message.find("[GUIDELINES]")
        if guidelines_idx != -1:
            # Find end of current guidelines (next section marker)
            next_section_markers = ["[OUTPUT]", "[EXAMPLE", "[ALGORITHM]", "[NAMING", "[INSTRUCTIONS]"]
            next_section_idx = len(system_message)
            for marker in next_section_markers:
                idx = system_message.find(marker, guidelines_idx + len("[GUIDELINES]"))
                if idx != -1 and idx < next_section_idx:
                    next_section_idx = idx
            
            # Build new [GUIDELINES] section
            new_guidelines = """[GUIDELINES]
You must follow these guidelines strictly for legal reasons. Do not stray from them.
Output Compliance: You must adhere to the specified \"Output Format\" and its instructions. Do not include any additional commentary in your output.

""" + compliance_contract
            
            before = system_message[:guidelines_idx]
            after = system_message[next_section_idx:]
            agent_tools_gen['system_message'] = before + new_guidelines + after
            print("✅ Updated AgentToolsFileGenerator with compliance contract")
        else:
            print("⚠️  [GUIDELINES] section not found in AgentToolsFileGenerator")
    else:
        print("❌ AgentToolsFileGenerator not found")
    
    # Update HookAgent
    hook_agent = agents_dict.get('HookAgent')
    if hook_agent:
        system_message = hook_agent['system_message']
        
        # Find [GUIDELINES] section
        guidelines_idx = system_message.find("[GUIDELINES]")
        if guidelines_idx != -1:
            # Find end of current guidelines (next section marker)
            next_section_markers = ["[OUTPUT]", "[EXAMPLE", "[ALGORITHM]", "[NAMING", "[INSTRUCTIONS]"]
            next_section_idx = len(system_message)
            for marker in next_section_markers:
                idx = system_message.find(marker, guidelines_idx + len("[GUIDELINES]"))
                if idx != -1 and idx < next_section_idx:
                    next_section_idx = idx
            
            # Build new [GUIDELINES] section
            new_guidelines = """[GUIDELINES]
You must follow these guidelines strictly for legal reasons. Do not stray from them.
Output Compliance: You must adhere to the specified \"Output Structure\" and its instructions. Do not include any additional commentary in your output.

""" + compliance_contract
            
            before = system_message[:guidelines_idx]
            after = system_message[next_section_idx:]
            hook_agent['system_message'] = before + new_guidelines + after
            print("✅ Updated HookAgent with compliance contract")
        else:
            print("⚠️  [GUIDELINES] section not found in HookAgent")
    else:
        print("❌ HookAgent not found")
    
    # Write back
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print("\n✅ All file generator agents updated with compliance contract")
    print("\nKey additions to all file generators:")
    print("  - Critical Output Compliance Requirements section")
    print("  - Real line breaks requirement")
    print("  - No markdown code fences")
    print("  - Escaped characters rules")
    print("  - No trailing garbage rule")

if __name__ == "__main__":
    main()
