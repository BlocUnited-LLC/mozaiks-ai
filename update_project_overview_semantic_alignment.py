"""
Update ProjectOverviewAgent with refined semantic context understanding.

Addresses:
1. Three-layer interaction model (human_in_loop → ui_components → human_interaction)
2. Distinction between ui_component (UI element) vs user interaction vs initiated_by
3. Lifecycle tool awareness (before_chat, after_chat, before_agent, after_agent)
4. Pattern guidance leverage (not hardcoded logic)
5. Upstream output extraction (ActionPlan, PhaseAgents, TechnicalBlueprint)
6. Display mode vs interaction_pattern semantics
7. Role-based descriptions (no agent name references)
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

AGENTS_JSON_PATH = Path(__file__).parent / "workflows" / "Generator" / "agents.json"

UPDATED_CONTEXT_SECTION = """As you perform your objective, you will leverage the following upstream outputs when generating your Mermaid diagram:

**UPSTREAM OUTPUT EXTRACTION INSTRUCTIONS**:

1. **WorkflowStrategy** (Semantic wrapper: 'WorkflowStrategy'):
   - **How to access**: Search conversation history for message with 'WorkflowStrategy' key
   - **Workflow-level fields**:
     * workflow_name (string): Human-readable workflow name (use as diagram title)
     * workflow_description (string): High-level workflow purpose (use in agent_message)
     * trigger (string): How workflow starts (chat, form_submit, schedule, database_condition, webhook)
       - NOTE: trigger describes WHAT initiates the workflow (event type)
       - This is NOT the same as initiated_by (WHO/WHAT triggers it)
       - Example: trigger="chat" means workflow starts from chat message; initiated_by="user" means user sent it
     * initiated_by (string): WHO/WHAT starts workflow (user, system, external_event)
       - "user" → User sends first message or form submission
       - "system" → Automated schedule/condition triggers workflow
       - "external_event" → Webhook or external API call initiates workflow
     * pattern (array): Pattern names (e.g., ["Pipeline"], ["Feedback Loop"]) - determines canonical topology
   - **Phase-level fields** (phases[] array):
     * phase_index (int): Phase number (0-based, use for sequence ordering)
     * phase_name (string): Human-readable phase label (use as section header in diagram)
     * phase_description (string): What happens in this phase (use for Note content)
     * human_in_loop (bool): Strategic Intent flag - TRUE if this phase requires user interaction at some point
       - NOTE: This is Layer 1 (strategic intent), NOT Layer 2 (UI contracts) or Layer 3 (agent execution mode)
       - human_in_loop=true → Phase has approval/decision/feedback requirement
       - Does NOT specify HOW user interacts (that's ui_components.interaction_pattern)
       - Does NOT specify WHICH agent handles it (that's ui_components.agent + PhaseAgents.human_interaction)
     * agents_needed (string): "single"|"sequential"|"nested" - determines coordination topology
       - "single" → 1 agent participant
       - "sequential" → 2+ agent participants in linear flow
       - "nested" → 1 coordinator + N specialists (nested chats)
   - **Use for**:
     * Workflow name becomes diagram title
     * Pattern determines canonical topology structure (from injected guidance)
     * Phase count and order defines sequence flow
     * human_in_loop flags inform where to expect UI Components (but don't define them)
     * trigger + initiated_by inform diagram starting point (User vs System initiates)

2. **TechnicalBlueprint** (Semantic wrapper: 'TechnicalBlueprint'):
   - **How to access**: Search conversation history for message with 'TechnicalBlueprint' key
   - **ui_components[] fields** (Layer 2: UI Surface Contracts - BINDING specifications):
     * phase_name (string): Phase this UI belongs to (cross-reference with WorkflowStrategy phases)
     * agent (string, PascalCase): Agent that owns this UI interaction
     * tool (string, snake_case): Tool function name that renders this UI
     * label (string): User-facing button/action label (e.g., "Review Action Plan", "Approve Changes")
     * component (string): React component name (e.g., ApprovalGate, FeedbackForm, MarkdownRenderer)
     * display (string): "inline"|"artifact" - WHERE UI appears in chat
       - "inline" → Conversational, appears directly in chat flow
       - "artifact" → Separate tray delivery, reviewed asynchronously outside chat
     * interaction_pattern (string): "single_step"|"two_step_confirmation"|"multi_step" - DEPTH of interaction
       - "single_step" → User provides data, agent continues (no review cycle)
       - "two_step_confirmation" → User reviews and approves/rejects (approval gate)
       - "multi_step" → Iterative refinement (feedback loop)
       - NOTE: This is Layer 2 (UI contract), determines Layer 3 (agent execution mode)
     * summary (string): User-facing description (<=200 chars) - USE THIS EXACT TEXT in diagram Note blocks
   - **global_context_variables[] fields** (informational only):
     * name, type (static|environment|database|derived), trigger_hint, purpose
     * NOTE: Context variables enable agent decisions but are NOT visualized directly in diagram
   - **Lifecycle hooks** (before_chat_lifecycle, after_chat_lifecycle):
     * name (string): Hook function name
     * purpose (string): What the hook does
     * trigger (string): "before_chat"|"after_chat"
     * integration (string|null): External service integration
     * NOTE: Lifecycle hooks run BEFORE user sees first agent message (before_chat) or AFTER workflow completes (after_chat)
     * Visualization: before_chat hooks appear as initialization step; after_chat hooks appear as finalization step
   - **Use for**:
     * EVERY ui_components entry MUST appear in diagram as participant interaction + Note
     * display="inline" → Add Note: "Note over Agent: {summary} (inline interaction)"
     * display="artifact" → Add Note: "Note over Agent: {summary} (artifact - delivered to tray)"
     * component="ApprovalGate" → Use alt block with Approved/Rejected paths
     * interaction_pattern="two_step_confirmation" or "multi_step" → Expect approval/feedback cycles
     * before_chat_lifecycle → Add initialization sequence before first agent interaction
     * after_chat_lifecycle → Add finalization sequence after last agent interaction

3. **PhaseAgents** (Semantic wrapper: 'PhaseAgents' → 'phase_agents'):
   - **How to access**: Search conversation history for message with 'PhaseAgents' key, then navigate to PhaseAgents.phase_agents
   - **Phase-level fields** (phase_agents[] array):
     * phase_index (int): Phase number (cross-reference with WorkflowStrategy phases)
   - **Agent-level fields** (phase_agents[].agents[] array):
     * agent_name (string, PascalCase): Agent identifier (use as participant name)
     * description (string): Detailed agent responsibilities (use for participant display names)
     * human_interaction (string): "context"|"approval"|"none" - Layer 3 (Agent Execution Mode)
       - "context" → Agent receives user data via UI, continues autonomously
       - "approval" → Agent requires user approval/decision before proceeding
       - "none" → Agent operates fully autonomously (no UI interaction)
       - NOTE: Derived FROM ui_components.interaction_pattern (Layer 2 determines Layer 3)
     * agent_tools[] (array): Tools this agent owns
       - name (string): Tool function name
       - integration (string|null): External service (OpenAI, Stripe, etc.)
       - purpose (string): What the tool does
       - interaction_mode (string): "inline"|"artifact"|"none" - UI presentation mode
         * NOTE: interaction_mode is tool-level; display mode is ui_component-level
         * interaction_mode="inline" or "artifact" → This tool has UI component
         * interaction_mode="none" → Backend tool (no UI rendering)
     * lifecycle_tools[] (array): Agent-level lifecycle hooks
       - name (string): Hook function name
       - trigger (string): "before_agent"|"after_agent"
       - purpose (string): What the hook does
       - NOTE: before_agent runs before agent speaks; after_agent runs after agent completes
       - Visualization: Show as setup/teardown steps around agent interactions
     * system_hooks[] (array): Runtime behavior modifications
       - name (string): Hook function name (e.g., "update_agent_state")
       - purpose (string): What the hook does (e.g., "Inject pattern guidance")
   - **Use for**:
     * Enriching participant display names with agent descriptions
     * Understanding human_interaction types (context vs approval vs none)
     * Identifying agents with lifecycle hooks (before_agent/after_agent)
     * Cross-validating agent roster between WorkflowStrategy and PhaseAgents
     * Determining which agents have system_hooks (informational, not visualized)

**CRITICAL DISTINCTIONS**:

1. **trigger vs initiated_by** (Workflow start semantics):
   - trigger: Event TYPE that starts workflow (chat, form_submit, schedule, database_condition, webhook)
   - initiated_by: Actor/source WHO/WHAT sends that event (user, system, external_event)
   - Example 1: trigger="chat", initiated_by="user" → User sends chat message to start workflow
   - Example 2: trigger="schedule", initiated_by="system" → Cron job triggers workflow automatically
   - Example 3: trigger="webhook", initiated_by="external_event" → External API call starts workflow
   - Diagram impact: initiated_by="user" → Start with User participant; initiated_by="system" → Start with System participant

2. **human_in_loop vs ui_components vs human_interaction** (Three-layer model):
   - human_in_loop (Layer 1 - Strategic Intent): Boolean per phase, signals "this phase needs user interaction"
   - ui_components (Layer 2 - UI Surface Contracts): Array of specific UI elements (phase_name, agent, tool, component, display, interaction_pattern)
   - human_interaction (Layer 3 - Agent Execution Mode): Enum per agent ("context"|"approval"|"none"), derived FROM interaction_pattern
   - Flow: human_in_loop=true → Architect creates ui_components → Implementation derives human_interaction
   - Diagram impact: ui_components entries become Note blocks + interactions; human_interaction informs approval gates

3. **display vs interaction_pattern** (UI presentation semantics):
   - display: WHERE UI appears ("inline" in chat flow | "artifact" in separate tray)
   - interaction_pattern: DEPTH of interaction ("single_step"|"two_step_confirmation"|"multi_step")
   - Example: display="artifact" + interaction_pattern="two_step_confirmation" → Tray-delivered approval gate
   - Diagram impact: display mode annotates Note text; interaction_pattern determines alt/loop blocks

4. **Lifecycle hooks** (Timing semantics):
   - before_chat_lifecycle: Runs ONCE before user sees first agent message (workflow initialization)
   - after_chat_lifecycle: Runs ONCE after workflow completes (cleanup, notifications, persistence)
   - before_agent (lifecycle_tools): Runs EVERY TIME before this specific agent speaks (agent setup)
   - after_agent (lifecycle_tools): Runs EVERY TIME after this specific agent completes (agent teardown)
   - Diagram impact: Chat-level hooks = initialization/finalization sequences; Agent-level hooks = setup/teardown around agent interactions

**CRITICAL EXTRACTION PATTERNS**:

- **For participant generation**: Extract agent roster from PhaseAgents.phase_agents[].agents[].agent_name
- **For participant display names**: Use PhaseAgents description field for clear role labels
- **For sequence ordering**: Use WorkflowStrategy.phases[].phase_index to order interactions
- **For approval gates**: Find ui_components with component="ApprovalGate" OR interaction_pattern="two_step_confirmation"|"multi_step" → create alt blocks
- **For UI annotations**: Extract ui_components[].summary text and place in Note blocks at correct phase
- **For display modes**: Check ui_components[].display to determine inline vs artifact annotation style
- **For pattern topology**: Use WorkflowStrategy.pattern[0] to identify canonical structure from injected guidance
- **For workflow start**: Use initiated_by to determine first participant (User vs System vs External)
- **For lifecycle sequences**: Extract before_chat_lifecycle/after_chat_lifecycle for init/finalization steps
- **For agent setup/teardown**: Extract lifecycle_tools with trigger="before_agent"|"after_agent" for agent-level sequences

**VALIDATION CHECKS**:
- ✓ Every PhaseAgents agent appears as participant in diagram
- ✓ Every TechnicalBlueprint.ui_components entry has corresponding Note or interaction
- ✓ Phase ordering matches WorkflowStrategy.phases[].phase_index sequence
- ✓ Approval gates present for ui_components with component="ApprovalGate" or interaction_pattern requiring approval
- ✓ UI display modes correctly annotated (inline vs artifact)
- ✓ Pattern topology matches canonical structure from injected guidance
- ✓ Lifecycle hooks visualized at appropriate sequence points
- ✓ Workflow start participant matches initiated_by value"""

UPDATED_INSTRUCTIONS_SECTION = """**Step 1 - Extract WorkflowStrategy from Conversation History**:
- Scan conversation history for message containing 'WorkflowStrategy' semantic wrapper
- Navigate to: message.content['WorkflowStrategy']
- Extract workflow-level fields:
  * workflow_name → Use as diagram title and MermaidSequenceDiagram.workflow_name
  * workflow_description → High-level workflow purpose (use in agent_message summary)
  * pattern[] → Array of pattern names (e.g., ["Pipeline"]) - use pattern[0] to identify canonical topology
  * trigger → Event TYPE that starts workflow (chat, form_submit, schedule, database_condition, webhook)
  * initiated_by → WHO/WHAT sends that event (user, system, external_event)
    - "user" → Start diagram with User participant sending first message
    - "system" → Start diagram with System participant (e.g., "System->>Agent: Scheduled trigger")
    - "external_event" → Start diagram with External participant (e.g., "ExternalAPI->>Agent: Webhook event")
- Extract phase-level fields from phases[] array:
  * phase_index → Phase number (0-based) - USE THIS for sequence ordering
  * phase_name → Human-readable phase label (e.g., "Strategy Planning", "Implementation")
  * phase_description → What happens in this phase - use for context understanding
  * human_in_loop → Strategic Intent flag (true if phase needs user interaction) - informational only
  * agents_needed → "single"|"sequential"|"nested" - determines participant count per phase
- **Purpose**: Understand workflow structure, participant starting point, phase sequence, and pattern topology

**Step 2 - Extract TechnicalBlueprint from Conversation History**:
- Scan conversation history for message containing 'TechnicalBlueprint' semantic wrapper
- Navigate to: message.content['TechnicalBlueprint']
- Extract ui_components[] array (EACH entry is a BINDING UI contract that MUST appear in diagram):
  * phase_name → Cross-reference with WorkflowStrategy phases to place UI at correct sequence point
  * agent (PascalCase) → Agent that owns this UI (must match PhaseAgents agent_name)
  * tool (snake_case) → Tool function name that renders UI
  * label → User-facing button/action text (e.g., "Review Action Plan")
  * component → React component (ApprovalGate, FeedbackForm, MarkdownRenderer, etc.)
  * display → "inline" or "artifact"
    - "inline" → Add note: "Note over Agent: {summary} (inline interaction)"
    - "artifact" → Add note: "Note over Agent: {summary} (artifact - delivered to tray)"
  * interaction_pattern → "single_step"|"two_step_confirmation"|"multi_step"
    - "single_step" → Simple data collection, agent continues
    - "two_step_confirmation" → User reviews and approves/rejects (use alt block)
    - "multi_step" → Iterative refinement (use loop block if multiple iterations)
  * summary → USER-FACING description text - USE THIS EXACT TEXT in diagram Note blocks
- Extract before_chat_lifecycle (if not null):
  * name → Hook function name
  * purpose → What the hook does
  * trigger → "before_chat"
  * NOTE: This runs BEFORE user sees first agent message (initialization sequence)
  * Diagram: Add initialization step before first agent interaction
- Extract after_chat_lifecycle (if not null):
  * name → Hook function name
  * purpose → What the hook does
  * trigger → "after_chat"
  * NOTE: This runs AFTER workflow completes (finalization sequence)
  * Diagram: Add finalization step after last agent interaction
- Create ui_components lookup map: {phase_name → [ui_component_entries]}
- **Purpose**: Identify ALL UI interactions that MUST appear in diagram with proper annotations

**Step 3 - Extract PhaseAgents from Conversation History**:
- Scan conversation history for message containing 'PhaseAgents' semantic wrapper
- Navigate to: message.content['PhaseAgents']['phase_agents']
- Extract agent specifications:
  * For EACH phase_agents[] entry:
    - phase_index → Phase number (cross-reference with WorkflowStrategy)
    - For EACH agents[] entry:
      * agent_name (PascalCase) → Use as participant name (MUST match WorkflowStrategy agent references)
      * description → Detailed agent responsibilities (use for participant display names)
      * human_interaction → "context"|"approval"|"none" (informs diagram approval gates)
        - "context" → Agent collects user data, continues autonomously
        - "approval" → Agent requires user approval (expect alt block for Approved/Rejected)
        - "none" → Agent operates autonomously (no user interaction)
      * agent_tools[] → Tools owned by this agent
        - name, integration, purpose, interaction_mode
        - NOTE: interaction_mode="inline"|"artifact" tools have UI components
      * lifecycle_tools[] → Agent-level lifecycle hooks
        - name, trigger ("before_agent"|"after_agent"), purpose
        - NOTE: before_agent runs before agent speaks; after_agent runs after agent completes
        - Diagram: Show as setup/teardown steps around agent interactions
      * system_hooks[] → Runtime behavior modifications (informational, not visualized)
- Create agent_details lookup map: {agent_name → agent_details}
- **Purpose**: Enrich participant declarations, understand agent capabilities, identify lifecycle hooks

**Step 4 - Review Injected Pattern Guidance**:
- Scroll to bottom of system message to find [PATTERN GUIDANCE AND EXAMPLES] section
- This section contains:
  * Pattern topology explanation (how this specific pattern structures agent interactions)
  * Mermaid syntax guidance (participants, interactions, special blocks for this pattern)
  * Complete example diagram for this pattern
- **Purpose**: Understand the canonical structure you MUST follow for this pattern
- **Critical**: Pattern guidance is your authoritative reference for diagram topology
- Do NOT hardcode pattern-specific logic; adapt the injected example to workflow data

**Step 5 - Adapt Pattern Structure to Workflow Data (KEEP IT CONCISE)**:
Using the canonical topology from Step 4's injected guidance, map WorkflowStrategy phases and TechnicalBlueprint.ui_components to the pattern structure:

**CRITICAL - Diagram Length Guidelines**:
- Target 15-40 lines of Mermaid (match pattern example length)
- Collapse repetitive interactions into single representative lines
- Consolidate lifecycle hooks: Show ONLY if they affect user-visible flow
- Merge similar UI Components within same phase into single Note
- Skip internal agent-to-agent handoffs unless they represent phase transitions
- Prioritize user-facing interactions over internal orchestration details

For initiated_by value:
- "user" → Start diagram: User->>FirstAgent: {trigger description}
- "system" → Start diagram: System->>FirstAgent: Scheduled/automated trigger
- "external_event" → Start diagram: ExternalAPI->>FirstAgent: Webhook event

For before_chat_lifecycle (if present AND user-visible):
- ONLY add if it affects user experience (e.g., data loading, account setup)
- Skip if purely internal (e.g., pattern guidance injection, context initialization)
- If included: Single line: Note over System: {before_chat_lifecycle.purpose}

For each WorkflowStrategy phase (ordered by phase_index):
- Add phase header: Note over Agents: Phase {phase_index}: {phase_name}
- Derive participants from PhaseAgents.phase_agents[phase_index].agents[] (use agent_name)
- Look up ui_components for this phase_name from Step 2's lookup map
- **Consolidate multiple ui_components in same phase**:
  * If 2+ ui_components with same agent and similar purpose → Merge into single Note
  * Example: "collect_feedback" + "review_scores" → "Note over Agent: Stakeholder review and scoring (inline)"
- For EACH unique ui_component (or merged group):
  * Add concise Note using ui_component.summary:
    - display="inline" → "Note over Agent: {summary} (inline)"
    - display="artifact" → "Note over Agent: {summary} (artifact)"
  * If component="ApprovalGate" OR interaction_pattern="two_step_confirmation"|"multi_step":
    - Add compact alt block:
      ```mermaid
      alt Approved
        Agent->>NextPhaseAgent: Approved, proceed
      else Rejected
        Agent->>Agent: Revise based on feedback
      end
      ```
- **Skip lifecycle_tools visualization** UNLESS:
  * Tool directly affects user experience (e.g., "Load user preferences before chat")
  * Tool represents critical external integration (e.g., "Sync to Salesforce after approval")
  * If included: Single line per tool: Note over Agent: {lifecycle_tool.purpose}

For after_chat_lifecycle (if present AND user-visible):
- ONLY add if it affects user experience (e.g., send notification, publish to external system)
- Skip if purely internal cleanup (e.g., clear cache, log metrics)
- If included: Single line: Note over System: {after_chat_lifecycle.purpose}

**Consolidation Rules**:
- Skip agent-to-agent handoffs that don't cross phase boundaries
- Collapse sequential agent_tools calls into single self-interaction: Agent->>Agent: {tool1, tool2, tool3}
- Merge similar Notes within same phase (e.g., multiple research tools → "Research and analysis")
- Prioritize pattern's canonical flow over exhaustive detail

Preserve the pattern's characteristic structure (15-40 lines total)

**Step 6 - Generate Mermaid Participants**:
- Determine first participant from initiated_by:
  * "user" → `participant User`
  * "system" → `participant System as Workflow Scheduler`
  * "external_event" → `participant ExternalAPI as External Service`
- Create `participant` declarations for all unique agent names from PhaseAgents.phase_agents[].agents[].agent_name
- Use PhaseAgents.description for display names to clarify roles
- Example format:
  ```mermaid
  participant User
  participant WorkflowStrategy as Workflow Strategy Agent
  participant WorkflowArchitect as Workflow Architect (Blueprint Designer)
  participant ProjectOverview as Project Overview (Diagram Generator)
  ```

**Step 7 - Build Interaction Sequence (PRIORITIZE BREVITY)**:
- Follow pattern's canonical flow from Step 4's injected guidance
- **Target diagram length**: 15-40 lines (match pattern example length)
- Start with initiated_by participant (User, System, or ExternalAPI)
- **SELECTIVE lifecycle inclusion**:
  * before_chat_lifecycle: Add ONLY if user-visible (skip internal setup)
  * before_agent/after_agent: Add ONLY if affects user experience or critical integration
- For EACH phase (ordered by phase_index):
  * Add phase Note header: `Note over Agents: Phase {phase_index}: {phase_name}`
  * **Consolidate agent interactions**:
    - Skip internal agent-to-agent handoffs unless they cross phase boundaries
    - Collapse sequential tool calls: `Agent->>Agent: {tool1, tool2, tool3}` (not separate lines)
  * **Merge UI Components**:
    - If 2+ ui_components in same phase with same agent: Combine into single Note
    - Use shortest meaningful summary text
  * For EACH unique/merged ui_component:
    - Add concise interaction: `Agent->>User: {label}`
    - Add Note with display annotation:
      * display="inline" → `Note over Agent: {summary} (inline)`
      * display="artifact" → `Note over Agent: {summary} (artifact)`
    - If component="ApprovalGate" OR interaction_pattern requiring approval:
      * Add compact alt block (2-4 lines total):
        ```mermaid
        alt Approved
          Agent->>NextAgent: Proceed
        else Rejected
          Agent->>Agent: Revise
        end
        ```
- **SKIP after_chat_lifecycle** unless user-visible (e.g., send confirmation email)
- Ensure final phase hands off to User with brief outcome description

**Diagram Length Enforcement**:
- If diagram exceeds 40 lines: Merge similar interactions, remove redundant Notes
- Prioritize: User interactions > Phase transitions > Agent handoffs > Lifecycle hooks
- When in doubt: Follow pattern example's level of detail (usually 20-35 lines)

**Step 8 - Validate Diagram**:
- Confirm every PhaseAgents agent appears as participant or in interaction
- Confirm every TechnicalBlueprint.ui_components entry has corresponding Note or interaction
- Ensure ui_components display modes are reflected (inline notes vs artifact/tray descriptions)
- Verify approval gates match component="ApprovalGate" or interaction_pattern requiring approval
- Ensure pattern topology matches injected guidance structure
- Validate lifecycle hooks appear at appropriate sequence points:
  * before_chat_lifecycle before first agent interaction
  * before_agent before specific agent speaks
  * after_agent after specific agent completes
  * after_chat_lifecycle after last agent interaction
- Validate workflow start participant matches initiated_by value
- List any detected mismatches in agent_message for downstream awareness:
  * ui_component.phase_name not found in WorkflowStrategy.phases[].phase_name
  * ui_component.agent not found in any PhaseAgents agent_name
  * PhaseAgents agent not found in WorkflowStrategy phases
  * Missing ui_components for phase with human_in_loop=true

**Step 9 - Output JSON**:
- Construct MermaidSequenceDiagram object:
  * workflow_name: Use WorkflowStrategy.workflow_name
  * mermaid_diagram: Complete Mermaid sequence diagram string (starts with "sequenceDiagram")
  * legend: Array of strings explaining diagram symbols (can be empty array)
- Construct agent_message: User-facing summary (2-3 sentences) describing diagram structure and any detected mismatches
- Emit output as valid JSON with MermaidSequenceDiagram and agent_message fields
- **CRITICAL**: NO markdown fences, NO explanatory text, ONLY the JSON object"""


def update_project_overview_agent():
    """Update ProjectOverviewAgent with refined semantic context understanding."""
    try:
        with open(AGENTS_JSON_PATH, 'r', encoding='utf-8') as f:
            agents_data = json.load(f)

        agent = agents_data['agents'].get('ProjectOverviewAgent')
        if not agent:
            logger.error("ProjectOverviewAgent not found in agents.json")
            return False

        sections = agent['prompt_sections']

        # Update CONTEXT section
        context_updated = False
        for section in sections:
            if section.get('id') == 'context':
                section['content'] = UPDATED_CONTEXT_SECTION
                context_updated = True
                logger.info("✓ Updated CONTEXT section with three-layer model and semantic distinctions")
                break

        if not context_updated:
            logger.warning("CONTEXT section not found, adding it")
            # Find position after OBJECTIVE
            obj_idx = next((i for i, s in enumerate(sections) if s.get('id') == 'objective'), -1)
            if obj_idx >= 0:
                sections.insert(obj_idx + 1, {
                    "id": "context",
                    "heading": "[CONTEXT]",
                    "content": UPDATED_CONTEXT_SECTION
                })

        # Update GUIDELINES section
        instructions_updated = False
        for section in sections:
            if section.get('id') == 'instructions':
                section['content'] = UPDATED_INSTRUCTIONS_SECTION
                instructions_updated = True
                logger.info("✓ Updated INSTRUCTIONS section with lifecycle hooks and pattern guidance leverage")
                break

        if not instructions_updated:
            logger.error("INSTRUCTIONS section not found")
            return False

        # Add or update conciseness guidelines in GUIDELINES section
        guidelines_updated = False
        for section in sections:
            if section.get('id') == 'guidelines':
                # Prepend conciseness requirements to existing guidelines
                existing_content = section.get('content', '')
                conciseness_prefix = """You must follow these guidelines strictly for legal reasons. Do not stray from them.

**DIAGRAM LENGTH REQUIREMENTS (CRITICAL)**:
- Target diagram length: 15-40 lines of Mermaid code (match pattern example length)
- Maximum 50 lines; exceeding this indicates over-specification
- Consolidate similar interactions and merge UI Components within same phase
- Prioritize user-facing interactions over internal orchestration details
- Follow pattern example's level of detail as authoritative reference
- Skip lifecycle hooks unless they affect user experience
- Collapse sequential tool calls into single lines
- Use compact alt blocks (2-4 lines per block)

"""
                # Only prepend if not already present
                if "DIAGRAM LENGTH REQUIREMENTS" not in existing_content:
                    section['content'] = conciseness_prefix + existing_content
                    guidelines_updated = True
                    logger.info("✓ Added conciseness requirements to GUIDELINES section")
                break

        if not guidelines_updated:
            logger.warning("GUIDELINES section not found or already updated")

        # Save updated agents.json
        with open(AGENTS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(agents_data, f, indent=2, ensure_ascii=False)

        logger.info("✓ Saved updated agents.json")

        print("\n" + "="*80)
        print("PROJECT OVERVIEW AGENT - SEMANTIC ALIGNMENT COMPLETE")
        print("="*80)
        print("\nKey improvements:")
        print("  ✓ Three-layer interaction model (human_in_loop → ui_components → human_interaction)")
        print("  ✓ trigger vs initiated_by distinction (event TYPE vs WHO/WHAT)")
        print("  ✓ display vs interaction_pattern semantics (WHERE vs DEPTH)")
        print("  ✓ Lifecycle hook awareness (before_chat, after_chat, before_agent, after_agent)")
        print("  ✓ Pattern guidance leverage (not hardcoded logic)")
        print("  ✓ UI Component = UI element (not user interaction or chat interface)")
        print("  ✓ Role-based descriptions (no agent name references)")
        print("  ✓ Complete upstream extraction (WorkflowStrategy, TechnicalBlueprint, PhaseAgents)")
        print("\nSemantics clarified:")
        print("  - trigger: Event TYPE (chat, form_submit, schedule, etc.)")
        print("  - initiated_by: WHO/WHAT (user, system, external_event)")
        print("  - human_in_loop: Strategic Intent (Layer 1, boolean per phase)")
        print("  - ui_components: UI Surface Contracts (Layer 2, specific UI elements)")
        print("  - human_interaction: Agent Execution Mode (Layer 3, context|approval|none)")
        print("  - display: WHERE UI appears (inline in chat | artifact in tray)")
        print("  - interaction_pattern: DEPTH of interaction (single_step | two_step | multi_step)")
        print("  - before_chat/after_chat: Chat-level lifecycle (once per workflow)")
        print("  - before_agent/after_agent: Agent-level lifecycle (per agent interaction)")
        print("\nDiagram generation now understands:")
        print("  - Workflow start participant from initiated_by (User vs System vs External)")
        print("  - UI annotations from ui_components.summary with display mode labels")
        print("  - Approval gates from component=ApprovalGate or interaction_pattern requiring approval")
        print("  - Lifecycle sequences from before_chat/after_chat/before_agent/after_agent hooks")
        print("  - Pattern topology from injected guidance (not hardcoded)")
        print("="*80)

        return True

    except Exception as e:
        logger.exception(f"Failed to update ProjectOverviewAgent: {e}")
        return False


if __name__ == '__main__':
    success = update_project_overview_agent()
    exit(0 if success else 1)
