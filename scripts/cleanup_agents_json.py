"""
Script to clean up agents.json:
1. Remove 'guidelines' section from all agents
2. Remove 'json_output_compliance' section from all agents
3. Remove 'runtime_integrations' section from all agents
4. Move agent-specific guidelines content into instructions where needed

The hook system injects universal guidelines, JSON compliance, and runtime context at runtime.
"""

import json
from pathlib import Path

def cleanup_agents_json():
    agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    with open(agents_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Sections to remove entirely (now handled by hooks)
    sections_to_remove = ["guidelines", "json_output_compliance", "runtime_integrations"]
    
    for agent_name, agent_data in data["agents"].items():
        sections = agent_data.get("prompt_sections", [])
        
        # Remove specified sections
        agent_data["prompt_sections"] = [
            s for s in sections if s["id"] not in sections_to_remove
        ]
    
    # Write back
    with open(agents_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Cleaned up agents.json")
    print(f"  - Removed sections: {sections_to_remove}")

if __name__ == "__main__":
    cleanup_agents_json()
