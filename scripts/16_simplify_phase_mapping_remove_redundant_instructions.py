#!/usr/bin/env python3
"""
Script 16: Simplify Phase Mapping - Remove Redundant "Keep Exact" Instructions

User observation: Instructions say "keep exact phase_name" but this is redundant -
the Implementation agent should just MAP from WorkflowStrategyPhase → WorkflowPhase schema.

Changes:
- Replace verbose "keep exact" instructions with concise schema mapping
- Emphasize this is a MAPPING operation, not regeneration
- Reference the schema field names explicitly (phase_name → name, etc.)
"""

import json
import sys
from pathlib import Path

AGENTS_JSON = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

def main():
    if not AGENTS_JSON.exists():
        print(f"❌ agents.json not found at {AGENTS_JSON}")
        return 1
    
    with open(AGENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if "WorkflowImplementationAgent" not in data.get("agents", {}):
        print("❌ WorkflowImplementationAgent not found")
        return 1
    
    impl_message = data["agents"]["WorkflowImplementationAgent"]["system_message"]
    
    # Replace the verbose phase ownership block with concise schema mapping
    old_ownership = """## 1.B PHASE OWNERSHIP (CRITICAL - READ ONLY)
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

    new_ownership = """## 1.B PHASE OWNERSHIP (CRITICAL - READ ONLY)

WorkflowStrategyCall already created the complete phase list. Your job is to MAP those phases into ActionPlanCall format and ADD AGENT DETAILS.

**SCHEMA MAPPING (WorkflowStrategyPhase → WorkflowPhase):**
- `phase_name` → `name` (preserve exact text including "Phase N:" prefix)
- `phase_description` → `description` (preserve or expand slightly with agent names)
- `specialist_domains` → (guides which agents to create)
- ADD: `agents: [...]` array with WorkflowAgent specs

**Phase Count Invariant:**
If strategy has N phases → ActionPlan MUST have N phases (same numbering, same naming).

**Example:**
Strategy: 5 phases → You output: 5 phases with agents array populated
Strategy: 3 phases → You output: 3 phases with agents array populated

If the phase list seems incomplete, ask for clarification - don't create/skip/merge phases yourself."""

    if old_ownership not in impl_message:
        print("❌ Could not find phase ownership section to update")
        return 1
    
    impl_message = impl_message.replace(old_ownership, new_ownership)
    
    data["agents"]["WorkflowImplementationAgent"]["system_message"] = impl_message
    
    with open(AGENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Simplified phase mapping instructions - removed redundant 'keep exact' text, emphasized schema mapping")
    return 0

if __name__ == "__main__":
    exit(main())
