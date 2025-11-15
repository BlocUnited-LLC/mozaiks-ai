"""
Remove decorative separator lines from PatternAgent's CONTEXT and EXAMPLES sections
"""
import json
import re
from pathlib import Path

# Load
data = json.loads(Path('workflows/Generator/agents.json').read_text(encoding='utf-8'))
agent = data['agents']['PatternAgent']

# Process each section
for section in agent['prompt_sections']:
    if section['heading'] in ['[CONTEXT]', '[EXAMPLES]']:
        # Remove the Unicode box-drawing separator lines
        # Pattern: \u2550 (═) repeated 7 or more times, possibly with trailing backslash
        content = section['content']
        
        # Remove lines that are just separator characters
        content = re.sub(r'\n═+\\?\n', '\n\n', content)  # Separator on its own line
        content = re.sub(r'═+\\?\n', '\n', content)      # Separator at start
        content = re.sub(r'\n═+\\?$', '', content)        # Separator at end
        
        # Clean up multiple consecutive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        section['content'] = content.strip()
        print(f"Cleaned {section['heading']}")

# Save
Path('workflows/Generator/agents.json').write_text(json.dumps(data, indent=2), encoding='utf-8')

print(f"\n✓ Removed decorative separators from PatternAgent")
