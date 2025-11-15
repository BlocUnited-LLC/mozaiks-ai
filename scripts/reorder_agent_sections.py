"""
Reorder agent sections to standard structure:
[ROLE] → [OBJECTIVE] → [CONTEXT] → domain-specific → [GUIDELINES] → [INSTRUCTIONS] → [EXAMPLES] → [JSON OUTPUT COMPLIANCE] → [OUTPUT FORMAT]
"""
import json
from pathlib import Path

def reorder_agent_sections(agent_name, sections, structured_outputs_required):
    """Reorder sections to standard structure"""
    
    # Standard section order
    section_order = {
        '[ROLE]': 1,
        '[OBJECTIVE]': 2,
        '[CONTEXT]': 3,
        # domain-specific sections: 4-98 (anything not in this map)
        '[GUIDELINES]': 99,
        '[INSTRUCTIONS]': 100,
        '[EXAMPLES]': 101,
        '[JSON OUTPUT COMPLIANCE]': 102,
        '[OUTPUT FORMAT]': 103
    }
    
    # Sort sections by order
    def get_order(section):
        heading = section['heading']
        return section_order.get(heading, 50)  # domain-specific go in middle (50)
    
    reordered = sorted(sections, key=get_order)
    
    # Verify OUTPUT FORMAT exists
    has_output_format = any(s['heading'] == '[OUTPUT FORMAT]' for s in reordered)
    if not has_output_format:
        # Add OUTPUT FORMAT stub
        reordered.append({
            'id': 'output_format',
            'heading': '[OUTPUT FORMAT]',
            'content': '[TODO: define output format]'
        })
        print(f"  ⚠️  Added missing [OUTPUT FORMAT] section")
    
    return reordered

# Load agents.json
agents_path = Path('workflows/Generator/agents.json')
data = json.loads(agents_path.read_text(encoding='utf-8'))

# Reorder all agents
for agent_name, agent_config in data['agents'].items():
    print(f"\n{agent_name}:")
    original_count = len(agent_config['prompt_sections'])
    
    agent_config['prompt_sections'] = reorder_agent_sections(
        agent_name,
        agent_config['prompt_sections'],
        agent_config.get('structured_outputs_required', False)
    )
    
    new_count = len(agent_config['prompt_sections'])
    
    # Show new order
    for i, section in enumerate(agent_config['prompt_sections'], 1):
        print(f"  {i}. {section['heading']}")
    
    if new_count != original_count:
        print(f"  Section count: {original_count} → {new_count}")

# Save
agents_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
print(f"\n✓ All agents reordered to standard structure")
