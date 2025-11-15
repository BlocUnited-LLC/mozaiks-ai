"""
Update WorkflowStrategyAgent INSTRUCTIONS section with:
1. Task-oriented language (not function-oriented)
2. Clear decision logic for trigger, initiated_by, human_in_loop, agents_needed
3. Better integration with pattern guidance examples
4. Reverses pattern verification (agent can't change pattern, only validate it fits)
"""

import json
from pathlib import Path

# Load agents.json
agents_path = Path("workflows/Generator/agents.json")
with open(agents_path, "r", encoding="utf-8") as f:
    agents_data = json.load(f)

# Find WorkflowStrategyAgent
workflow_strategy_agent = agents_data["agents"]["WorkflowStrategyAgent"]

# Find INSTRUCTIONS section
for section in workflow_strategy_agent["prompt_sections"]:
    if section["id"] == "instructions":
        # Update with improved instructions
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
Use the interview transcript and concept_overview to decide:

**trigger** (how workflow starts):
- "chat" → User types message to start conversation (most conversational workflows)
- "form_submit" → User submits web form with structured data
- "schedule" → Time-based trigger (cron job, daily/weekly automation)
- "database_condition" → Triggered when database state changes (e.g., new order, status update)
- "webhook" → External service sends HTTP POST (e.g., Stripe payment, Slack event)

**initiated_by** (who/what starts it):
- "user" → Human explicitly starts (chatbot, form submit, button click)
- "system" → Platform automatically starts (LLM, schedule, database watcher)
- "external_event" → Third-party service triggers (webhook from Stripe, Slack, etc.)

**Decision Logic**:
- If user mentions or their request implies "when I..." or conversational interaction → trigger="chat", initiated_by="user"
- If user mentions or their request implies forms, submissions, structured input → trigger="form_submit", initiated_by="user"
- If user mentions or their request implies "daily", "weekly", "scheduled" → trigger="schedule", initiated_by="system"
- If user mentions or their request implies "when order is placed", "when status changes" → trigger="database_condition", initiated_by="system"
- If user mentions or their request implies "when Stripe payment", "when Slack message" → trigger="webhook", initiated_by="external_event"

**Step 4 - Generate Workflow Metadata**:
- Create a Title Case workflow_name that reflects the automation goal (e.g., "Marketing Content Creator", "Customer Support Router").
- Write workflow_description summarizing the outcome using this template: "When [TRIGGER], workflow [ACTIONS], resulting in [VALUE]."
- Set trigger and initiated_by based on Step 3 decision logic.
- Copy the pattern name from PatternSelection (e.g., ["Pipeline"], ["Feedback Loop"]) - you cannot change this.

**Step 5 - Create Phase Scaffold**:
Use the pattern guidance at the bottom of your message as the starting point, then adapt to user context.

For each phase, determine:

**human_in_loop** (Strategic Intent - does this PHASE need human participation?):
- true → Phase requires human input, review, approval, or any user interaction
- false → Phase is fully automated (agents work on the backend without human involvement)

**Decision Logic**:
- Check pattern guidance example for recommended human_in_loop values per phase
- Validate against interview content:
  * Phase involves "review", "approve", "decide", "input", "feedback", "confirm", "select" → human_in_loop=true
  * Phase involves "analyze", "process", "generate", "send", "update", "calculate" (backend automation keywords) → human_in_loop=false
  * If monetization_enabled=true and phase delivers value to end user (user sees results, makes choices) → human_in_loop=true
  * If pattern guidance shows user interaction at this phase → human_in_loop=true

**IMPORTANT**: human_in_loop is STRATEGIC INTENT, not implementation detail. It signals to downstream agents:
- Architect layer: Create UI Components for phases flagged true
- Implementation layer: Set agent execution modes appropriately

**agents_needed** (how many agents coordinate?):
- "single" → One agent does all the work (simple, focused task)
- "sequential" → Multiple agents work in order, each handling different step (pipeline-style)
- "nested" → Coordinator agent + specialist agents (complex coordination, synthesis needed)

**Decision Logic**:
- If pattern guidance shows 1 agent for this phase → agents_needed="single"
- If pattern guidance shows 2+ agents working in sequence → agents_needed="sequential"  
- If pattern guidance shows coordinator + specialists → agents_needed="nested"
- If phase requires diverse expertise (research + analysis, or compare multiple approaches) → agents_needed="nested"
- If phase is simple transformation or single-domain work → agents_needed="single"

Generate output that includes phases array, where each entry contains:
  * phase_index: sequential integer starting at 0
  * phase_name: Copy from pattern guidance, format "Phase N: Purpose" (N = phase_index + 1)
  * phase_description: Adapt pattern guidance description to user's specific automation goal
  * human_in_loop: Determined by decision logic above
  * agents_needed: Determined by decision logic above

**Step 6 - Validate Output Quality**:
- Verify phase_index values increment without gaps (0..N-1).
- Confirm phase names and descriptions follow the pattern guidance structure.
- Check that human_in_loop reflects actual human participation requirements from interview.
- Ensure trigger and initiated_by match the decision logic from Step 3.
- Verify agents_needed matches the coordination style described in pattern guidance.

**Step 7 - Emit Structured Output**:
- Generate WorkflowStrategyOutput JSON exactly as described in [OUTPUT FORMAT].
- Include workflow_name, workflow_description, trigger, initiated_by, pattern (copied from PatternSelection), and phases array.
- Do not include lifecycle operations, tool manifests, or agent names—those are derived downstream."""
        print("✓ Updated WorkflowStrategyAgent INSTRUCTIONS section")
        break

# Save updated agents.json
with open(agents_path, "w", encoding="utf-8") as f:
    json.dump(agents_data, f, indent=2, ensure_ascii=False)

print(f"\n✓ Saved updated agents.json")
print("\n" + "="*80)
print("THREE-LAYER INTERACTION MODEL - LAYER 1 (Strategic Intent)")
print("="*80)
print("\nKey improvements:")
print("1. Removed 'Use upstream artifacts generically' (not relevant for first agent)")
print("2. Reversed pattern verification (agent validates fit, doesn't change pattern)")
print("3. Added explicit decision logic for:")
print("   - trigger (5 types with examples)")
print("   - initiated_by (3 types with examples)")
print("   - human_in_loop (Strategic Intent - does PHASE need human participation?)")
print("     * true = Phase requires user input/review/approval/confirmation")
print("     * false = Phase is fully automated backend processing")
print("     * Signals to downstream agents: WorkflowArchitectAgent creates UI Components")
print("   - agents_needed (5 decision rules)")
print("4. Better integration with pattern guidance (copy phase names, adapt descriptions)")
print("5. Task-oriented language throughout (Generate/Create/Review vs Read/Filter/Extract)")
