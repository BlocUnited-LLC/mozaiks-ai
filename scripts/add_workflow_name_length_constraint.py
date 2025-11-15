"""
Add workflow name length constraint to WorkflowStrategyAgent.

This script updates the WorkflowStrategyAgent system message to enforce
concise workflow names (2-3 words max) to prevent unwieldy file paths.
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
    
    # Find the guideline about workflow_name and add length constraint after it
    old_guideline = "- Use Title Case With Spaces for workflow_name; never emit PascalCase, kebab-case, or snake_case."
    new_guideline = (
        "- Use Title Case With Spaces for workflow_name; never emit PascalCase, kebab-case, or snake_case.\n"
        "- Keep workflow_name concise: 2-3 words maximum (e.g., \"Content Creator\", \"Story Builder\", \"Report Generator\"). "
        "Long names create unwieldy file paths and zip archives."
    )
    
    if old_guideline not in system_message:
        print("❌ Could not find guideline to update")
        print("   Searching for:", old_guideline)
        return
    
    # Replace the guideline
    updated_message = system_message.replace(old_guideline, new_guideline)
    
    # Update the system message
    data["agents"]["WorkflowStrategyAgent"]["system_message"] = updated_message
    
    # Write back to file
    with open(agents_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Added workflow name length constraint to WorkflowStrategyAgent")
    print("📝 WorkflowStrategyAgent will now enforce 2-3 word workflow names")

if __name__ == "__main__":
    main()
