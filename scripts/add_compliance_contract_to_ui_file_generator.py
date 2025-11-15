#!/usr/bin/env python3
"""
Add comprehensive compliance contract to UIFileGenerator system message.

Based on proven pattern from previous project's file generation agents.
"""
import json
from pathlib import Path

def main():
    agents_json_path = Path("workflows/Generator/agents.json")
    
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    ui_file_gen = agents_data['agents'].get('UIFileGenerator')
    if not ui_file_gen:
        print("❌ UIFileGenerator not found")
        return
    
    # Find [GUIDELINES] section and add compliance contract
    system_message = ui_file_gen['system_message']
    
    # New compliance contract to insert after "[GUIDELINES]" line
    compliance_contract = """[GUIDELINES]
You must follow these guidelines strictly for legal reasons. Do not stray from them.
Output Compliance: You must adhere to the specified \"Output Format\" and its instructions. Do not include any additional commentary in your output.

**Critical Output Compliance Requirements:**
- **Output Format**: Provide **only** a valid JSON object matching the UIFileGeneratorOutput schema. **No additional text, markdown, or commentary** is allowed.
- **Real Line Breaks**: Ensure all code in the `py_content` and `js_content` fields is properly formatted with real line breaks (`\\n`).
- **No Markdown**: Do **not** wrap JSON output in code block markers (e.g., ```json).
- **Escaped Characters**: Only escape necessary characters as per JSON standards:
    - Use `\\"` for double quotes within strings.
    - Use `\\\\` for backslashes.
    - Use valid escape sequences like `\\n`, `\\t`, etc.
    - **Do not** use invalid escape sequences like `\\'`.
- **Exact Formatting**: Generated files must be formatted for disk, without unnecessary modifications.
- **Code Documentation Formatting**: At the top of every class, function, or method, include concise documentation (e.g., docstrings, JSDoc, or equivalent) describing its purpose, parameters, and return values where applicable.
- **Programmatic Parsing**: Output a valid JSON object that can be parsed without modification.
- **Separate Fields**: py_content contains ONLY Python code. js_content contains ONLY React code. **Never concatenate them with `---` or any separator**.
- **No Trailing Garbage**: Output must end immediately after the final closing brace `}`. No additional text, notes, or commentary after the JSON.

"""
    
    # Find where [GUIDELINES] starts
    guidelines_marker = "[GUIDELINES]"
    guidelines_idx = system_message.find(guidelines_marker)
    
    if guidelines_idx == -1:
        print("❌ [GUIDELINES] section not found")
        return
    
    # Find the end of the current guidelines section (next section marker or end of string)
    next_section_markers = ["[OUTPUT]", "[EXAMPLE", "[ALGORITHM]", "[FAILURE"]
    next_section_idx = len(system_message)
    for marker in next_section_markers:
        idx = system_message.find(marker, guidelines_idx + len(guidelines_marker))
        if idx != -1 and idx < next_section_idx:
            next_section_idx = idx
    
    # Replace the [GUIDELINES] section
    before_guidelines = system_message[:guidelines_idx]
    after_guidelines = system_message[next_section_idx:]
    
    ui_file_gen['system_message'] = before_guidelines + compliance_contract + after_guidelines
    
    # Write back
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print("✅ Updated UIFileGenerator with comprehensive compliance contract")
    print("\nKey additions:")
    print("  - Critical Output Compliance Requirements section")
    print("  - Real line breaks requirement")
    print("  - No markdown code fences")
    print("  - Escaped characters rules")
    print("  - Separate fields enforcement (py_content vs js_content)")
    print("  - No trailing garbage rule")

if __name__ == "__main__":
    main()
