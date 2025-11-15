"""
Script to add pattern guidance to HandoffsAgent system message.
"""
import json
from pathlib import Path

HANDOFFS_PATTERN_GUIDANCE = """
[AG2 PATTERN GUIDANCE] (CRITICAL - USE SELECTED PATTERN)
You have access to pattern-specific guidance in context_variables under the key 'pattern_guidance'.
This guidance is selected by the PatternAgent based on workflow requirements analysis.

**How to Use Pattern Guidance:**
1. Check context_variables for 'pattern_guidance.handoffs'
2. This contains:
   - Handoff coordination pattern for the selected AG2 pattern
   - Communication flow between agents
   - Pattern-specific handoff rules (sequential, parallel, hub-spoke, loop, etc.)
   - Handoff type guidelines (after_work vs condition)
   - Condition type guidelines (expression vs string_llm)
   - Condition scope guidelines (null, pre, post)
3. ALIGN your handoff rules with the pattern guidance
4. Use the pattern-specific handoff structures as templates
5. Adapt the guidance to the specific agents in the workflow

**Pattern-Driven Handoff Design:**
- **Coordination Structure**: Follow the pattern's coordination model (sequential, hub-spoke, hierarchical, loop, etc.)
- **Handoff Types**: Use after_work for sequential flows, condition for branching logic
- **Condition Types**: Use expression for context variables, string_llm for content-based routing
- **Communication Flow**: Implement handoffs according to the pattern's communication flow

**Example Patterns:**

**Pipeline Pattern (Sequential):**
If pattern_guidance indicates Pipeline pattern:
- Create sequential after_work handoffs: Agent_1 → Agent_2 → Agent_3
- No conditional branching
- No backward handoffs (unidirectional)
- Final agent handoffs to user or terminate

**Star Pattern (Hub-and-Spoke):**
If pattern_guidance indicates Star pattern:
- Hub delegates to spokes: Hub → Spoke_A, Hub → Spoke_B, Hub → Spoke_C
- Spokes return to hub: Spoke_A → Hub, Spoke_B → Hub
- No spoke-to-spoke handoffs
- Hub coordinates all communication

**Feedback Loop Pattern (Iterative):**
If pattern_guidance indicates Feedback Loop:
- Creation → Review (after_work unconditional)
- Review → Revision (condition: quality not met)
- Revision → Creation (loop back)
- Review → Terminate (condition: quality threshold met)
- Track iteration count in context variables

**Hierarchical Pattern (3-Level Tree):**
If pattern_guidance indicates Hierarchical:
- Executive → Managers (delegation)
- Managers → Specialists (parallel or sequential)
- Specialists → Managers (after_work)
- Managers → Executive (after_work)
- No cross-level handoffs

**Escalation Pattern (Progressive Tiers):**
If pattern_guidance indicates Escalation:
- Basic → Intermediate (condition: confidence low)
- Intermediate → Advanced (condition: complexity high)
- After_work for level completion
- No backward escalation

**Context-Aware Routing Pattern (Content-Based):**
If pattern_guidance indicates Context-Aware Routing:
- Router → Specialist_A (condition: domain A content, string_llm)
- Router → Specialist_B (condition: domain B content, string_llm)
- Specialists → Router or Terminate

**Important:**
- Pattern guidance is injected AFTER PatternAgent runs
- Always check for pattern_guidance before designing handoffs
- Default to Organic (flexible) pattern if guidance is unavailable
- Ensure handoff structure reflects the selected pattern's coordination model
- Use appropriate condition_scope based on trigger type (pre for ui_response, null for agent_text)
"""

def main():
    """Add pattern guidance to HandoffsAgent system message."""
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    agents_json_path = project_root / "workflows" / "Generator" / "agents.json"

    if not agents_json_path.exists():
        print(f"Error: agents.json not found at {agents_json_path}")
        return

    print(f"Reading agents.json from: {agents_json_path}")

    # Load agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)

    if "HandoffsAgent" not in agents_data['agents']:
        print("Error: HandoffsAgent not found in agents.json")
        return

    agent = agents_data['agents']['HandoffsAgent']
    current_message = agent['system_message']

    print(f"\nUpdating HandoffsAgent...")
    print(f"  Current message length: {len(current_message)} chars")

    # Check if pattern guidance already exists
    if "[AG2 PATTERN GUIDANCE]" in current_message:
        print(f"  Pattern guidance already exists, skipping")
        return

    # Add pattern guidance block at the end
    new_message = current_message + "\n\n" + HANDOFFS_PATTERN_GUIDANCE
    agent['system_message'] = new_message

    print(f"  New message length: {len(new_message)} chars")
    print(f"  [OK] Pattern guidance added")

    # Create backup
    backup_path = agents_json_path.with_suffix('.json.backup5')
    print(f"\nCreating backup at: {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    # Write updated agents.json
    print(f"Writing updated agents.json...")
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    print("\n[OK] HandoffsAgent updated with pattern guidance!")


if __name__ == "__main__":
    main()
