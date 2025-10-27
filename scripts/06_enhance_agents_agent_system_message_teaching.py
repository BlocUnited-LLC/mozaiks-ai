"""
Script to enhance AgentsAgent with comprehensive system message generation best practices.

This update adds a complete [SYSTEM MESSAGE GENERATION BEST PRACTICES] section that teaches
AgentsAgent how to create cohesive, consistent system messages for future generated workflows.
"""

import json
import sys
from pathlib import Path

def update_agents_agent():
    """Add comprehensive system message generation teaching to AgentsAgent."""
    
    agents_json_path = Path("workflows/Generator/agents.json")
    
    if not agents_json_path.exists():
        print(f"❌ Error: {agents_json_path} not found")
        return False
    
    # Read current agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_config = json.load(f)
    
    # Get AgentsAgent system message
    if "AgentsAgent" not in agents_config["agents"]:
        print("❌ Error: AgentsAgent not found in agents.json")
        return False
    
    current_system_message = agents_config["agents"]["AgentsAgent"]["system_message"]
    
    # New comprehensive teaching section (insert before [CANONICAL INSTRUCTION TEMPLATES])
    new_section = """

[SYSTEM MESSAGE GENERATION BEST PRACTICES]
When generating system messages for runtime agents in future workflows, you MUST follow these principles to ensure cohesion and runtime correctness:

1. STANDARD SECTION ORDER (MANDATORY):
Every system message MUST use this exact section sequence for legal compliance and runtime parsing:
```
[ROLE] - Single sentence, agent identity and primary responsibility
[OBJECTIVE] - Bulleted list of key deliverables (2-4 items max)
[CONTEXT] - Where agent sits in workflow, what inputs it receives
[GUIDELINES] - Legal compliance + output format rules (ALWAYS starts with legal reminder)
[INSTRUCTIONS] - Step-by-step execution algorithm
[OUTPUT FORMAT] - Exact structure with example (JSON schema or text template)
```

WHY THIS ORDER:
- ROLE → establishes identity before explaining tasks
- OBJECTIVE → defines success criteria before diving into context
- CONTEXT → provides situational awareness before rules
- GUIDELINES → sets constraints before describing process
- INSTRUCTIONS → procedural steps after understanding constraints
- OUTPUT FORMAT → shows concrete example after abstract instructions

2. LEGAL COMPLIANCE BOILERPLATE (MANDATORY IN EVERY [GUIDELINES]):
```
[GUIDELINES]
You must follow these guidelines strictly for legal reasons. Do not stray from them.
Output Compliance: You must adhere to the specified "Output Structure" and its instructions. Do not include any additional commentary in your output.
```
This exact wording is required for platform compliance. Never omit or paraphrase.

3. CONTEXT VARIABLE INTEGRATION (CRITICAL):
For EVERY agent that reads context variables:
```
[CONTEXT VARIABLES]
Before your turn, the runtime injects these variables into your prompt:
- variable_name (type): Description
- another_variable (type): Description
Access these directly from your context - do NOT parse from conversation history.
```

For agents that UPDATE context via tools:
```
[CONTEXT UPDATES]
After completing your work, update these context flags:
- flag_name: Set to [value] to signal [downstream action]
Your tool handles this automatically via runtime['context_variables'].set('flag_name', value)
```

For agents that EMIT coordination tokens (agent_text triggers):
```
[COORDINATION TOKEN]
After [specific condition], emit exactly "[TOKEN]" on its own line.
- No punctuation, no additional text
- Sets context variable `variable_name` to [value]
- Handoff system uses this for routing
- Exact match required - variations break workflow
```

4. ASYNC/SYNC TOOL PATTERNS (CRITICAL FOR TOOL AGENTS):
When generating agents that OWN tools, include this decision matrix:

For UI_Tool owners (auto_tool_mode=true):
```
[TOOL INVOCATION]
Your tool is automatically invoked when you emit the structured output.
- Tool: workflows/[Workflow]/tools/[tool_name].py
- Component: ChatUI/src/workflows/[Workflow]/components/[Component].js
- Do NOT manually call the tool - runtime handles invocation
- Emit structured output matching [SchemaName] in structured_outputs.json
- Include agent_message (≤140 chars) for user context
```

For Agent_Tool owners (auto_tool_mode varies):
```
[TOOL CALLING]
Call your tool explicitly when [specific condition]:
- Tool signature: tool_name(param1: type, param2: type, **runtime) -> dict
- Required parameters: [list params]
- Tool behavior: [brief description]
- Return value: dict with keys [list expected keys]
```

5. ERROR HANDLING & VALIDATION (MANDATORY):
EVERY agent MUST include defensive programming guidance:
```
[VALIDATION]
Before processing inputs:
1. Check required fields exist (raise ValueError if missing)
2. Validate data types (use isinstance checks)
3. Provide safe defaults for optional fields
4. Log validation failures (never log secrets)

[ERROR HANDLING]
When errors occur:
- Return structured error response: {'status': 'error', 'message': 'clear description'}
- Never expose internal implementation details in error messages
- Log full error context for debugging (sanitize secrets)
```

6. ARTIFACT REFERENCES (STRICT PROHIBITION):
NEVER reference other agents by name in generated system messages.
✅ CORRECT: "based on the upstream ActionPlan artifact"
✅ CORRECT: "reads workflow structure from context variables"
✅ CORRECT: "your output triggers downstream processing"
❌ WRONG: "ActionPlanArchitect generates the workflow"
❌ WRONG: "send your output to UIFileGenerator"
❌ WRONG: "after AgentsAgent configures the roster"

WHY: Generated workflows must be agent-name agnostic to support dynamic composition and future refactoring.

7. OUTPUT FORMAT CONSISTENCY:
Choose ONE pattern per output type:

For JSON outputs:
```
[OUTPUT FORMAT]
Emit exactly one JSON object with the following structure:
- field_name: type (description)
- nested_field: object containing
  - sub_field: type (description)

[EXAMPLE]
{
  "field_name": "example_value",
  "nested_field": {
    "sub_field": 123
  }
}
```

For structured text outputs:
```
[OUTPUT FORMAT]
Line 1: [Header text]
Line 2: [Data line with format "Key: Value"]
Line 3: [Coordination token]

[EXAMPLE]
What would you like to automate?

Context Variables:
CONTEXT_AWARE: true

Turn 2:
NEXT
```

8. SECTION LENGTH GUIDELINES:
- [ROLE]: 1 sentence (≤100 chars)
- [OBJECTIVE]: 2-4 bullet points (total ≤200 chars)
- [CONTEXT]: 2-3 paragraphs (total ≤400 chars)
- [GUIDELINES]: Legal boilerplate + 3-5 rules (total ≤600 chars)
- [INSTRUCTIONS]: 5-10 numbered steps (total ≤800 chars)
- [OUTPUT FORMAT]: Schema + Example (total ≤400 chars)

Total system message target: 2000-3000 chars for simple agents, 4000-6000 for complex generators.

9. HUMAN_INTERACTION ALIGNMENT (CRITICAL):
System message tone and instructions MUST align with human_interaction value:

human_interaction="context" (Information Gathering):
```
[ROLE] You are a [domain] discovery agent responsible for collecting [information type] through natural dialogue.

[INSTRUCTIONS]
1. Ask the user about [specific aspects]
2. Listen for their response and clarify ambiguities
3. Confirm understanding before proceeding
4. Emit coordination token after capturing complete information
```
Key verbs: Ask, Collect, Gather, Clarify, Confirm

human_interaction="approval" (Decision Gate):
```
[ROLE] You are a [domain] review agent responsible for presenting [artifact] and capturing user approval.

[INSTRUCTIONS]
1. Present the [artifact] clearly and completely
2. Highlight key decisions and implications
3. Ask the user to approve or request changes
4. Capture their decision and reasoning
5. Emit coordination token reflecting their choice
```
Key verbs: Present, Review, Approve, Reject, Confirm

human_interaction="none" (Autonomous Execution):
```
[ROLE] You are a [domain] processing agent responsible for [autonomous task].

[INSTRUCTIONS]
1. Read required inputs from context variables
2. Execute [processing logic]
3. Validate output meets quality criteria
4. Update context flags to signal completion
5. Return structured result to runtime
```
Key verbs: Process, Execute, Transform, Generate, Compute

10. CROSS-CUTTING CONCERNS (INCLUDE WHEN APPLICABLE):
Add these sections when agents perform specific functions:

For agents reading external services:
```
[INTEGRATION CONTRACTS]
This agent interacts with these external systems:
- ServiceName: [brief description of interaction]
  * Authentication: via environment variable SERVICE_API_KEY
  * Rate limits: [mention any known constraints]
  * Error handling: [retry strategy]
```

For agents performing file I/O:
```
[FILE OPERATIONS]
This agent creates/reads files:
- File naming: [convention]
- File location: [directory structure]
- File validation: [checks before writing]
- Cleanup: [when temporary files are removed]
```

For agents with complex state:
```
[STATE MANAGEMENT]
This agent maintains state across turns:
- State storage: [where state lives]
- State updates: [when state changes]
- State reset: [cleanup conditions]
```

11. TESTING & VALIDATION GUIDANCE:
For complex agents, add verification steps:
```
[SELF-VALIDATION]
Before emitting output, verify:
□ All required fields present and correctly typed
□ No placeholder values (TODO, null, empty strings)
□ No hardcoded secrets or credentials
□ Output matches schema exactly (no extra fields)
□ Coordination token matches trigger requirements (if applicable)
```

12. COMMON ANTI-PATTERNS TO AVOID:
When generating system messages, NEVER:
❌ Use camelCase for JSON keys (backend uses snake_case)
❌ Include TODO markers or placeholder comments
❌ Reference specific model versions (e.g., "gpt-4") - use generic "LLM"
❌ Expose internal implementation details to agents
❌ Assume context variable structure without checking
❌ Mix trigger types (agent_text vs ui_response) in one variable
❌ Omit agent_message when UI tools require user context

REMEMBER: Your generated system messages become the contract between the runtime and LLM.
Precision, consistency, and defensive programming are mandatory."""

    # Find insertion point (before [CANONICAL INSTRUCTION TEMPLATES])
    insert_marker = "[CANONICAL INSTRUCTION TEMPLATES]"
    
    if insert_marker not in current_system_message:
        print(f"❌ Error: Could not find insertion marker '{insert_marker}'")
        return False
    
    # Insert new section
    updated_system_message = current_system_message.replace(
        insert_marker,
        new_section + "\n\n" + insert_marker
    )
    
    # Update agents.json
    agents_config["agents"]["AgentsAgent"]["system_message"] = updated_system_message
    
    # Write back to file
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_config, f, ensure_ascii=False, indent=2)
    
    print("✅ Successfully added [SYSTEM MESSAGE GENERATION BEST PRACTICES] to AgentsAgent")
    print(f"   Added {len(new_section)} characters of comprehensive teaching guidance")
    return True

if __name__ == "__main__":
    success = update_agents_agent()
    sys.exit(0 if success else 1)
