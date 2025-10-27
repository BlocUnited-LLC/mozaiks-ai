"""
Update WorkflowImplementationAgent OUTPUT FORMAT section to emphasize multi-phase list requirements.
"""

import json
from pathlib import Path

AGENTS_JSON = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

def main():
    with open(AGENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    original_message = data["agents"]["WorkflowImplementationAgent"]["system_message"]
    
    # Find and replace the OUTPUT FORMAT section
    old_section = '''## 8. YOUR OUTPUT: action_plan TOOL

After designing detailed implementation, call the `action_plan` tool with complete specifications:

```python
action_plan(
    workflow_name="[Same as strategy]",
    workflow_description="[Same as strategy or slightly expanded]",
    trigger="[Same as strategy]",
    interaction_mode="[Same as strategy]",
    pattern="[Same as strategy]",
    phases=[
        {
            "phase_name": "[Phase from strategy]",
            "phase_description": "[EXPANDED with specific agents and tools]",
            "agents": [
                {
                    "agent_name": "PascalCaseAgentName",
                    "agent_description": "2-3 sentence description",
                    "agent_system_message": "Detailed instructions using template",
                    "human_interaction": "none|approval|collaboration",
                    "tools": ["Tool1", "Tool2"],
                    "operations": ["Operation 1", "Operation 2"],
                    "integrations": ["Service1", "Service2"]
                }
                # ... more agents if parallel/sequential
            ]
        }
        # ... more phases
    ]
)
```'''
    
    new_section = '''## 8. YOUR OUTPUT: action_plan TOOL

After designing detailed implementation, call the `action_plan` tool with complete specifications:

```python
action_plan(
    workflow_name="[Same as strategy]",
    workflow_description="[Same as strategy or slightly expanded]",
    trigger="[Same as strategy]",
    interaction_mode="[Same as strategy]",
    pattern="[Same as strategy]",
    phases=[
        # CRITICAL: phases is a LIST that MUST mirror WorkflowStrategyAgent exactly
        # Each phase from strategy becomes one entry here (same name, same order, same approval flags)
        # Do NOT collapse, skip, or rename phases
        {
            "phase_name": "[Exact phase name from strategy - e.g., 'Phase 1: Content Ideation and Planning']",
            "phase_description": "[EXPANDED with specific agents and tools]",
            "agents": [
                {
                    "agent_name": "PascalCaseAgentName",
                    "agent_description": "2-3 sentence description",
                    "agent_system_message": "Detailed instructions using template",
                    "human_interaction": "none|approval|collaboration",
                    "tools": ["Tool1", "Tool2"],
                    "operations": ["Operation 1", "Operation 2"],
                    "integrations": ["Service1", "Service2"]
                }
                # ... more agents if parallel/sequential
            ]
        },
        # Repeat for EVERY phase from strategy (Phase 2, Phase 3, etc.)
        # Multi-phase workflows are expected; provide all phases in the list
    ]
)
```'''
    
    if old_section not in original_message:
        print("❌ Could not find OUTPUT FORMAT section to update")
        return 1
    
    updated_message = original_message.replace(old_section, new_section)
    data["agents"]["WorkflowImplementationAgent"]["system_message"] = updated_message
    
    with open(AGENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Updated WorkflowImplementationAgent OUTPUT FORMAT section with multi-phase list emphasis")
    return 0

if __name__ == "__main__":
    exit(main())
