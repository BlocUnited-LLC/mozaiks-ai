"""
Update agent system messages to reference structured output schemas instead of agent names.
Agents don't know other agent names; they only see the structured outputs.
"""

import json
from pathlib import Path

AGENTS_JSON = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

REPLACEMENTS = [
    # WorkflowStrategyAgent references
    ("WorkflowStrategyAgent", "WorkflowStrategyCall"),
    
    # In context of reading from context variables, use the cached key name
    ("from WorkflowStrategyAgent", "from upstream WorkflowStrategyCall output"),
    ("provided by WorkflowStrategyAgent", "provided by the upstream WorkflowStrategyCall output"),
    ("WorkflowImplementationAgent must mirror your phases", "WorkflowImplementationAgent must mirror your WorkflowStrategyCall.phases"),
    
    # ActionPlanArchitect references
    ("ActionPlanArchitect output", "ActionPlanCall output"),
    ("from ActionPlanArchitect", "from upstream ActionPlanCall"),
    ("ActionPlanArchitect)", "ActionPlanCall output)"),
]

def main():
    with open(AGENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    updates_count = 0
    
    for agent_name, agent_config in data["agents"].items():
        if "system_message" not in agent_config:
            continue
            
        original_message = agent_config["system_message"]
        updated_message = original_message
        
        for old_ref, new_ref in REPLACEMENTS:
            if old_ref in updated_message:
                updated_message = updated_message.replace(old_ref, new_ref)
                updates_count += 1
        
        if updated_message != original_message:
            agent_config["system_message"] = updated_message
            print(f"✅ Updated {agent_name}")
    
    if updates_count > 0:
        with open(AGENTS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Applied {updates_count} schema reference updates across agents")
    else:
        print("❌ No agent name references found to update")
    
    return 0

if __name__ == "__main__":
    exit(main())
