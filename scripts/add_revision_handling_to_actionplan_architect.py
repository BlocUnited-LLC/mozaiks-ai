"""
Add revision handling instructions to ActionPlanArchitect system message.

This script updates the ActionPlanArchitect agent's system message to include
instructions for handling user revision requests, allowing the agent to modify
existing action plans instead of regenerating from scratch.
"""

import json
from pathlib import Path

def main():
    agents_json_path = Path("workflows/Generator/agents.json")
    
    if not agents_json_path.exists():
        print(f"❌ Error: {agents_json_path} not found")
        return 1
    
    # Read current agents.json
    with open(agents_json_path, "r", encoding="utf-8") as f:
        agents_data = json.load(f)
    
    # Locate ActionPlanArchitect
    architect_agent = agents_data.get("agents", {}).get("ActionPlanArchitect")
    if not architect_agent:
        print("❌ Error: ActionPlanArchitect not found in agents.json")
        return 1
    
    current_msg = architect_agent.get("system_message", "")
    
    # Check if revision handling already exists
    if "REVISION HANDLING" in current_msg or "existing action plan" in current_msg.lower():
        print("✅ Revision handling instructions already present")
        return 0
    
    # Find insertion point (after [GUIDELINES] section, before [WORKFLOW INITIATION SEMANTICS])
    insertion_marker = "[WORKFLOW INITIATION SEMANTICS]"
    
    if insertion_marker not in current_msg:
        print(f"❌ Error: Could not find insertion point '{insertion_marker}'")
        return 1
    
    revision_section = """

[REVISION HANDLING] (CRITICAL - Handle user feedback correctly)

**BEFORE generating a new Action Plan, check context variables for an existing plan:**

1. **Check for existing action_plan in context:**
   - If `action_plan` context variable exists with a workflow object, this is a REVISION REQUEST
   - The user wants to MODIFY the existing plan, NOT create a new one from scratch
   
2. **Detect revision intent from user message:**
   - Keywords indicating revision: "change", "modify", "remove", "add", "update", "adjust", "revise", "edit", "get rid of", "take out", "delete"
   - Examples:
     * "remove the validate_inputs operation"
     * "add an approval step before payment"
     * "change the integration from Stripe to MozaiksPay"
     * "get rid of the email notification"
   
3. **When handling revisions:**
   - Start with the existing workflow from context
   - Identify EXACTLY what the user wants changed (be specific, don't guess)
   - Modify ONLY the requested elements:
     * If removing operation: delete from operations array
     * If adding agent: insert in appropriate phase
     * If changing integration: replace in integrations array
     * If modifying description: update the text
   - Preserve ALL other parts of the workflow unchanged:
     * Keep same workflow.name
     * Keep same initiated_by, trigger_type, interaction_mode
     * Keep same phase structure unless explicitly requested to change
     * Keep same agent names unless explicitly requested to change
   
4. **Revision output format:**
   - Return the COMPLETE modified ActionPlan (not a diff, not just changes)
   - Include agent_message acknowledging what was changed
   - Example: "Updated RequirementsAgent to remove input validation operation as requested."
"""
    
    # Insert revision section
    new_msg = current_msg.replace(
        insertion_marker,
        revision_section + insertion_marker
    )
    
    # Update the agent
    architect_agent["system_message"] = new_msg
    agents_data["agents"]["ActionPlanArchitect"] = architect_agent
    
    # Write back
    with open(agents_json_path, "w", encoding="utf-8") as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print("✅ Successfully added revision handling instructions to ActionPlanArchitect")
    print(f"   - Inserted {len(revision_section)} characters")
    print(f"   - New system_message length: {len(new_msg)} characters")
    print("\n📋 Added revision handling section:")
    print("   - Check for existing action_plan in context")
    print("   - Detect revision keywords in user message")
    print("   - Modify only requested elements")
    print("   - Preserve unchanged parts of workflow")
    
    return 0

if __name__ == "__main__":
    exit(main())
