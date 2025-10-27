"""
Phase 1: Add CONTEXT VARIABLE INTEGRATION to AgentToolsFileGenerator
Teaches generated Agent_Tool implementations how to read/write context variables.
"""
from pathlib import Path
import json

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read file
with open(agents_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find AgentToolsFileGenerator and add context integration section
agent_tools_gen = data['agents']['AgentToolsFileGenerator']
system_msg = agent_tools_gen['system_message']

# Check if already exists
marker = "[CONTEXT VARIABLE INTEGRATION]"

if marker in system_msg:
    print("⚠️  [CONTEXT VARIABLE INTEGRATION] already exists in AgentToolsFileGenerator")
else:
    # New section to add
    new_section = """[CONTEXT VARIABLE INTEGRATION]
Tools you generate must properly integrate with the context system:

1. READING CONTEXT VARIABLES:
   - All tools receive **runtime dict containing context_variables
   - Access via: context_variables = runtime.get('context_variables', {})
   - Document which context variables each tool depends on
   - Example docstring: "Depends on context: action_plan (dict), api_credentials (dict)"

2. WRITING CONTEXT VARIABLES:
   - Import: from core.workflow.context_variables import ContextVariables
   - Get instance: context_variables = runtime.get('context_variables')
   - Set values: context_variables.set('flag_name', value)
   - Common pattern: Set completion flags after tool finishes

3. GENERATED CODE TEMPLATE:
async def tool_name(*, param: str, **runtime) -> dict:
    # Read context
    context_vars = runtime.get('context_variables', {})
    action_plan = context_vars.get('action_plan')
    if not action_plan:
        raise ValueError('action_plan not found in context')
    
    # Tool logic here
    result = process(action_plan, param)
    
    # Optionally set context flags
    if 'context_variables' in runtime:
        runtime['context_variables'].set('tool_complete', True)
    
    return {'status': 'success', 'result': result}

"""

    # Find insertion point - after [AUTHORIZED INPUT SOURCES] section
    insertion_marker = "[Defensive Design]"
    if insertion_marker in system_msg:
        parts = system_msg.split(insertion_marker, 1)
        system_msg = parts[0] + new_section + "\n" + insertion_marker + parts[1]
        agent_tools_gen['system_message'] = system_msg
        
        # Write back
        with open(agents_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print("✅ Successfully added [CONTEXT VARIABLE INTEGRATION] to AgentToolsFileGenerator")
        print("\nKey additions:")
        print("- Runtime dict context access pattern")
        print("- Context variable read/write methods")
        print("- Complete generated code template with context handling")
    else:
        print(f"❌ Could not find insertion marker: {insertion_marker}")
