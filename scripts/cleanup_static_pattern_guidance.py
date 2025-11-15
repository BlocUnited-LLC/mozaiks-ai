"""
Remove static [AG2 PATTERN GUIDANCE] sections from agent system messages.

These sections are now obsolete because update_agent_state hooks dynamically
inject pattern guidance at runtime.
"""
import json
import re
from pathlib import Path

# Path to agents.json
AGENTS_JSON = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

def remove_pattern_guidance_section(system_message: str) -> str:
    """Remove [AG2 PATTERN GUIDANCE] section from system message."""
    # Pattern to match the entire [AG2 PATTERN GUIDANCE] block
    # Match from the header until the next major section or end
    pattern = r'\n\n\[AG2 PATTERN GUIDANCE\].*?(?=\n\n\[|$)'
    
    # Remove the section
    cleaned = re.sub(pattern, '', system_message, flags=re.DOTALL)
    
    # Clean up any extra newlines left behind
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    return cleaned.strip()

def main():
    print("Loading agents.json...")
    with open(AGENTS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    agents_to_clean = [
        "WorkflowStrategyAgent",
        "WorkflowImplementationAgent",
        "ProjectOverviewAgent",
        "HandoffsAgent"
    ]
    
    cleaned_count = 0
    
    for agent_name in agents_to_clean:
        if agent_name not in data.get("agents", {}):
            print(f"⚠️  Agent '{agent_name}' not found in agents.json")
            continue
        
        agent = data["agents"][agent_name]
        original_message = agent.get("system_message", "")
        
        # Check if it contains the static guidance section
        if "[AG2 PATTERN GUIDANCE]" not in original_message:
            print(f"✓ Agent '{agent_name}' already clean (no static guidance found)")
            continue
        
        # Remove the section
        cleaned_message = remove_pattern_guidance_section(original_message)
        
        # Update the agent
        agent["system_message"] = cleaned_message
        cleaned_count += 1
        
        # Show what was removed
        removed_chars = len(original_message) - len(cleaned_message)
        print(f"✓ Cleaned '{agent_name}' (removed {removed_chars} chars)")
    
    if cleaned_count > 0:
        # Save the updated file
        print(f"\nSaving updated agents.json...")
        with open(AGENTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Successfully cleaned {cleaned_count} agent(s)")
    else:
        print("\n✅ No changes needed - all agents already clean")

if __name__ == "__main__":
    main()
