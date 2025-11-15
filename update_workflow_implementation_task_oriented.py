"""
Update WorkflowImplementationAgent INSTRUCTIONS section to:
1. Align with WorkflowStrategyAgent (human_in_loop) and WorkflowArchitectAgent (ui_components)
2. Clarify the three-layer interaction model:
   - WorkflowStrategy.human_in_loop = Strategic intent (does PHASE need human participation?)
   - TechnicalBlueprint.ui_components = UI surface contracts (WHAT interactions exist, WHERE they render)
   - WorkflowAgent.human_interaction = Agent execution mode (HOW this specific agent involves humans)
3. Provide clear decision logic for human_interaction based on ui_components.interaction_pattern
4. Task-oriented language throughout
"""

import json
from pathlib import Path

# Load agents.json
agents_path = Path("workflows/Generator/agents.json")
with open(agents_path, "r", encoding="utf-8") as f:
    agents_data = json.load(f)

# Find WorkflowImplementationAgent
workflow_implementation_agent = agents_data["agents"]["WorkflowImplementationAgent"]

# Find INSTRUCTIONS section
for section in workflow_implementation_agent["prompt_sections"]:
    if section["id"] == "instructions":
        # Update with improved instructions
        section["content"] = """**UNDERSTANDING THE THREE-LAYER INTERACTION MODEL**

Before you design agents, understand how human interaction is represented across the workflow:

**Layer 1 - Strategic Intent (WorkflowStrategy.human_in_loop)**:
- Set by: Upstream strategy agent
- Type: Boolean per phase
- Meaning: "Does this PHASE require human participation?"
- Purpose: High-level planning signal for downstream agents
- Example: Phase 2 has human_in_loop=true → Someone needs to interact during Phase 2

**Layer 2 - UI Surface Contracts (TechnicalBlueprint.ui_components)**:
- Set by: Upstream architecture agent
- Type: Array of WorkflowUIComponent objects
- Meaning: "WHAT UI surfaces exist, WHERE they render, HOW users interact"
- Purpose: Binding contracts that define specific UI tools agents must use
- Example: Phase 2 has ui_component with agent="ReviewAgent", tool="submit_approval", display="artifact", interaction_pattern="two_step_confirmation"

**Layer 3 - Agent Execution Mode (WorkflowAgent.human_interaction)**:
- Set by: YOU (this agent)
- Type: "none" | "context" | "approval" per agent
- Meaning: "HOW does THIS SPECIFIC AGENT involve humans during execution?"
- Purpose: Runtime behavior control for individual agent instances
- Example: ReviewAgent has human_interaction="approval" → This agent pauses for human decision

**YOUR JOB**: Translate Layer 1 + Layer 2 → Layer 3 for each agent you design.

---

**Step 1 - Access Context Inputs**:
- Review WorkflowStrategy from context variables (workflow metadata and phases array)
- Review TechnicalBlueprint from context variables (global_context_variables, ui_components, lifecycle hooks)
- Review interview transcript and concept_overview from context variables

**Step 2 - Review Pattern Guidance**:
- Locate the injected [PATTERN GUIDANCE AND EXAMPLES] section at the bottom of your system message
- This section contains:
  * Complete PhaseAgents JSON example for the selected pattern
  * Recommended agent counts and coordination patterns per phase
  * Recommended human_interaction modes based on ui_components
  * Recommended tool naming and integration patterns
- Use the example as a foundation and adapt it to WorkflowStrategy phases and TechnicalBlueprint UI contracts

**Step 2 - Build UI Component Lookup**:
Create mental map: {phase_name → {agent_name → ui_component}}

For EACH entry in TechnicalBlueprint.ui_components:
- Extract: phase_name, agent (PascalCase), tool (snake_case), component, display, interaction_pattern, label, summary
- Store mapping so you can quickly check: "Does agent X in phase Y have a UI Component?"

**Step 3 - Design Agents for Each Phase**:
For EACH phase in WorkflowStrategy.phases:

**4a. Determine Agent Count**:
- Review pattern guidance example for recommended agent count in this phase
- Use WorkflowStrategy.phases[i].agents_needed as guide:
  * "single" → Design 1 agent (handles entire phase alone)
  * "sequential" → Design 2+ agents (execute in order, each handles different step)
  * "nested" → Design 1 coordinator + 2+ specialists (coordinator delegates to specialists)

**4b. Assign Agent Names**:
- Review pattern guidance example for agent naming patterns
- If TechnicalBlueprint.ui_components specifies agent name for this phase → Use that name exactly
- Otherwise: Generate descriptive name based on phase_description (e.g., "ContentGenerator", "DataAnalyzer", "NotificationSender")
- Ensure uniqueness across ALL phases (no duplicate agent names in entire workflow)

**3c. Determine Human Interaction Mode**:
For EACH agent you design, apply this decision tree:

**CHECK**: Does this agent have a ui_component entry?
- Look up in TechnicalBlueprint.ui_components where phase_name matches AND agent matches

**IF NO UI Component**:
→ Set human_interaction="none"
→ Agent runs backend logic without human involvement

**IF UI Component EXISTS**, check interaction_pattern:
- interaction_pattern="single_step" → human_interaction="context" (user provides data, agent continues)
- interaction_pattern="two_step_confirmation" → human_interaction="approval" (user reviews and approves)
- interaction_pattern="multi_step" → human_interaction="approval" (iterative review/refinement)

**KEY INSIGHT**: ui_component.display controls WHERE UI renders; interaction_pattern controls HOW user interacts and determines human_interaction mode

**KEY INSIGHT**: 
- ui_component.display ("inline" vs "artifact") controls WHERE UI renders (chat flow vs side panel)
- ui_component.interaction_pattern controls HOW user interacts (single input vs approval vs wizard)
- human_interaction is derived FROM interaction_pattern, NOT from display mode

**Step 5 - Build Agent Tool Specifications**:
For EACH agent, define agent_tools array:

**IF agent has UI Component**:
- name: Use EXACT tool name from ui_component.tool
- integration: Third-party service if applicable, otherwise null
- purpose: What tool accomplishes (<=140 chars)
- interaction_mode: Match ui_component.display ("inline" | "artifact")

**IF agent has NO UI Component**:
- Review pattern guidance example for tool naming patterns
- Generate descriptive snake_case names based on phase operations
- integration: Real service name (OpenAI, Stripe, Slack, etc.) or null
- purpose: Brief explanation (<=140 chars)
- interaction_mode: "none"

**Step 5 - Build Complete Agent Specifications**:
For EACH agent, construct WorkflowAgent object:
- agent_name: PascalCase unique identifier
- description: Comprehensive role description including:
  * Agent's primary responsibility
  * When agent executes in workflow sequence
  * What tools agent uses and when to call them
  * How agent interprets tool results
  * What agent produces as output
- agent_tools: Array of AgentTool objects (from Step 4)
- lifecycle_tools: Array of LifecycleTool objects (only if TechnicalBlueprint specifies before_agent/after_agent hooks for this agent, otherwise empty array [])
- system_hooks: Array of SystemHook objects (usually empty [] unless agent needs runtime behavior modification)
- human_interaction: "none" | "context" | "approval" (from Step 3c decision tree)

**Step 6 - Validate Phase Agents Output**:
Before emitting JSON, verify:
- ✅ phase_agents.length == WorkflowStrategy.phases.length (one entry per phase)
- ✅ phase_agents[i].phase_index == i (sequential 0-based indexing)
- ✅ Every phase has at least 1 agent in agents array
- ✅ Agent count matches agents_needed:
  * "single" → 1 agent
  * "sequential" → 2+ agents
  * "nested" → 1 coordinator + 2+ specialists
- ✅ For EACH phase where WorkflowStrategy.phases[i].human_in_loop=true:
  * At least ONE agent in that phase has human_interaction="context" OR "approval" (NOT all "none")
- ✅ For EACH ui_component in TechnicalBlueprint:
  * Corresponding agent exists with matching name
  * Agent has tool with matching tool name
  * Agent has human_interaction="context" or "approval" (NOT "none")
- ✅ All agent names are PascalCase and unique across entire workflow
- ✅ All tool names are snake_case
- ✅ All integrations are real service names (PascalCase) or null

**Step 7 - Emit Structured Output**:
- Generate PhaseAgentsOutput JSON exactly as described in [OUTPUT FORMAT]
- Structure: {"PhaseAgents": [{"phase_index": 0, "agents": [...]}, {"phase_index": 1, "agents": [...]}, ...]}
- Include ALL required fields for each WorkflowAgent object
- NO markdown fences, NO explanatory prose, ONLY the JSON object"""
        print("✓ Updated WorkflowImplementationAgent INSTRUCTIONS section")
        break

# Save updated agents.json
with open(agents_path, "w", encoding="utf-8") as f:
    json.dump(agents_data, f, indent=2, ensure_ascii=False)

print(f"\n✓ Saved updated agents.json")
print("\n" + "="*80)
print("THREE-LAYER INTERACTION MODEL ALIGNMENT")
print("="*80)
print("\n✓ WorkflowStrategyAgent → human_in_loop (Strategic Intent)")
print("  - Boolean per phase")
print("  - Answers: 'Does this PHASE need human participation?'")
print("  - Set by: WorkflowStrategyAgent based on interview + pattern guidance")
print("\n✓ WorkflowArchitectAgent → ui_components (UI Surface Contracts)")
print("  - Array of WorkflowUIComponent objects")
print("  - Answers: 'WHAT UI surfaces exist? WHERE do they render? HOW do users interact?'")
print("  - Fields: phase_name, agent, tool, component, display, interaction_pattern, label, summary")
print("  - Set by: WorkflowArchitectAgent based on human_in_loop flags + interview requirements")
print("\n✓ WorkflowImplementationAgent → human_interaction (Agent Execution Mode)")
print("  - Enum per agent: 'none' | 'context' | 'approval'")
print("  - Answers: 'HOW does THIS SPECIFIC AGENT involve humans during execution?'")
print("  - Derived FROM: ui_components.interaction_pattern")
print("  - Decision logic:")
print("    * NO ui_component → human_interaction='none'")
print("    * interaction_pattern='single_step' → human_interaction='context'")
print("    * interaction_pattern='two_step_confirmation' → human_interaction='approval'")
print("    * interaction_pattern='multi_step' → human_interaction='approval'")
print("\n" + "="*80)
print("KEY IMPROVEMENTS")
print("="*80)
print("\n1. Clear three-layer conceptual model explained upfront")
print("2. Decision tree for human_interaction based on ui_components.interaction_pattern")
print("3. Validation ensures human_in_loop=true phases have at least one agent with human_interaction≠'none'")
print("4. Clarified display mode (inline vs artifact) affects rendering, NOT interaction type")
print("5. Task-oriented language: Design/Build/Determine/Validate vs Extract/Map/Filter/Draft")
