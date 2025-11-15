"""
Comprehensive alignment of WorkflowStrategyAgent, WorkflowArchitectAgent, and WorkflowImplementationAgent.

ALIGNMENT PRINCIPLES:
1. Never reference specific agent names in conceptual descriptions (use roles/responsibilities)
2. Leverage injected pattern guidance examples (not hardcoded logic)
3. Maintain modular design for any pattern
4. Align semantic context flow across all three agents
5. Task-oriented language throughout
"""

import json
from pathlib import Path

# Load agents.json
agents_path = Path("workflows/Generator/agents.json")
with open(agents_path, "r", encoding="utf-8") as f:
    agents_data = json.load(f)

# =============================================================================
# LAYER 1: WORKFLOW STRATEGY (Strategic Intent)
# =============================================================================

workflow_strategy_agent = agents_data["agents"]["WorkflowStrategyAgent"]
for section in workflow_strategy_agent["prompt_sections"]:
    if section["id"] == "instructions":
        section["content"] = """**Step 1 - Access Context Inputs**:
- Review concept_overview, interview responses, and platform feature flags (CONTEXT_AWARE, MONETIZATION_ENABLED) from context variables
- Review PatternSelection from context variables (contains pattern id and name selected by upstream pattern analysis)

**Step 2 - Review Pattern Guidance**:
- Locate the injected [PATTERN GUIDANCE AND EXAMPLES] section at the bottom of your system message
- This section contains:
  * Complete WorkflowStrategy JSON example for the selected pattern
  * Recommended phase topology (phase names, descriptions, coordination patterns)
  * Guidance on trigger types, human_in_loop flags, and agent coordination styles
- Use the example as a foundation and adapt it to the user's specific automation goal from the interview

**Step 3 - Determine Trigger and Initiator**:
Use the interview transcript and concept_overview to decide how workflow starts:

**trigger** (activation mechanism):
- "chat" → User types message to initiate conversation
- "form_submit" → User submits structured web form
- "schedule" → Time-based activation (cron, daily/weekly automation)
- "database_condition" → Database state change triggers workflow
- "webhook" → External service sends HTTP POST

**initiated_by** (originating actor):
- "user" → Human explicitly starts workflow
- "system" → Platform automatically starts workflow
- "external_event" → Third-party service triggers workflow

**Decision Logic**:
Check pattern guidance example for recommended trigger/initiator, then validate against interview:
- User mentions or their request implies "chat", "conversation", "talk to" → likely trigger="chat", initiated_by="user"
- User mentions or their request implies "form", "submit", "enter data" → likely trigger="form_submit", initiated_by="user"
- User mentions or their request implies "daily", "weekly", "scheduled" → likely trigger="schedule", initiated_by="system"
- User mentions or their request implies "when order placed", "status changes" → likely trigger="database_condition", initiated_by="system"
- User mentions or their request implies "Stripe payment", "Slack message" → likely trigger="webhook", initiated_by="external_event"

**Step 4 - Generate Workflow Metadata**:
- Create workflow_name in Title Case reflecting automation goal (e.g., "Marketing Content Creator", "Customer Support Router")
- Write workflow_description: "When [TRIGGER], workflow [ACTIONS], resulting in [VALUE]"
- Set trigger and initiated_by based on Step 3 decision logic
- Copy pattern name from PatternSelection exactly (e.g., ["Pipeline"], ["Feedback Loop"])

**Step 5 - Create Phase Scaffold**:
Use pattern guidance example as starting topology, then adapt phase descriptions to user's specific goal:

For EACH phase, determine:

**human_in_loop** (Strategic Intent - does this PHASE require human participation?):
- Boolean flag signaling whether humans interact during this phase
- true → Phase requires user input, review, approval, confirmation, or decision
- false → Phase runs fully automated on backend (no human interaction)

**Decision Logic**:
- Check pattern guidance example for recommended human_in_loop values per phase
- Validate against interview content:
  * Phase involves "review", "approve", "decide", "input", "feedback", "confirm", "select" → human_in_loop=true
  * Phase involves "analyze", "process", "generate", "send", "update", "calculate" (backend keywords) → human_in_loop=false
  * If monetization_enabled=true and phase delivers value to end user → human_in_loop=true (user sees results, makes choices)

**IMPORTANT**: human_in_loop is STRATEGIC INTENT, not implementation detail. It signals to downstream agents:
- Architect layer: Create UI Components for phases flagged true
- Implementation layer: Set agent execution modes appropriately

**agents_needed** (coordination pattern):
- "single" → One agent handles entire phase
- "sequential" → Multiple agents execute in sequence (pipeline style)
- "nested" → Coordinator delegates to specialists (hierarchical coordination)

**Decision Logic**:
- Check pattern guidance example for recommended agents_needed per phase
- Validate against phase complexity:
  * Simple, focused task → "single"
  * Multi-step pipeline → "sequential"
  * Requires diverse expertise or coordinator+specialists → "nested"

Generate phases array where each entry contains:
- phase_index: Sequential integer starting at 0
- phase_name: Copy format from pattern guidance ("Phase N: Purpose")
- phase_description: Adapt pattern guidance description to user's specific automation goal
- human_in_loop: Boolean determined by decision logic above
- agents_needed: String determined by decision logic above

**Step 6 - Validate Output Quality**:
- Verify phase_index values increment without gaps (0, 1, 2, ...)
- Confirm phase names follow "Phase N: Purpose" format from pattern guidance
- Check human_in_loop reflects actual human participation requirements
- Ensure trigger and initiated_by match interview signals
- Verify agents_needed aligns with pattern guidance coordination style

**Step 7 - Emit Structured Output**:
- Generate WorkflowStrategyOutput JSON exactly as described in [OUTPUT FORMAT]
- Include workflow_name, workflow_description, trigger, initiated_by, pattern, and phases array
- Do not include lifecycle operations, tool manifests, or agent names (derived downstream)"""
        print("✓ Updated WorkflowStrategyAgent INSTRUCTIONS (Layer 1 - Strategic Intent)")
        break

# =============================================================================
# LAYER 2: TECHNICAL BLUEPRINT (UI Surface Contracts)
# =============================================================================

workflow_architect_agent = agents_data["agents"]["WorkflowArchitectAgent"]
for section in workflow_architect_agent["prompt_sections"]:
    if section["id"] == "instructions":
        section["content"] = """**Step 1 - Access Context Inputs**:
- Review WorkflowStrategy from context variables (contains workflow metadata and phases array)
- Review interview transcript and concept_overview from context variables
- Review PatternSelection from context variables

**Step 2 - Review Pattern Guidance**:
- Locate the injected [PATTERN GUIDANCE AND EXAMPLES] section at the bottom of your system message
- This section contains:
  * Complete TechnicalBlueprint JSON example for the selected pattern
  * Recommended global_context_variables (with type, trigger_hint, purpose)
  * Recommended ui_components (with display modes, interaction patterns)
  * Recommended lifecycle hooks (before_chat, after_chat)
- Use the example as a foundation and adapt it to WorkflowStrategy phases and interview requirements

**Step 3 - Create Global Context Variables**:
Generate global_context_variables array where each entry contains:
- name: Snake_case variable name
- type: "static" | "derived" | "environment" | "database"
- trigger_hint: Simple description of when/how variable gets set, or null
- purpose: What this variable tracks and why it's needed (1-2 sentences)

**Decision Logic**:
- Review pattern guidance example for recommended context variables
- Adapt variable names/purposes to user's specific domain from interview
- If WorkflowStrategy.trigger="form_submit" → Create variables matching form fields
- If WorkflowStrategy.trigger="webhook" → Create "webhook_payload" variable
- If WorkflowStrategy.trigger="schedule" → Create "execution_timestamp" variable
- For phases where human_in_loop=true AND interview mentions or implies approval/decision tracking → Create approval state variables
- For phases where agents_needed="nested" AND interview mentions or implies coordination → Create coordination signal variables

**Step 4 - Define UI Components (UI Surface Contracts)**:
Generate ui_components array where each entry contains:
- phase_name: Must match WorkflowStrategy.phases[].phase_name EXACTLY
- agent: PascalCase agent name that will own this UI tool
- tool: Snake_case tool function name
- label: User-facing CTA or heading
- component: PascalCase React component name
- display: "inline" | "artifact"
  * inline = Embedded in chat flow (small forms, quick inputs)
  * artifact = Side panel rendering (rich content, multi-section forms)
- interaction_pattern: "single_step" | "two_step_confirmation" | "multi_step"
  * single_step = User provides data once, agent continues
  * two_step_confirmation = User reviews content, then approves/rejects
  * multi_step = Progressive wizard or iterative refinement
- summary: <=200 char narrative explaining what user sees/confirms

**Decision Logic**:
- Review pattern guidance example for recommended ui_components
- For EACH phase where WorkflowStrategy.phases[i].human_in_loop=true:
  * Determine if phase needs structured UI beyond plain text chat
  * Check interview for UI interaction requirements
  * If simple data collection → interaction_pattern="single_step", display="inline"
  * If approval workflow → interaction_pattern="two_step_confirmation", display="artifact"
  * If multi-step form → interaction_pattern="multi_step", display based on complexity
- Adapt agent names, tool names, labels from pattern example to user's specific domain

**IMPORTANT**: Chat interface is transport mechanism, NOT a ui_component. Only create ui_components for structured interactions beyond text.

**Step 5 - Decide on Lifecycle Hooks**:
Generate before_chat_lifecycle and after_chat_lifecycle (single objects or null):

**before_chat_lifecycle** (WorkflowLifecycleToolRef or null):
- name: Snake_case lifecycle tool name
- purpose: What the lifecycle tool accomplishes
- trigger: "before_chat" (literal value)
- integration: Third-party service (PascalCase) or null

**Decision Logic**:
- Review pattern guidance example for recommended before_chat hook
- If WorkflowStrategy.trigger="schedule" OR "webhook" → Likely needs initialization hook
- If interview mentions or implies setup, loading config, fetching data before workflow → Include hook
- Otherwise: Set to null

**after_chat_lifecycle** (WorkflowLifecycleToolRef or null):
- name: Snake_case lifecycle tool name
- purpose: What the lifecycle tool accomplishes
- trigger: "after_chat" (literal value)
- integration: Third-party service (PascalCase) or null

**Decision Logic**:
- Review pattern guidance example for recommended after_chat hook
- If final phase mentions or implies reporting, persistence, notification, cleanup → Include hook
- If interview mentions or implies logging, analytics, sending final notifications → Include hook
- Otherwise: Set to null

**Step 6 - Validate Output Quality**:
- For EVERY phase where human_in_loop=true, verify at least one ui_component exists with matching phase_name
- Verify ui_component.phase_name values match WorkflowStrategy.phases[].phase_name EXACTLY
- Check ui_component.summary is <=200 chars
- Verify context variable types use valid values: "static", "derived", "environment", "database"
- If before_chat_lifecycle not null, verify trigger="before_chat"
- If after_chat_lifecycle not null, verify trigger="after_chat"

**Step 7 - Emit Structured Output**:
- Generate TechnicalBlueprintOutput JSON exactly as described in [OUTPUT FORMAT]
- Include global_context_variables, ui_components, before_chat_lifecycle, after_chat_lifecycle
- Do not include agent names, tool manifests, or handoff sequences (derived downstream)"""
        print("✓ Updated WorkflowArchitectAgent INSTRUCTIONS (Layer 2 - UI Surface Contracts)")
        break

# =============================================================================
# LAYER 3: WORKFLOW IMPLEMENTATION (Agent Execution Modes)
# =============================================================================

workflow_implementation_agent = agents_data["agents"]["WorkflowImplementationAgent"]
for section in workflow_implementation_agent["prompt_sections"]:
    if section["id"] == "instructions":
        section["content"] = """**Step 1 - Access Context Inputs**:
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

**Step 3 - Build UI Component Lookup**:
Create mental map: {phase_name → {agent_name → ui_component}}

For EACH entry in TechnicalBlueprint.ui_components:
- Extract: phase_name, agent, tool, component, display, interaction_pattern, label, summary
- Store mapping for quick lookup during agent design

**Step 4 - Design Agents for Each Phase**:
For EACH phase in WorkflowStrategy.phases:

**4a. Determine Agent Count**:
- Review pattern guidance example for recommended agent count in this phase
- Use WorkflowStrategy.phases[i].agents_needed as guide:
  * "single" → Design 1 agent
  * "sequential" → Design 2+ agents executing in sequence
  * "nested" → Design 1 coordinator + 2+ specialists

**4b. Assign Agent Names**:
- Review pattern guidance example for agent naming patterns
- If TechnicalBlueprint.ui_components specifies agent name for this phase → Use exactly
- Otherwise: Generate PascalCase name based on phase_description (e.g., "ContentGenerator", "DataAnalyzer")
- Ensure uniqueness across ALL phases

**4c. Determine Human Interaction Mode**:
For EACH agent, apply decision tree:

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

**Step 6 - Build Complete Agent Specifications**:
For EACH agent, construct WorkflowAgent object:
- agent_name: PascalCase unique identifier
- description: Comprehensive role description (what agent does, when it executes, what tools it uses)
- agent_tools: Array of AgentTool objects (from Step 5)
- lifecycle_tools: Array of LifecycleTool objects (empty [] unless TechnicalBlueprint specifies before_agent/after_agent hooks)
- system_hooks: Array of SystemHook objects (empty [] unless agent needs runtime behavior modification)
- human_interaction: "none" | "context" | "approval" (from Step 4c decision tree)

**Step 7 - Validate Phase Agents Output**:
- Verify phase_agents.length == WorkflowStrategy.phases.length
- Verify phase_agents[i].phase_index == i (sequential 0-based)
- Verify every phase has at least 1 agent
- Verify agent count matches agents_needed recommendations
- For EACH phase where human_in_loop=true:
  * At least ONE agent has human_interaction="context" OR "approval" (NOT all "none")
- For EACH ui_component in TechnicalBlueprint:
  * Corresponding agent exists with matching name
  * Agent has tool with matching tool name
  * Agent has human_interaction="context" or "approval"
- All agent names are PascalCase and unique
- All tool names are snake_case
- All integrations are real services or null

**Step 8 - Emit Structured Output**:
- Generate PhaseAgentsOutput JSON exactly as described in [OUTPUT FORMAT]
- Structure: {"PhaseAgents": [{"phase_index": 0, "agents": [...]}, ...]}
- Include ALL required fields for each WorkflowAgent
- NO markdown fences, NO prose, ONLY JSON"""
        print("✓ Updated WorkflowImplementationAgent INSTRUCTIONS (Layer 3 - Agent Execution Modes)")
        break

# Save updated agents.json
with open(agents_path, "w", encoding="utf-8") as f:
    json.dump(agents_data, f, indent=2, ensure_ascii=False)

print(f"\n✓ Saved updated agents.json")
print("\n" + "="*80)
print("THREE-LAYER SEMANTIC ALIGNMENT")
print("="*80)
print("\n✅ LAYER 1: WorkflowStrategy (Strategic Intent)")
print("   - Output: workflow metadata + phases with human_in_loop flags")
print("   - Leverages: Injected pattern guidance examples (complete WorkflowStrategy JSON)")
print("   - Adapts: Example topology to user's specific automation goal")
print("   - Signals: human_in_loop=true tells downstream to create UI Components")
print("\n✅ LAYER 2: TechnicalBlueprint (UI Surface Contracts)")
print("   - Input: WorkflowStrategy phases + interview requirements")
print("   - Output: global_context_variables + ui_components + lifecycle hooks")
print("   - Leverages: Injected pattern guidance examples (complete TechnicalBlueprint JSON)")
print("   - Adapts: Variable names, UI labels, agent names to user's domain")
print("   - Signals: interaction_pattern determines downstream human_interaction mode")
print("\n✅ LAYER 3: PhaseAgents (Agent Execution Modes)")
print("   - Input: WorkflowStrategy phases + TechnicalBlueprint UI contracts")
print("   - Output: phase_agents with human_interaction modes and tool specifications")
print("   - Leverages: Injected pattern guidance examples (complete PhaseAgents JSON)")
print("   - Adapts: Agent names, tool purposes, coordination to specific workflow")
print("   - Derives: human_interaction from ui_components.interaction_pattern")
print("\n" + "="*80)
print("KEY PRINCIPLES")
print("="*80)
print("\n1. ✅ NO agent name references in conceptual descriptions (role-based only)")
print("2. ✅ Pattern guidance injection provides complete JSON examples per pattern")
print("3. ✅ Agents adapt examples to user's specific domain from interview")
print("4. ✅ Modular design works for any pattern (1-9)")
print("5. ✅ Semantic context flows: Strategy → Blueprint → Implementation")
print("6. ✅ Task-oriented language throughout (Review/Adapt/Generate vs Extract/Map/Filter)")
