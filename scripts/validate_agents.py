"""Quick validation script for Generator agents"""
import json

# Load agents.json
with open(r'workflows\Generator\agents.json', encoding='utf-8') as f:
    data = json.load(f)

agents = data['agents']

print("=" * 80)
print("AGENT VALIDATION REPORT")
print("=" * 80)

# Check section counts
print("\n### SECTION COUNTS ###")
for name, agent in agents.items():
    section_count = len(agent['prompt_sections'])
    structured_output = agent.get('structured_outputs_required', False)
    expected = 9 if structured_output else 8
    status = "✅" if section_count == expected else "❌"
    print(f"{status} {name}: {section_count} sections (expected {expected}, structured={structured_output})")

# Check for section ID mismatches
print("\n### SECTION ID VALIDATION ###")
standard_ids = ['role', 'objective', 'context', 'runtime_integrations', 'guidelines', 
                'instructions', 'pattern_guidance_and_examples', 'json_output_compliance', 'output_format']

for name, agent in agents.items():
    sections = agent['prompt_sections']
    section_ids = [s['id'] for s in sections]
    
    # Check for non-standard IDs
    non_standard = [sid for sid in section_ids if sid not in standard_ids]
    if non_standard:
        print(f"❌ {name}: Non-standard section IDs found: {non_standard}")
        
    # Check for section ID/heading mismatch
    for section in sections:
        sid = section['id']
        heading = section['heading']
        
        # Common mismatches
        if sid == 'responsibilities' and '[OBJECTIVE]' in heading:
            print(f"❌ {name}: Section ID '{sid}' doesn't match heading '{heading}'")

# Check for agent name references in content
print("\n### AGENT NAME REFERENCE CHECK ###")
agent_ref_patterns = ['Agent output', 'from Agent', 'Agent selected', 'Agent output']

for name, agent in agents.items():
    sections = agent['prompt_sections']
    for section in sections:
        content = section.get('content', '') or ''
        if isinstance(content, str):
            # Skip references to "agent" in lowercase (that's OK)
            # Look for "Agent" with capital A followed by specific patterns
            for pattern in agent_ref_patterns:
                if pattern in content:
                    print(f"⚠️  {name} [{section['id']}]: May contain agent name reference: '{pattern}'")
                    break

# Check auto_tool_mode alignment
print("\n### AUTO_TOOL_MODE VALIDATION ###")
for name, agent in agents.items():
    auto_tool = agent.get('auto_tool_mode', False)
    print(f"  {name}: auto_tool_mode={auto_tool}")

# Check structured_outputs_required
print("\n### STRUCTURED OUTPUTS ###")
for name, agent in agents.items():
    structured = agent.get('structured_outputs_required', False)
    print(f"  {name}: structured_outputs_required={structured}")

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
