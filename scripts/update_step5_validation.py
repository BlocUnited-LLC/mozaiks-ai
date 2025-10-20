"""
Add human_interaction validation checks to Step 5.
"""
import json
from pathlib import Path

agents_json_path = Path("workflows/Generator/agents.json")

# Read the current agents.json
with open(agents_json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get the AgentsAgent system message
system_message = data['agents']['AgentsAgent']['system_message']

# Find Step 5 and replace it
step5_start = system_message.find("Step 5 - Validate")
step6_start = system_message.find("Step 6 - Emit JSON")

if step5_start == -1 or step6_start == -1:
    print("❌ Could not find Step 5 or Step 6 markers")
    exit(1)

# New Step 5 with human_interaction validation
new_step5 = """Step 5 - Validate
  - All trigger tokens from ContextVariablesPlan have corresponding OUTPUT FORMAT constraints in source agents
  - All agent names match ActionPlan roster
  - All agents with human_interaction="context" have conversational system_message instructions
  - All agents with human_interaction="approval" have review/approval system_message instructions
  - All agents with human_interaction="none" have autonomous execution system_message instructions
  - No duplicate agent names
  - Deterministic ordering (lifecycle sequence)
  
"""

# Replace Step 5
new_system_message = system_message[:step5_start] + new_step5 + system_message[step6_start:]

# Update the data
data['agents']['AgentsAgent']['system_message'] = new_system_message

# Write back
with open(agents_json_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("✅ Successfully updated Step 5 validation rules")
print(f"   - Added human_interaction alignment validation checks")
print(f"   - New system_message length: {len(new_system_message)} characters")
