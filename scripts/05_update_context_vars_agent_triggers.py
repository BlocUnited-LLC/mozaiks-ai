"""
Phase 2: Clarify trigger semantics in ContextVariablesAgent
Makes trigger.type (agent_text vs ui_response) differences explicit for downstream consumption.
"""
from pathlib import Path
import json

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read file
with open(agents_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find ContextVariablesAgent and update TRIGGER SEMANTICS section
context_vars_agent = data['agents']['ContextVariablesAgent']
system_msg = context_vars_agent['system_message']

# Find and replace existing TRIGGER SEMANTICS section
old_trigger_section = """2. TRIGGER SEMANTICS (CRITICAL FOR HANDOFFS):
   - agent_text triggers: Variables updated when specific agents emit coordination tokens (e.g., "NEXT", "PROCEED")
     * Evaluated AFTER agent completes its turn (post-reply)
     * Example: interview_complete set to True when intake agent emits "NEXT"
   - ui_response triggers: Variables updated when UI tools receive user interactions (e.g., button clicks)
     * Evaluated BEFORE next agent's turn (pre-reply) to catch asynchronous UI updates
     * Example: action_plan_acceptance set by MermaidSequenceDiagram tool when user clicks Approve/Reject"""

new_trigger_section = """2. TRIGGER SEMANTICS (CRITICAL FOR HANDOFFS):
   - agent_text triggers: Variables updated when specific agents emit coordination tokens (e.g., "NEXT", "PROCEED")
     * Evaluated AFTER agent completes its turn (post-reply)
     * Example: interview_complete set to True when intake agent emits "NEXT"
   - ui_response triggers: Variables updated when UI tools receive user interactions (e.g., button clicks)
     * Evaluated BEFORE next agent's turn (pre-reply) to catch asynchronous UI updates
     * Example: action_plan_acceptance set by MermaidSequenceDiagram tool when user clicks Approve/Reject

CRITICAL DISTINCTION FOR DOWNSTREAM AGENTS:
   - agent_text: Tool code does NOT set the variable (DerivedContextManager detects agent's text output)
   - ui_response: Tool code MUST explicitly set the variable (via runtime['context_variables'].set(...))
   - This distinction determines condition_scope in handoffs.json (null vs "pre")"
"""

if old_trigger_section in system_msg:
    system_msg = system_msg.replace(old_trigger_section, new_trigger_section)
    context_vars_agent['system_message'] = system_msg
    
    # Write back
    with open(agents_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Successfully updated TRIGGER SEMANTICS in ContextVariablesAgent")
    print("\nKey additions:")
    print("- Clarified agent_text = passive detection (no tool code needed)")
    print("- Clarified ui_response = active setting (tool must set variable)")
    print("- Linked trigger type to handoff condition_scope downstream")
else:
    print("⚠️  Could not find exact trigger section to replace")
    print("Trigger semantics may have been modified - manual review needed")
