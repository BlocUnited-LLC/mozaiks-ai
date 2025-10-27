"""
Phase 1: Add CONTEXT VARIABLE INTEGRATION to UIFileGenerator
Teaches generated UI tools how to read/write context variables via runtime dict.
"""
from pathlib import Path
import json

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read file
with open(agents_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find UIFileGenerator and add context integration section
ui_gen = data['agents']['UIFileGenerator']
system_msg = ui_gen['system_message']

# Find insertion point - after [CONTEXT] section, before [GUIDELINES]
marker = "[CONTEXT VARIABLE INTEGRATION]"

if marker in system_msg:
    print("⚠️  [CONTEXT VARIABLE INTEGRATION] already exists in UIFileGenerator")
else:
    # New section to add
    new_section = """[CONTEXT VARIABLE INTEGRATION]
You must understand how context variables flow through the system:

1. INPUTS FROM CONTEXT (Not Conversation):
   - `action_plan` (dict): Read workflow structure from context, NOT from chat history
   - `context_variables_plan` (dict): Schema defining all context variables
   - Tools manifest: Defines which tools you're generating

2. TOOLS YOU GENERATE MUST:
   - Read context variables in their **runtime parameter
   - Example: context_variables = runtime.get('context_variables', {})
   - Document in docstrings which context variables the tool depends on
   - Set context flags after user interactions (UI tools only)

3. DEFENSIVE CONTEXT ACCESS:
   - Always check if context variable exists before reading
   - Provide safe defaults when variables missing
   - Never assume context structure - validate all access paths

"""

    # Find insertion point - after [SEQUENCE POSITION] section
    insertion_marker = "[AUTHORIZED INPUT SOURCES]"
    if insertion_marker in system_msg:
        parts = system_msg.split(insertion_marker, 1)
        system_msg = parts[0] + new_section + "\n" + insertion_marker + parts[1]
        ui_gen['system_message'] = system_msg
        
        # Write back
        with open(agents_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print("✅ Successfully added [CONTEXT VARIABLE INTEGRATION] to UIFileGenerator")
        print("\nKey additions:")
        print("- Context variable reading pattern from runtime dict")
        print("- Tool generation contract for context access")
        print("- Defensive context access requirements")
    else:
        print(f"❌ Could not find insertion marker: {insertion_marker}")
