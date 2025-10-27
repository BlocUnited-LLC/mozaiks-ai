"""
Phase 2: Add CONDITION SCOPE RULES to HandoffsAgent
Explains when to use condition_scope="pre" vs null for proper handoff timing.
"""
from pathlib import Path
import json

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read file
with open(agents_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find HandoffsAgent and add condition scope rules
handoffs_agent = data['agents']['HandoffsAgent']
system_msg = handoffs_agent['system_message']

# Check if already exists
marker = "[CONDITION SCOPE RULES]"

if marker in system_msg:
    print("⚠️  [CONDITION SCOPE RULES] already exists in HandoffsAgent")
else:
    # New section to add
    new_section = """[CONDITION SCOPE RULES]
For handoff_type="condition" with condition_type="expression":

- condition_scope="pre" (Pre-Reply Context Conditions):
  * Use when: Context variable updated by UI tool responses (trigger.type="ui_response")
  * Why: Variable changes AFTER agent finishes, need re-evaluation before next turn
  * Pattern: User interaction → tool updates variable → pre-reply check catches it
  * Example: ${action_plan_acceptance} == "accepted" (set by UI tool, checked before user's next turn)

- condition_scope=null (Default Context Conditions):
  * Use when: Context variable updated by agent text emission (trigger.type="agent_text")
  * Why: Variable changes DURING agent's turn, available immediately after
  * Pattern: Agent emits token → variable updates → post-reply check sees it
  * Example: ${interview_complete} == True (set when agent emits "NEXT", checked after agent finishes)

For handoff_type="condition" with condition_type="string_llm":
- condition_scope: ALWAYS null (LLM conditions don't use scope, evaluated during reply)

For handoff_type="after_work":
- condition_scope: ALWAYS null (no condition to scope)

"""

    # Find insertion point - after [AG2 HANDOFF EVALUATION ORDER] section
    insertion_marker = "[GUIDELINES]"
    if insertion_marker in system_msg:
        parts = system_msg.split(insertion_marker, 1)
        system_msg = parts[0] + new_section + "\n" + insertion_marker + parts[1]
        handoffs_agent['system_message'] = system_msg
        
        # Write back
        with open(agents_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print("✅ Successfully added [CONDITION SCOPE RULES] to HandoffsAgent")
        print("\nKey additions:")
        print("- Pre-reply vs default evaluation timing explained")
        print("- UI tool response handling (scope=pre)")
        print("- Agent text emission handling (scope=null)")
        print("- Clear examples for each scope type")
    else:
        print(f"❌ Could not find insertion marker: {insertion_marker}")
