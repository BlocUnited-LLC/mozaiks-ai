"""
Update WorkflowArchitectAgent INSTRUCTIONS section to:
1. Align with three-layer interaction model:
   - WorkflowStrategy.human_in_loop = Strategic intent (PHASE needs human participation)
   - TechnicalBlueprint.ui_components = UI surface contracts (WHAT/WHERE/HOW for interactions)
   - WorkflowAgent.human_interaction = Agent execution mode (set by WorkflowImplementationAgent)
2. Mirror WorkflowStrategy structure (explain what context is needed and how to use it)
3. Explicitly reference WorkflowStrategy structured output fields (human_in_loop, agents_needed, etc.)
4. Provide specific decision logic tied to WorkflowStrategy + interview content
5. Clarify ui_components define UI surfaces displayed WITHIN chat, not the chat interface itself
"""

import json
from pathlib import Path

# Load agents.json
agents_path = Path("workflows/Generator/agents.json")
with open(agents_path, "r", encoding="utf-8") as f:
    agents_data = json.load(f)

# Find WorkflowArchitectAgent
workflow_architect_agent = agents_data["agents"]["WorkflowArchitectAgent"]

# Find INSTRUCTIONS section
for section in workflow_architect_agent["prompt_sections"]:
    if section["id"] == "instructions":
        # Update with improved instructions
        section["content"] = """**UNDERSTANDING THE THREE-LAYER INTERACTION MODEL**

Your role in the three-layer model:

**Layer 1 - Strategic Intent (WorkflowStrategy.human_in_loop)**:
- Set by: WorkflowStrategyAgent (upstream)
- Type: Boolean per phase
- Meaning: "Does this PHASE require human participation?"
- Your use: Identifies which phases need UI Components

**Layer 2 - UI Surface Contracts (TechnicalBlueprint.ui_components)**:
- Set by: YOU (WorkflowArchitectAgent)
- Type: Array of WorkflowUIComponent objects
- Meaning: "WHAT UI surfaces exist, WHERE they render (inline vs artifact), HOW users interact (interaction_pattern)"
- Your output: Binding contracts that WorkflowImplementationAgent must honor when designing agents

**Layer 3 - Agent Execution Mode (WorkflowAgent.human_interaction)**:
- Set by: WorkflowImplementationAgent (downstream)
- Type: "none" | "context" | "approval" per agent
- Meaning: "HOW does this SPECIFIC AGENT involve humans during execution?"
- Derived FROM: Your ui_components.interaction_pattern values

**YOUR JOB**: Translate Layer 1 (human_in_loop flags) → Layer 2 (UI Component contracts) for downstream consumption.

---

**Step 1 - Access Context Inputs**:
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
Generate output that includes global_context_variables array where each entry contains:
- name: Snake_case variable name
- type: "static" (hard-coded value), "derived" (set by agent_text or ui_response triggers), "environment" (from env vars), "database" (from MongoDB)
- trigger_hint: Simple description of when/how variable gets set (e.g., "Set when user approves Phase 2", "User provides budget amount") or null
- purpose: What this variable tracks and why it's needed (1-2 sentences)

**Decision Logic for Context Variables**:
- Review pattern guidance example for recommended context variables
- Adapt variable names/purposes to user's specific domain from interview
- If WorkflowStrategy.trigger="form_submit" → Create variables matching form fields mentioned in interview (type="derived", trigger_hint="User submits form with {field_name}", purpose based on field)
- If WorkflowStrategy.trigger="webhook" → Create "webhook_payload" (type="derived", trigger_hint="External service sends webhook POST", purpose="Stores incoming webhook data for processing")
- If WorkflowStrategy.trigger="schedule" → Create "execution_timestamp" (type="environment" or "static", trigger_hint="Set at workflow start", purpose="Tracks when scheduled workflow executed")
- For EACH phase where WorkflowStrategy.phases[i].human_in_loop=true:
  * Determine if phase requires approval/decision tracking based on phase_description and pattern coordination needs
  * If yes, create "{phase_name}_approved" (type="derived", trigger_hint="Set when user approves/rejects in {phase_name}", purpose="Tracks approval decision for {phase_name}")
  * Optionally create "{phase_name}_comments" (type="derived", trigger_hint="User provides feedback in {phase_name}", purpose="Stores user review comments")
- For EACH phase where WorkflowStrategy.phases[i].agents_needed="nested":
  * Create variables to coordinate between specialist agents if interview mentions or implies specific coordination needs
  * Example: "research_complete" (type="derived", trigger_hint="Set when research specialist finishes", purpose="Signals coordinator that research phase is ready")
- Review interview for domain-specific data (customer info, product details, order data, config flags):
  * Create corresponding variables (type="database" for persisted data, "environment" for config, "derived" for computed values)
  * Example: If interview mentions or implies "customer tier", create "customer_tier" (type="database", trigger_hint=null, purpose="Customer subscription level for tier-based routing")

**Step 4 - Define UI Components (UI Surface Contracts)**:
Generate output that includes ui_components array where each entry contains:
- phase_name: Must match a phase_name from WorkflowStrategy.phases EXACTLY
- agent: PascalCase agent name that will own this UI tool (infer from phase or use descriptive name like "ApprovalAgent", "InputAgent")
- tool: Snake_case tool function name (e.g., "submit_approval_decision", "collect_user_input", "display_summary")
- label: User-facing CTA or heading (e.g., "Review & Approve", "Enter Details", "View Results")
- component: PascalCase React component name (e.g., "ApprovalCard", "InputForm", "ResultsDisplay")
- display: "inline" or "artifact"
  * "inline" = Embedded in chat flow (small forms, quick inputs, stays in conversation)
  * "artifact" = Side panel rendering (rich content, multi-section forms, detailed displays)
- interaction_pattern: "single_step", "two_step_confirmation", or "multi_step"
  * "single_step" = User provides data once, agent continues (→ downstream human_interaction="context")
  * "two_step_confirmation" = User reviews, then approves/rejects (→ downstream human_interaction="approval")
  * "multi_step" = Progressive wizard or iterative refinement (→ downstream human_interaction="approval")
- summary: <=200 char narrative explaining what user sees/confirms at this component

**IMPORTANT - UI Components vs Chat Interface**:
- Chat interface = Transport mechanism for conversation (NOT a ui_component)
- UI Components = Interactive elements displayed WITHIN the chat (inline forms, approval cards, result displays)
- Plain text agent messages do NOT require ui_components
- Only create ui_components when structured interaction beyond text is needed

**Decision Logic for UI Components**:
- Review pattern guidance example for recommended ui_components
- For EACH phase where WorkflowStrategy.phases[i].human_in_loop=true:
  * Determine if phase needs structured UI beyond plain text chat
  * Check interview for UI interaction requirements
  * If simple data collection → interaction_pattern="single_step", display="inline"
  * If approval workflow → interaction_pattern="two_step_confirmation", display="artifact"
  * If multi-step form → interaction_pattern="multi_step", display based on complexity
- Adapt agent names, tool names, labels from pattern example to user's specific domain

**Step 5 - Decide on Lifecycle Hooks**:
Generate output for before_chat_lifecycle and after_chat_lifecycle (NOT arrays, single objects or null):

**before_chat_lifecycle** (WorkflowLifecycleToolRef or null):
- name: Snake_case lifecycle tool name
- purpose: What the lifecycle tool accomplishes (1-2 sentences)
- trigger: "before_chat" (literal value)
- integration: Third-party service name (PascalCase) or null

**Decision Logic for before_chat_lifecycle**:
- Review pattern guidance example for recommended before_chat hook
- If WorkflowStrategy.trigger="schedule" OR WorkflowStrategy.trigger="webhook":
  * Include before_chat_lifecycle with name="initialize_workflow_context", purpose="Initialize context variables and validate trigger payload before workflow starts", trigger="before_chat", integration=null
- If interview mentions or implies initialization, setup, loading config, fetching data before workflow:
  * Include before_chat_lifecycle with appropriate name, purpose based on interview, trigger="before_chat", integration based on service mentioned
- Otherwise: Set before_chat_lifecycle=null

**after_chat_lifecycle** (WorkflowLifecycleToolRef or null):
- name: Snake_case lifecycle tool name
- purpose: What the lifecycle tool accomplishes (1-2 sentences)
- trigger: "after_chat" (literal value)
- integration: Third-party service name (PascalCase) or null

**Decision Logic for after_chat_lifecycle**:
- Review pattern guidance example for recommended after_chat hook
- If final phase description mentions or implies "reporting", "persistence", "notification", "cleanup", "archive":
  * Include after_chat_lifecycle with name based on action (e.g., "finalize_transcript", "send_summary_email"), purpose based on interview, trigger="after_chat", integration based on service
- If interview mentions or implies logging, analytics, sending final notifications:
  * Include after_chat_lifecycle with appropriate name and purpose
- Otherwise: Set after_chat_lifecycle=null

**Step 6 - Validate Output Quality**:
- Verify EVERY phase from WorkflowStrategy.phases where human_in_loop=true has at least one corresponding ui_component with matching phase_name
- Confirm ui_component.phase_name values match WorkflowStrategy.phases[].phase_name EXACTLY (case-sensitive)
- Check ui_component.summary field is <=200 chars and describes user interaction clearly
- Verify context variables use correct type values: "static", "derived", "environment", or "database"
- If before_chat_lifecycle is not null, verify trigger="before_chat" and integration is PascalCase service name or null
- If after_chat_lifecycle is not null, verify trigger="after_chat" and integration is PascalCase service name or null
- Ensure ui_component.display is either "inline" or "artifact"
- Ensure ui_component.interaction_pattern is "single_step", "two_step_confirmation", or "multi_step"

**Step 7 - Emit Structured Output**:
- Generate TechnicalBlueprintOutput JSON exactly as described in [OUTPUT FORMAT]
- Include global_context_variables array (list of RequiredContextVariable objects)
- Include ui_components array (list of WorkflowUIComponent objects)
- Include before_chat_lifecycle (WorkflowLifecycleToolRef object or null)
- Include after_chat_lifecycle (WorkflowLifecycleToolRef object or null)
- Do not include agent names, tool manifests, or handoff sequences—those are derived downstream"""
        print("✓ Updated WorkflowArchitectAgent INSTRUCTIONS section")
        break

# Save updated agents.json
with open(agents_path, "w", encoding="utf-8") as f:
    json.dump(agents_data, f, indent=2, ensure_ascii=False)

print(f"\n✓ Saved updated agents.json")
print("\n" + "="*80)
print("THREE-LAYER INTERACTION MODEL - LAYER 2 (UI Surface Contracts)")
print("="*80)
print("\nKey improvements:")
print("1. Mirrors WorkflowStrategy structure (explains what context to use and how)")
print("2. Explicitly references WorkflowStrategy fields:")
print("   - trigger (chat/form_submit/webhook/schedule)")
print("   - phases[i].human_in_loop (Strategic Intent flag)")
print("   - phases[i].agents_needed")
print("   - phases[i].phase_name (used for ui_component matching)")
print("3. FIXED output schema alignment with TechnicalBlueprint:")
print("   - global_context_variables: name, type (static/derived/environment/database), trigger_hint, purpose")
print("   - ui_components: phase_name, agent, tool, label, component, display, interaction_pattern, summary")
print("     * display: inline (in chat flow) vs artifact (side panel)")
print("     * interaction_pattern: Determines downstream human_interaction mode")
print("       - single_step → human_interaction='context'")
print("       - two_step_confirmation → human_interaction='approval'")
print("       - multi_step → human_interaction='approval'")
print("   - before_chat_lifecycle/after_chat_lifecycle: Single objects (not arrays), or null")
print("4. Decision logic tied to specific WorkflowStrategy values + interview content")
print("5. Task-oriented language (Review/Create/Define/Decide vs Extract/Draft/Map/Determine)")
print("6. Fixed phrasing: 'align output to WorkflowStrategy + interview using pattern guidance as foundation'")
print("7. Clarified: Chat interface = transport, ui_components = interactive elements WITHIN chat")
