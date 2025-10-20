"""
Script to enhance agents.json with proper context variable coordination
and remove explicit agent name references.
"""
import json
import re

# Load the current agents.json
with open('workflows/Generator/agents.json', 'r', encoding='utf-8') as f:
    agents_data = json.load(f)

# Define transformations for each agent
transformations = {
    'InterviewAgent': {
        'replacements': [
            ('routes to ActionPlanArchitect', 'routes control to the downstream planning agent'),
            ('HandoffsAgent routes to ActionPlanArchitect', 'Handoff system routes to downstream agent'),
            ('Defined in ContextVariablesPlan and enforced by handoffs.json', 'Defined in context variables schema and enforced by handoff routing rules'),
        ]
    },
    'ActionPlanArchitect': {
        'add_section_after': '[CONTEXT VARIABLE COORDINATION]',
        'new_content': '''
You integrate with the runtime context system which manages shared workflow state:

1. REVISION DETECTION (Pre-Execution):
   - BEFORE generating, check if `action_plan` context variable exists
   - IF EXISTS → REVISION mode: apply user's changes to existing workflow only
   - IF NOT EXISTS → NEW PLAN mode: create from scratch
   - The action_plan tool caches your output and sets flags for downstream coordination

2. CONTEXT FLAGS YOUR OUTPUT SETS (via action_plan tool):
   - `action_plan` (dict): Your normalized workflow cached for downstream agents
   - `diagram_ready` (bool): Signals that planning is complete
   - Downstream agents read these flags to proceed with their responsibilities

3. DOWNSTREAM COORDINATION:
   - Your output triggers the diagram generation phase
   - After diagram + user review, `action_plan_acceptance` flag controls routing
   - Handoffs depend on context flags being set correctly by the action_plan tool
''',
        'replacements': [
            ('set by ActionPlanArchitect via action_plan tool', 'set by upstream planning via action_plan tool'),
            ('triggers ProjectOverviewAgent', 'triggers downstream diagram generation'),
            ('triggers downstream agents (ContextVariablesAgent)', 'triggers downstream context schema definition'),
            ('triggers handoff back to ActionPlanArchitect for revisions', 'triggers revision cycle back to planning'),
        ]
    },
    'ProjectOverviewAgent': {
        'replacements': [
            ('set by ActionPlanArchitect via action_plan tool', 'set by upstream planning via action_plan tool'),
            ('triggers downstream agents (ContextVariablesAgent)', 'triggers downstream context schema definition'),
            ('triggers handoff back to ActionPlanArchitect for revisions', 'triggers revision cycle back to upstream planning'),
        ]
    },
    'ContextVariablesAgent': {
        'add_context': '''

[CONTEXT VARIABLE USAGE IN DOWNSTREAM AGENTS]
Your ContextVariablesPlan output is consumed by all remaining downstream agents:

1. TOOLS MANAGER AGENT:
   - Reads action_plan from context to generate tools.json manifest
   - Maps operations → Agent_Tool, UI responsibilities → UI_Tool
   - Your agent exposure mappings determine which agents get which variables

2. UI/AGENT TOOL FILE GENERATORS:
   - Read action_plan and tools manifest from context
   - Generate tool code that reads/writes context variables you define
   - Tool docstrings reference context variables by name

3. AGENTS AGENT (System Message Generator):
   - Reads your ContextVariablesPlan to determine trigger tokens
   - Generates system messages teaching runtime agents how to:
     * Read context variables injected before their turn
     * Emit coordination tokens that update derived variables
     * Understand when UI tool responses update context flags
   - CRITICAL: Your trigger definitions become instructions in generated agent prompts

4. HANDOFFS AGENT:
   - Reads your derived variables with triggers
   - Generates routing expressions checking context flags
   - Your trigger.type (agent_text vs ui_response) determines condition_scope

EXAMPLE FLOW:
- You define: interview_complete (derived, agent_text trigger, match.equals="NEXT")
- Agents Agent generates: "Emit exactly 'NEXT' on its own line after user responds"
- Handoffs Agent generates: condition="${interview_complete} == True", scope=null
- Runtime: Interview agent emits "NEXT" → DerivedContextManager sets flag → handoff fires
''',
        'replacements': [
            ('Example: interview_complete set to True when InterviewAgent emits "NEXT"', 'Example: interview_complete set to True when intake agent emits "NEXT"'),
            ('HandoffsAgent reads your ContextVariablesPlan', 'Downstream routing agent reads your ContextVariablesPlan'),
        ]
    },
    'ToolsManagerAgent': {
        'replacements': [
            ('Your manifest is consumed by UIFileGenerator and AgentToolsFileGenerator', 'Your manifest is consumed by downstream code generation agents'),
            ('You execute after ContextVariablesAgent completes', 'You execute after upstream context schema definition completes'),
        ]
    },
    'UIFileGenerator': {
        'add_section': '''

[CONTEXT VARIABLE INTEGRATION]
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
''',
        'replacements': [
            ('Locate ActionPlan JSON ({\"ActionPlan\": {\"workflow\": {...}}}) for workflow context', 'Read action_plan from context variables (set by upstream planning tool)'),
            ('Locate ContextVariablesPlan JSON ({\"ContextVariablesPlan\": {...}}) if referencing variables', 'Read context_variables_plan from context (set by upstream context schema agent)'),
        ]
    },
    'AgentToolsFileGenerator': {
        'add_section': '''

[CONTEXT VARIABLE INTEGRATION]
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
''',
        'replacements': [
            ('ActionPlan ({\"ActionPlan\": {\"workflow\": {...}}})', 'action_plan from context variables'),
            ('optional context to understand general responsibilities', 'workflow structure from context (if needed)'),
        ]
    },
    'AgentsAgent': {
        'add_critical_section': '''

[CONTEXT VARIABLE TEACHING RESPONSIBILITY]
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
''',
        'replacements': [
            ('HandoffsAgent reads your ContextVariablesPlan', 'Downstream routing generator reads your ContextVariablesPlan'),
            ('InterviewAgent', 'intake agent'),
            ('ActionPlanArchitect', 'planning agent'),
            ('ContextVariablesAgent', 'context schema agent'),
        ]
    },
    'StructuredOutputsAgent': {
        'replacements': [
            ('ActionPlanArchitect', 'planning agent'),
            ('InterviewAgent', 'intake agent'),
        ]
    },
    'HandoffsAgent': {
        'replacements': [
            ('InterviewAgent', 'intake agent'),
            ('ActionPlanArchitect', 'planning agent'),
            ('ContextVariablesAgent', 'context schema agent'),
            ('ProjectOverviewAgent', 'diagram generation agent'),
        ]
    },
}

# Apply transformations
for agent_name, transform in transformations.items():
    if agent_name not in agents_data['agents']:
        continue
    
    system_message = agents_data['agents'][agent_name]['system_message']
    
    # Apply replacements
    if 'replacements' in transform:
        for old, new in transform['replacements']:
            system_message = system_message.replace(old, new)
    
    # Add new sections
    if 'add_section' in transform:
        # Find appropriate insertion point (after [CONTEXT] or [OBJECTIVE])
        insertion_point = system_message.find('[GUIDELINES]')
        if insertion_point == -1:
            insertion_point = system_message.find('[CONTEXT]')
        if insertion_point > 0:
            system_message = system_message[:insertion_point] + transform['add_section'] + '\n\n' + system_message[insertion_point:]
    
    if 'add_context' in transform:
        # Add after existing content
        system_message = system_message + transform['add_context']
    
    if 'add_critical_section' in transform:
        # Add after [GUIDELINES] section
        insertion_point = system_message.find('[CANONICAL INSTRUCTION TEMPLATES]')
        if insertion_point > 0:
            system_message = system_message[:insertion_point] + transform['add_critical_section'] + '\n\n' + system_message[insertion_point:]
    
    agents_data['agents'][agent_name]['system_message'] = system_message

# Save the updated agents.json
with open('workflows/Generator/agents.json', 'w', encoding='utf-8') as f:
    json.dump(agents_data, f, indent=2, ensure_ascii=False)

print("✓ Successfully updated agents.json with context variable coordination")
print("✓ Removed explicit agent name references")
print("✓ Added context awareness to downstream agents")
print("✓ Enhanced AgentsAgent with context variable teaching responsibility")
