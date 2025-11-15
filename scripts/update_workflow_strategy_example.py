"""
Update WorkflowStrategyAgent example to follow 2-3 word naming constraint.

Changes "Automated Marketing Content Creation" (4 words) to "Marketing Content Creator" (3 words).
"""
import json
from pathlib import Path

def main():
    agents_file = Path("workflows/Generator/agents.json")
    
    with open(agents_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Find WorkflowStrategyAgent
    if "WorkflowStrategyAgent" not in data.get("agents", {}):
        print("❌ WorkflowStrategyAgent not found")
        return
    
    system_message = data["agents"]["WorkflowStrategyAgent"]["system_message"]
    
    # Update example to follow 2-3 word constraint
    old_example_name = 'workflow_name="Automated Marketing Content Creation"'
    new_example_name = 'workflow_name="Marketing Content Creator"'
    
    if old_example_name not in system_message:
        print("❌ Could not find example to update")
        return
    
    # Replace the example
    updated_message = system_message.replace(old_example_name, new_example_name)
    
    # Update the system message
    data["agents"]["WorkflowStrategyAgent"]["system_message"] = updated_message
    
    # Write back to file
    with open(agents_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Updated WorkflowStrategyAgent example to follow 2-3 word constraint")
    print("   Changed: 'Automated Marketing Content Creation' → 'Marketing Content Creator'")

if __name__ == "__main__":
    main()
