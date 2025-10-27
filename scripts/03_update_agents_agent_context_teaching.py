"""
Phase 1: Add CONTEXT VARIABLE TEACHING RESPONSIBILITY to AgentsAgent
Teaches AgentsAgent how to generate system messages that properly explain context variables to runtime agents.
"""
from pathlib import Path
import json

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read file
with open(agents_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find AgentsAgent and add context teaching section
agents_agent = data['agents']['AgentsAgent']
system_msg = agents_agent['system_message']

# Check if already exists
marker = "[CONTEXT VARIABLE TEACHING RESPONSIBILITY]"

if marker in system_msg:
    print("⚠️  [CONTEXT VARIABLE TEACHING RESPONSIBILITY] already exists in AgentsAgent")
else:
    # New section to add
    new_section = """[CONTEXT VARIABLE TEACHING RESPONSIBILITY]
**CRITICAL**: When you generate system messages for runtime agents, you MUST teach them how to use context variables properly. This is YOUR PRIMARY RESPONSIBILITY.

1. READING CONTEXT VARIABLES:
Add to each agent's system_message:
```
[CONTEXT VARIABLES]
Before your turn, the runtime injects context variables into your prompt. You have access to:
- [List specific variables from ContextVariablesPlan.agents[AgentName].variables]
- Access these values directly - they're already in your context
- Do NOT attempt to parse them from conversation history
```

2. EMITTING COORDINATION TOKENS (for agents with agent_text triggers):
When ContextVariablesPlan shows an agent must emit a token:
```
[COORDINATION TOKEN]
After [specific condition], emit exactly "[TOKEN_VALUE]" on its own line.
- No punctuation, no additional text
- This sets the derived context variable `variable_name` to [expected_value]
- The handoff system uses this flag to route to the next agent
- Token must match exactly - variations will break the workflow
```

3. UI TOOL RESPONSE HANDLING (for agents with UI tools):
When agent has auto_tool_mode=true:
```
[UI TOOL COORDINATION]
Your tool emits a UI artifact and awaits user interaction.
- Tool automatically called when you emit the structured output
- User response updates context variable `variable_name`
- Handoff routing checks this flag before next agent's turn
- You do NOT manually call the tool - runtime handles invocation
```

4. VALIDATION RULES:
- NEVER mention other agent names in generated system messages
- ALWAYS reference "upstream agent", "downstream agent", "your output"
- ALWAYS specify exact token format when coordination token required
- ALWAYS list context variables the agent can read
- NEVER assume context structure - teach defensive access patterns

EXAMPLE GENERATED SYSTEM MESSAGE SNIPPET:
```
[ROLE] You are a workflow planning agent.

[CONTEXT VARIABLES]
You have access to these context variables injected before your turn:
- user_goal (str): The automation goal captured by upstream intake
- concept_overview (str|null): Optional high-level context

[COORDINATION]
After generating your plan, emit exactly "PLAN_COMPLETE" on its own line.
This sets the plan_ready flag and triggers downstream diagram generation.

[INSTRUCTIONS]
1. Read user_goal from context (do NOT parse from conversation)
2. Generate action plan based on user_goal
3. Emit structured output (automatically triggers your tool)
4. Emit coordination token "PLAN_COMPLETE"
```

"""

    # Find insertion point - after [GUIDELINES] section, before [INSTRUCTIONS]
    insertion_marker = "[INSTRUCTIONS]"
    if insertion_marker in system_msg:
        parts = system_msg.split(insertion_marker, 1)
        system_msg = parts[0] + new_section + "\n" + insertion_marker + parts[1]
        agents_agent['system_message'] = system_msg
        
        # Write back
        with open(agents_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print("✅ Successfully added [CONTEXT VARIABLE TEACHING RESPONSIBILITY] to AgentsAgent")
        print("\nKey additions:")
        print("- Context variable reading instructions for runtime agents")
        print("- Coordination token emission patterns")
        print("- UI tool response handling guidance")
        print("- Complete example system message snippet")
    else:
        print(f"❌ Could not find insertion marker: {insertion_marker}")
