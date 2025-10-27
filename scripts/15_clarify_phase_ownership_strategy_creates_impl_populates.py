"""
Restructure phase ownership: WorkflowStrategyAgent creates phases, 
WorkflowImplementationAgent only adds agent details to existing phases.
"""

import json
from pathlib import Path

AGENTS_JSON = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

def main():
    with open(AGENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Update WorkflowImplementationAgent to clarify it doesn't create phases
    impl_message = data["agents"]["WorkflowImplementationAgent"]["system_message"]
    
    # Replace the phase parity section with clearer instructions
    old_parity = """## 1.B PHASE PARITY & COUNT VALIDATION (CRITICAL)
Before designing any agent specifications, enforce the strategic phase contract so the Action Plan mirrors WorkflowStrategyCall exactly.

**Non-negotiable validation steps:**
1. Read `workflow_strategy` from context variables. If it is missing or malformed, stop and request that the upstream strategy be regenerated.
2. Extract `strategy_phases = workflow_strategy.get("phases", [])` and build `strategy_phase_names = [phase.get("phase_name", "").strip() for phase in strategy_phases]`.
3. Ensure `strategy_phase_names` is non-empty, ordered, unique, and each entry starts with `Phase {index}:`. If numbering or naming is inconsistent, surface an error instead of proceeding.
4. While drafting the Action Plan, maintain `implementation_phase_names` that reflect the phases you have completed so far. Do not skip phases, rename them, or reorder them.
5. Before calling `action_plan(...)`, compare `implementation_phase_names` to `strategy_phase_names` (exact match including spacing, casing, and order). Also confirm each phase preserves the original `approval_required`, `agents_needed`, and `specialist_domains` semantics unless the strategy explicitly directs otherwise.
6. If any mismatch exists (count, order, spelling, or approval flags), stop and respond with a corrective explanation rather than invoking the tool. Direct the upstream agent to repair the discrepancy.

**Example parity contract (FeedbackLoop pattern with five phases):**
Strategy phases:
1. Phase 1: Content Ideation and Planning
2. Phase 2: AI Content Generation
3. Phase 3: Review and Approval
4. Phase 4: Content Revision and Finalization
5. Phase 5: Scheduling and Distribution

Implementation must emit those same five `phase_name` values, in order, when calling `action_plan(...)`. Any deviation (missing Phase 2, renamed Phase 3, altered numbering, etc.) is a fatal error. Never rely on downstream agents to repair parity."""

    new_parity = """## 1.B PHASE OWNERSHIP (CRITICAL - READ ONLY)
WorkflowStrategyCall already created the complete phase list. Your job is to ADD AGENT DETAILS to those existing phases, not create new ones.

**Your workflow:**
1. Read `workflow_strategy` from context variables.
2. Extract `strategy_phases = workflow_strategy.get("phases", [])` - this is your COMPLETE phase list.
3. For EACH phase in that list:
   - Keep the exact `phase_name` (e.g., "Phase 1: Content Ideation and Planning")
   - Keep the exact `phase_description` from strategy (or expand slightly with agent names)
   - ADD the `agents` array with detailed agent specifications
4. You do NOT:
   - Create new phases
   - Remove phases
   - Rename phases
   - Reorder phases
   - Change approval_required flags
5. When calling `action_plan(...)`, your phases array MUST have the same length and same phase_name values as the strategy.

**Example:**
Strategy gives you 5 phases → You return 5 phases (same names) + agent details added to each.
Strategy gives you 3 phases → You return 3 phases (same names) + agent details added to each.

If the strategy phase list seems incomplete, that's a WorkflowStrategyCall problem - ask for clarification, don't fix it yourself."""

    if old_parity not in impl_message:
        print("❌ Could not find phase parity section to update")
        return 1
    
    impl_message = impl_message.replace(old_parity, new_parity)
    
    # Update the scope description at the top
    old_scope = """# YOUR SCOPE (IMPLEMENTATION ONLY)
You receive a `workflow_strategy` from WorkflowStrategyCall and design:
1. **Detailed Workflow Phases** - Specific agent names, descriptions, operations, integrations
2. **Agent Specifications** - System messages, human_interaction settings, capabilities
3. **Tool Integrations** - Which agents need which tools (databases, APIs, services)
4. **Operations & Logic** - Handoff rules, data flow, error handling
5. **Approval Validation** - Ensure approval gates match interaction_mode and requirements

You DO NOT change the overall pattern, trigger, or strategic structure - WorkflowStrategyCall already determined that."""

    new_scope = """# YOUR SCOPE (AGENT DETAILS ONLY - NOT PHASE CREATION)
You receive a `workflow_strategy` from WorkflowStrategyCall with a COMPLETE phase list already defined.

**Your ONLY job:**
1. **Read the existing phases** - WorkflowStrategyCall created them; you don't create/modify/remove phases
2. **Add agent specifications to each phase** - Name, description, system_message, human_interaction, tools, operations, integrations
3. **Validate approval alignment** - Ensure human_interaction settings match the approval_required flags from strategy

**You DO NOT:**
- Create new phases (WorkflowStrategyCall did that)
- Remove or rename phases (use exact phase_name from strategy)
- Change the phase count (if strategy has 5 phases, you output 5 phases)
- Modify pattern, trigger, interaction_mode (WorkflowStrategyCall set those)"""

    if old_scope not in impl_message:
        print("⚠️ Could not find scope section, skipping that update")
    else:
        impl_message = impl_message.replace(old_scope, new_scope)
    
    # Update the collaboration section
    old_collab = """# COLLABORATION WITH WorkflowStrategyCall

WorkflowStrategyCall provided high-level architecture. You:
1. Read `workflow_strategy` from context variables
2. Design detailed agents, tools, operations for each phase
3. Validate approval requirements match strategy
4. Call `action_plan` with complete executable specification
5. Trust that WorkflowStrategyCall chose the right pattern - implement it faithfully"""

    new_collab = """# COLLABORATION WITH WorkflowStrategyCall

WorkflowStrategyCall provided:
- Complete phase list (phase_name, phase_description, approval_required, agents_needed, specialist_domains)
- Orchestration pattern, trigger, interaction_mode
- Strategy notes with constraints

You provide:
- Detailed agent specifications for each phase (who does the work)
- Tool and integration mappings (how the work gets done)
- Agent system messages (what each agent knows)

**Critical:** You add agent details TO the existing phases; you don't create the phases themselves."""

    if old_collab not in impl_message:
        print("⚠️ Could not find collaboration section, skipping that update")
    else:
        impl_message = impl_message.replace(old_collab, new_collab)
    
    data["agents"]["WorkflowImplementationAgent"]["system_message"] = impl_message
    
    with open(AGENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Updated WorkflowImplementationAgent to clarify: WorkflowStrategyCall owns phases, Implementation only adds agent details")
    return 0

if __name__ == "__main__":
    exit(main())
