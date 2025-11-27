"""
Migrate all remaining 'derived' type instances to proper six-type taxonomy.
Classification rules:
- Orchestration flags/status → state
- Aggregated data collections → data_entity
- Calculated values → computed
"""
import re

def classify_variable(name, purpose, trigger_hint):
    """Classify derived variable based on semantic meaning."""
    name_lower = name.lower()
    purpose_lower = purpose.lower()
    trigger_lower = trigger_hint.lower()
    
    # State: orchestration flags, status tracking, completion markers
    state_keywords = ['status', 'complete', 'ready', 'started', 'done', 'flag', 
                     'stage', 'current', 'active', 'selected', 'answered']
    if any(kw in name_lower or kw in purpose_lower for kw in state_keywords):
        if 'set when' in trigger_lower or 'updated when' in trigger_lower:
            return 'state'
    
    # Data_entity: collections, logs, registries, snapshots that persist
    data_entity_keywords = ['log', 'registry', 'pool', 'collection', 'snapshot',
                           'assignments', 'updates', 'notes', 'submissions', 'matrix']
    if any(kw in name_lower or kw in purpose_lower for kw in data_entity_keywords):
        if 'appended' in trigger_lower or 'recorded' in trigger_lower:
            return 'data_entity'
    
    # Computed: calculations, aggregations, scoring
    computed_keywords = ['confidence', 'score', 'calculation', 'evaluation', 
                        'recommendation', 'result', 'summary']
    if any(kw in name_lower or kw in purpose_lower for kw in computed_keywords):
        return 'computed'
    
    # Default to state for orchestration-like variables
    return 'state'

# Read file
with open('workflows/Generator/tools/update_agent_state_pattern.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all derived variables in TechnicalBlueprint examples
pattern = r'{\s*\n\s*"name":\s*"([^"]+)",\s*\n\s*"type":\s*"derived",\s*\n\s*"purpose":\s*"([^"]+)",\s*\n\s*"trigger_hint":\s*"([^"]+)"'

matches = list(re.finditer(pattern, content))
print(f"Found {len(matches)} TechnicalBlueprint derived variables\n")

replacements = []
for match in matches:
    name = match.group(1)
    purpose = match.group(2)
    trigger_hint = match.group(3)
    classification = classify_variable(name, purpose, trigger_hint)
    
    old_text = match.group(0)
    new_text = old_text.replace('"type": "derived"', f'"type": "{classification}"')
    replacements.append((old_text, new_text, name, classification))
    print(f"✓ {name}: derived → {classification}")

# Apply replacements
for old, new, name, classification in replacements:
    content = content.replace(old, new, 1)

# Now handle ContextVariablesPlan examples with triggers
# Pattern for derived with trigger blocks
plan_pattern = r'"type":\s*"derived",\s*\n\s*"(?:description|default)":'

plan_matches = list(re.finditer(plan_pattern, content))
print(f"\n\nFound {len(plan_matches)} ContextVariablesPlan derived instances")
print("Replacing with 'state' (orchestration variables)...")

content = re.sub(
    r'"type":\s*"derived",',
    '"type": "state",',
    content
)

# Write updated content
with open('workflows/Generator/tools/update_agent_state_pattern.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n✓ Migration complete!")
print(f"✓ {len(matches)} TechnicalBlueprint variables classified")
print(f"✓ {len(plan_matches)} ContextVariablesPlan variables updated to 'state'")
