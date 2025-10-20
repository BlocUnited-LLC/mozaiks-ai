"""
Script to remove model field from ActionPlanArchitect system message
"""
import json
import re

# Read the agents.json file
with open('workflows/Generator/agents.json', 'r', encoding='utf-8') as f:
    agents = json.load(f)

# Get the system message
system_message = agents['agents']['ActionPlanArchitect']['system_message']

# Remove instruction #5 about adding the model
system_message = re.sub(
    r'5\. \*\*Add the model\*\* used by agents \(e\.g\., gpt-4o-mini, gpt-5\)\. This value is MANDATORY\.\n\n',
    '',
    system_message
)

# Renumber instructions 6-12 to 5-11
for i in range(12, 5, -1):
    system_message = system_message.replace(f'{i}. **', f'{i-1}. **')

# Remove "model" field from all three examples
# Pattern: "model": "gpt-4o-mini",\n
system_message = re.sub(
    r'      "model": "gpt-4o-mini",\n',
    '',
    system_message
)

# Remove "model" line from OUTPUT STRUCTURE
system_message = re.sub(
    r'      "model": "str — LLM model \(e\.g\., gpt-4o-mini\)",\n',
    '',
    system_message
)

# Update the agents.json
agents['agents']['ActionPlanArchitect']['system_message'] = system_message

# Write back
with open('workflows/Generator/agents.json', 'w', encoding='utf-8') as f:
    json.dump(agents, f, indent=4, ensure_ascii=False)

print("✅ Successfully removed model field from ActionPlanArchitect system message")
print("   - Removed instruction #5 about adding model")
print("   - Renumbered instructions 6-12 to 5-11")
print("   - Removed model field from all 3 examples")
print("   - Removed model field from OUTPUT STRUCTURE schema")
