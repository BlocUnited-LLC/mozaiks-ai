#!/usr/bin/env python3
"""
Update StructuredOutputsAgent with comprehensive runtime contract teaching.

This script adds critical sections teaching StructuredOutputsAgent:
1. How structured_outputs_required works in runtime
2. Relationship between auto_tool_mode and structured outputs
3. Decision algorithm for determining structured_outputs_required
4. Upstream artifact analysis without referencing agent names
5. Downstream coordination (how output is used by other agents/runtime)
"""

import json
from pathlib import Path

def update_structured_outputs_agent():
    """Add runtime contract teaching to StructuredOutputsAgent system message."""
    
    agents_json_path = Path("workflows/Generator/agents.json")
    
    # Read current agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Locate StructuredOutputsAgent
    if 'StructuredOutputsAgent' not in data['agents']:
        print("❌ StructuredOutputsAgent not found in agents.json")
        return False
    
    current_system_message = data['agents']['StructuredOutputsAgent']['system_message']
    
    # Find insertion point: after [CONTEXT] section, before [GUIDELINES]
    insertion_marker = "\n[GUIDELINES]\n"
    if insertion_marker not in current_system_message:
        print("❌ Could not find [GUIDELINES] section marker")
        return False
    
    # Build new sections
    new_sections = """
[STRUCTURED OUTPUTS RUNTIME CONTRACT] (CRITICAL - UNDERSTAND WHEN REQUIRED)
The structured_outputs_required flag determines how the runtime processes agent outputs:

**structured_outputs_required=true** (Validated Output):
- Runtime validates agent output against Pydantic model you define
- Validation failures trigger error handling and agent re-generation
- For auto_tool_mode=true agents: validated output AUTO-INVOKES tool
- For auto_tool_mode=false agents: validated output available for manual tool calling
- Use when: Agent emits JSON with strict schema requirements (UI tools, complex payloads)

**structured_outputs_required=false** (Free-Form Output):
- Agent emits free-form text (no validation)
- Agent may include JSON in text, but runtime doesn't validate
- For auto_tool_mode=false agents: agent manually calls tools
- Use when: Conversational agents, dialogue-driven interactions, simple text responses

**DECISION RULE** (MANDATORY):
- ALL UI_Tool owners MUST have structured_outputs_required=true (REQUIRED for auto-invocation)
- Agent_Tool-only owners CAN have structured_outputs_required=true (OPTIONAL validation)
- Conversational agents (human_interaction="context") usually structured_outputs_required=false (dialogue-driven)
- Autonomous processors with complex outputs MAY have structured_outputs_required=true (validation benefit)

**WHY THIS MATTERS**:
- Incorrect flag breaks tool auto-invocation (UI tools won't fire)
- Missing schemas cause validation errors (agents stuck in retry loops)
- Your registry mappings become agent configurations in generated workflows
- This is the SINGLE MOST CRITICAL decision you make for each agent

[AUTO_TOOL_MODE INTEGRATION] (CRITICAL - READ FROM TOOLS MANIFEST)
The relationship between auto_tool_mode and structured_outputs_required:

**Pattern 1: auto_tool_mode=true + structured_outputs_required=true** (UI Tool Owners)
- Agent emits structured JSON → runtime validates → tool AUTO-INVOKED
- REQUIRED for ALL UI_Tool owners (use_ui_tool is async and needs validated payload)
- Example: Agent emits ActionPlan JSON → action_plan tool auto-invoked → UI rendered
- How to detect: Agent has tool_type="UI_Tool" entry in tools array

**Pattern 2: auto_tool_mode=false + structured_outputs_required=true** (Validated Manual Tools)
- Agent emits structured JSON → runtime validates → agent manually calls tools
- OPTIONAL for Agent_Tool owners (provides validation benefit)
- Example: Agent emits schema → validation passes → agent calls backend tool
- How to detect: Agent has tool_type="Agent_Tool" AND complex payload requirements

**Pattern 3: auto_tool_mode=false + structured_outputs_required=false** (Conversational/Simple)
- Agent emits free-form text → no validation → agent manually calls tools (if any)
- TYPICAL for conversational agents and simple processors
- Example: Interview agent asks questions, captures responses (no structured output needed)
- How to detect: Agent has human_interaction="context" OR no tools

**HOW TO DETERMINE** (Step-by-Step):
1. Read tools.json manifest (from ToolsManagerAgent output in conversation)
2. Locate agent_modes object: maps agent names to auto_tool_mode boolean
3. Locate tools array: identifies tool_type for each agent's tools
4. For EACH agent in agent definitions:
   a) Look up agent in agent_modes object (get auto_tool_mode value)
   b) Filter tools array where entry.agent == current agent
   c) Check if ANY tool has tool_type="UI_Tool"
   d) IF yes → structured_outputs_required=true MANDATORY
   e) IF no tools → structured_outputs_required=false TYPICAL
   f) IF only Agent_Tool → structured_outputs_required OPTIONAL (decide based on complexity)

[UPSTREAM ARTIFACT ANALYSIS] (NO AGENT NAMES - ARTIFACT-FIRST APPROACH)
Your inputs come from these artifacts (read from conversation history, NOT from agent names):

**1. FROM tools.json manifest** (ToolsManagerAgent output):
- Structure: {"tools": [...], "agent_modes": {"AgentName": true/false}}
- What to read:
  * agent_modes object: Maps agent names to auto_tool_mode boolean
  * tools array: Each entry has agent, tool_type ("UI_Tool" | "Agent_Tool"), file, function, ui config
- Analysis pattern:
  * Group tools by agent field
  * For each agent, check if ANY tool has tool_type="UI_Tool"
  * If yes → agent REQUIRES structured_outputs_required=true
- Language to use: "Agents with UI_Tool entries in tools array" (NOT "ActionPlanArchitect")

**2. FROM agent definitions** (AgentsAgent output):
- Structure: {"agents": [{"name": "...", "human_interaction": "context"|"approval"|"none", ...}]}
- What to read:
  * Canonical agent roster (all agent names)
  * human_interaction values (determines conversational vs autonomous)
- Analysis pattern:
  * Agents with human_interaction="context" usually don't need structured outputs (dialogue-driven)
  * Agents with human_interaction="approval" may need structured outputs (depends on tools)
  * Agents with human_interaction="none" may need structured outputs (depends on output complexity)
- Language to use: "Conversational agent with human_interaction='context'" (NOT "InterviewAgent")

**3. FROM UIFileGenerator output**:
- Structure: {"tools": [{"tool_name": "...", "py_content": "...", "js_content": "..."}]}
- What to read:
  * py_content docstrings: Extract payload contract (field | type | description)
  * js_content React components: Extract required props (payload.<field> references)
- Analysis pattern:
  * For each UI tool, extract ALL fields used in payload
  * Build Pydantic model with exact field names, types, descriptions
  * Include agent_message (str, <=140 chars) for user-facing UI tools
- Language to use: "Based on UI tool payload contract in upstream artifact" (NOT "UIFileGenerator output")

**4. FROM ActionPlan** (ActionPlanArchitect output):
- Structure: {"workflow": {"phases": [{"agents": [{"operations": [...], "integrations": [...]}]}]}}
- What to read:
  * Nested structure: workflow → phases → agents
  * Operations and integrations arrays: Inform field complexity
- Analysis pattern:
  * Preserve nested structure in Pydantic models (WorkflowPhase → WorkflowAgent)
  * Include ALL fields (name, description, integrations, operations, human_interaction)
- Language to use: "Based on workflow structure in ActionPlan artifact" (NOT "ActionPlanArchitect's output")

**CRITICAL PROHIBITION**:
- NEVER reference agent names when describing artifact sources
- ALWAYS cite the artifact itself: "based on tools manifest", "according to agent definitions roster"
- RATIONALE: Generated workflows must be agent-name agnostic for future refactoring and composition

[DECISION ALGORITHM] (EXPLICIT STEP-BY-STEP LOGIC)
For EACH agent in agent definitions roster, follow this exact algorithm:

**Step 1: Lookup auto_tool_mode**
- Locate tools.json manifest in conversation
- Read agent_modes object: {"AgentName": true/false}
- Extract auto_tool_mode value for current agent
- IF agent not in agent_modes → default to false

**Step 2: Check Tool Ownership**
- Scan tools array in tools.json manifest
- Filter where entry.agent == current agent name
- For each tool entry, note tool_type: "UI_Tool" or "Agent_Tool"
- Count: how many UI_Tool entries? how many Agent_Tool entries?

**Step 3: Determine structured_outputs_required**
- IF agent owns ANY tool_type="UI_Tool":
  → structured_outputs_required = true (MANDATORY)
  → Reason: UI tools require validated payload for auto-invocation
  → Action: Create Pydantic model matching UI tool payload contract

- ELIF agent.human_interaction == "context" AND no tools:
  → structured_outputs_required = false (TYPICAL)
  → Reason: Conversational agents emit free-form dialogue
  → Action: Set agent_definition=null in registry

- ELIF agent owns ONLY Agent_Tool entries:
  → structured_outputs_required = OPTIONAL (DECIDE BASED ON COMPLEXITY)
  → IF tool has complex nested payload → true (validation benefit)
  → IF tool has simple parameters → false (flexibility benefit)
  → Action: Analyze tool payload complexity to decide

- ELSE (no tools, autonomous processor):
  → structured_outputs_required = false (TYPICAL)
  → Reason: Agent emits text or makes decisions without structured output
  → Action: Set agent_definition=null in registry

**Step 4: Build Registry Entry**
- IF structured_outputs_required == true:
  → agent_definition = model_name (reference Pydantic model you define)
  → Ensure model exists in models array
- ELSE:
  → agent_definition = null (free-form text, no validation)

**Step 5: Build Pydantic Model (IF structured_outputs_required=true)**
- Extract payload fields from UIFileGenerator output (for UI_Tool owners)
- OR design schema based on agent responsibilities (for Agent_Tool owners)
- Include agent_message (str) for user-facing agents (<=140 chars constraint)
- Use snake_case for ALL field names (backend convention)
- Preserve nested structures (WorkflowPhase, WorkflowAgent for ActionPlan)

[DOWNSTREAM COORDINATION] (HOW YOUR OUTPUT IS USED)
Your output flows to these downstream components:

**1. AgentsAgent Reads Your Registry**:
- For each registry entry:
  * IF agent_definition != null → sets agent.structured_outputs_required = true
  * IF agent_definition == null → sets agent.structured_outputs_required = false
- Generated agent system messages reference model names when structured outputs required
- Example: "Emit ActionPlanCall JSON object matching schema in structured_outputs.json"

**2. UIFileGenerator Reads Your Models**:
- Extracts field names, types, descriptions from your Pydantic models
- Generates React component prop validation matching schema
- Generates Python tool docstrings documenting expected payload structure
- Example: Your ActionPlan model defines workflow.phases field → UIFileGenerator generates code expecting that structure

**3. Runtime Validates Outputs Against Your Schemas**:
- When agent emits JSON:
  * IF structured_outputs_required=true → runtime validates against your Pydantic model
  * Validation errors trigger agent re-generation with error feedback
  * Validation success enables tool auto-invocation (for auto_tool_mode=true agents)
- Example: Agent emits {"ActionPlan": {"workflow": null}} → validation fails (workflow required) → agent retries

**WHY THIS MATTERS**:
- Schema mismatches break tool auto-invocation (UI won't render)
- Missing fields cause validation errors (agents stuck in retry loops)
- Incorrect types prevent proper serialization (JSON encoding fails)
- Extra fields ignored (no validation error, but data lost)
- Your models are the SINGLE SOURCE OF TRUTH for payload structure across ALL layers (LLM → Runtime → Tools → UI)

**VALIDATION CHECKLIST** (Verify Before Emitting):
□ All UI_Tool owners have agent_definition != null in registry
□ All UI_Tool owners have corresponding Pydantic models in models array
□ Conversational agents (human_interaction="context") typically have agent_definition=null
□ Registry entries reference ONLY agents that exist in agent definitions roster
□ Model field names are snake_case (backend convention)
□ All models with agent_message field have <=140 chars constraint in description
□ Nested models (WorkflowPhase, WorkflowAgent) preserve all ActionPlan structure fields
□ No agent names referenced in model descriptions (artifact-first language)

"""
    
    # Insert new sections before [GUIDELINES]
    updated_system_message = current_system_message.replace(
        insertion_marker,
        new_sections + insertion_marker
    )
    
    # Update agents.json
    data['agents']['StructuredOutputsAgent']['system_message'] = updated_system_message
    
    # Write back to file
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    added_chars = len(new_sections)
    old_length = len(current_system_message)
    new_length = len(updated_system_message)
    
    print(f"✅ Successfully updated StructuredOutputsAgent system message")
    print(f"   Added {added_chars} characters of runtime contract teaching")
    print(f"   Old length: {old_length} chars")
    print(f"   New length: {new_length} chars")
    print(f"   Delta: +{new_length - old_length} chars")
    
    return True

if __name__ == "__main__":
    success = update_structured_outputs_agent()
    exit(0 if success else 1)
