"""Update WorkflowStrategyAgent Step 3 to reference injected pattern guidance"""

import json
import sys
from pathlib import Path

def update_step_3():
    """Update [INSTRUCTIONS] Step 3 in WorkflowStrategyAgent"""
    
    agents_json_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    with open(agents_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Find WorkflowStrategyAgent
    if "agents" not in data or "WorkflowStrategyAgent" not in data["agents"]:
        print("❌ WorkflowStrategyAgent not found")
        return False
    
    agent = data["agents"]["WorkflowStrategyAgent"]
    
    # Find [INSTRUCTIONS] section
    instructions_section = None
    for section in agent["prompt_sections"]:
        if section["id"] == "instructions":
            instructions_section = section
            break
    
    if not instructions_section:
        print("❌ [INSTRUCTIONS] section not found")
        return False
    
    # Current Step 3 text (simplified to just find/replace the pattern knowledge part)
    old_step_3 = """**Step 3 - Apply Pattern Knowledge**:

Understand the selected pattern's coordination characteristics:

- **ContextAwareRouting** → Analyzer classifies intent and routes to domain specialists; later phases consolidate responses
- **Escalation** → Tiered resolution with confidence-based escalation (Tier1 → Tier2 → Tier3)
- **FeedbackLoop** → Iterative create → review → revise cycles tracked via context variables
- **Hierarchical** → Executive strategist delegates to managers and specialists, then synthesizes final output
- **Organic** → Free-form collaboration without rigid handoffs; rely on strong agent descriptions for routing
- **Pipeline** → Strict sequential transformation (validate → enrich → finalize) with deterministic handoffs
- **Redundant** → Multiple experts independently solve the same task via sequential nested chats; evaluator compares and selects or synthesizes the best result
- **Star** → Central coordinator delegates to spokes and aggregates results back to the hub
- **TriageWithTasks** → Decompose request into typed tasks, enforce dependency ordering, and execute via specialist task runners"""
    
    new_step_3 = """**Step 3 - Use Pattern-Specific Guidance from Runtime Injection**:

CRITICAL: Before you begin phase design, the runtime has injected detailed pattern-specific guidance into your system message via the update_agent_state hook (from update_agent_state_pattern.py). This injected content appears as a [INJECTED PATTERN GUIDANCE - {PatternName}] section and includes:

1. **Phase Structure Recommendations** - Pattern's coordination pattern description and flow logic
2. **Recommended Phases** - Pre-defined phase templates specific to this pattern (with names, purposes, specialist_domains, typical agents)
3. **When to Use This Pattern** - Validation of pattern appropriateness
4. **Pattern Characteristics** - Key traits and implementation notes
5. **Pattern-Specific Example** - Complete workflow_strategy(...) call showing realistic phase structure, lifecycle_operations, and strategy_notes for this pattern

**You MUST**:
- Scroll to the bottom of your system message to locate the [INJECTED PATTERN GUIDANCE - {PatternName}] section
- Use the **Recommended Phases** as your starting template for phase design
- Adapt the recommended phases to the user's specific goal (rename phases, adjust descriptions, add/remove phases as needed)
- Follow the **Phase Structure Recommendations** to understand the pattern's coordination flow and ensure your phases align with the pattern's topology
- Reference the **Pattern-Specific Example** to understand proper formatting of phase_name, specialist_domains, lifecycle_operations, and strategy_notes for this pattern
- Validate that your workflow design matches the **When to Use This Pattern** criteria to ensure the selected pattern is appropriate

**Why This Matters**:
The injected guidance is dynamically selected based on the PatternAgent's upstream decision. It ensures your workflow strategy aligns with the pattern's canonical structure while adapting to the user's unique requirements. DO NOT design phases from scratch; USE the injected Recommended Phases as your foundation and customize from there."""
    
    # Replace in content
    if old_step_3 not in instructions_section["content"]:
        print("❌ Could not find exact Step 3 text to replace")
        print("\nSearching for Step 3 heading...")
        if "**Step 3" in instructions_section["content"]:
            print("✓ Found Step 3 heading, but exact content doesn't match")
            print("This may require manual inspection")
        return False
    
    instructions_section["content"] = instructions_section["content"].replace(old_step_3, new_step_3)
    
    # Write back
    with open(agents_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Successfully updated WorkflowStrategyAgent Step 3")
    print("   - Removed static pattern summaries")
    print("   - Added explicit instructions to USE injected [INJECTED PATTERN GUIDANCE] section")
    print("   - Documented 5 components of injected guidance")
    print("   - Instructed agent to use Recommended Phases as template")
    return True

if __name__ == "__main__":
    success = update_step_3()
    sys.exit(0 if success else 1)
