#!/usr/bin/env python3
"""
Add JSON compliance teaching instructions to AgentsAgent system message.

This ensures that when AgentsAgent generates workflow agents, those agents will include
the JSON OUTPUT COMPLIANCE section in their system messages, preventing the invalid escape
sequence errors that broke workflow generation.
"""

import json
from pathlib import Path

def main():
    agents_json_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    # Read agents.json
    with open(agents_json_path, "r", encoding="utf-8") as f:
        agents_data = json.load(f)
    
    # Get AgentsAgent system message
    agents_agent_msg = agents_data["agents"]["AgentsAgent"]["system_message"]
    
    # Check if already updated
    if "[JSON OUTPUT COMPLIANCE]** (MANDATORY for agents with structured_outputs_required=true)" in agents_agent_msg:
        print("✅ AgentsAgent already has JSON compliance teaching instructions")
        return
    
    # Find the section to update
    old_section = """8. **[INSTRUCTIONS]**: Step-by-step execution algorithm

9. **[OUTPUT FORMAT]**: 
   - If structured_outputs_required=true: Show exact JSON schema with example
   - If structured_outputs_required=false: Show text format or dialogue pattern"""
    
    new_section = """8. **[INSTRUCTIONS]**: Step-by-step execution algorithm

9. **[JSON OUTPUT COMPLIANCE]** (MANDATORY for agents with structured_outputs_required=true):
   - Add the complete JSON OUTPUT COMPLIANCE section teaching proper escaping
   - This prevents invalid escape sequence errors (\\', \\\\\\\") that break JSON parsing
   - Include ALL escaping rules with examples (docstrings, single quotes, backslashes)
   - Place AFTER [INSTRUCTIONS] and BEFORE [OUTPUT FORMAT]
   - Use the exact template from your own system message as reference

10. **[OUTPUT FORMAT]**: 
   - If structured_outputs_required=true: Show exact JSON schema with example
   - If structured_outputs_required=false: Show text format or dialogue pattern"""
    
    # Replace the section
    if old_section in agents_agent_msg:
        agents_agent_msg = agents_agent_msg.replace(old_section, new_section)
        agents_data["agents"]["AgentsAgent"]["system_message"] = agents_agent_msg
        
        # Write back to file
        with open(agents_json_path, "w", encoding="utf-8") as f:
            json.dump(agents_data, f, indent=2, ensure_ascii=False)
        
        print("✅ Updated AgentsAgent system message with JSON compliance teaching instructions")
        print("📝 AgentsAgent will now ensure all generated workflow agents include proper JSON escaping guidance")
    else:
        print("❌ Could not find expected section in AgentsAgent system message")
        print("Section to replace:", repr(old_section))

if __name__ == "__main__":
    main()
