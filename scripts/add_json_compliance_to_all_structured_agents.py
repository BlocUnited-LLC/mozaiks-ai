#!/usr/bin/env python3
"""
Add JSON output compliance contract to ALL agents with structured_outputs_required=true.

These agents must output valid JSON and are failing due to invalid escape sequences.
This script adds comprehensive JSON escaping instructions to their system messages.
"""
import json
from pathlib import Path

def main():
    agents_json_path = Path("workflows/Generator/agents.json")
    
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    agents_dict = agents_data.get('agents', {})
    
    # Comprehensive JSON compliance contract
    json_compliance = """

[JSON OUTPUT COMPLIANCE] (CRITICAL - REQUIRED FOR ALL STRUCTURED OUTPUTS)
You MUST output valid, parseable JSON. Follow these rules EXACTLY:

**1. Output Format**:
- Output ONLY raw JSON object - no markdown code fences (```json), no explanatory text
- JSON must be valid and parseable by json.loads() without any cleaning

**2. String Escaping (CRITICAL)**:
When JSON strings contain special characters, escape them correctly:
- Double quotes: Use `\\"` (single backslash + quote)
  * CORRECT: `"description": "This is a \\"quoted\\" word"`
  * WRONG: `"description": "This is a \\\\\\"quoted\\\\\\" word"` (double-escaped)

- Python docstrings (triple quotes): Use `\\"\\"\\"` (escape each quote separately)
  * CORRECT: `"code": "def func():\\n    \\"\\"\\"This is a docstring\\"\\"\\"\\n    pass"`
  * WRONG: `"code": "def func():\\n    \\\\\\"\\\\\\"\\\\\\"docstring\\\\\\"\\\\\\"\\\\\\"\\n    pass"` (double-escaped)

- Single quotes in strings: Use `'` (NO escaping needed in JSON)
  * CORRECT: `"text": "It's a test"`
  * WRONG: `"text": "It\\'s a test"` (invalid escape sequence)

- Backslashes: Use `\\\\` (double backslash)
  * CORRECT: `"path": "C:\\\\Users\\\\file.txt"`
  * WRONG: `"path": "C:\\Users\\file.txt"` (incomplete escape)

- Newlines: Use `\\n`, tabs: Use `\\t`
  * CORRECT: `"code": "line1\\nline2"`

**3. No Trailing Commas**:
- Remove commas before closing brackets
  * CORRECT: `{"a": 1, "b": 2}`
  * WRONG: `{"a": 1, "b": 2,}` (trailing comma)

**4. No Trailing Garbage**:
- JSON must end with final closing brace `}`
- NO additional text, notes, or comments after JSON
  * CORRECT: `{"status": "complete"}`
  * WRONG: `{"status": "complete"} **Note: Additional info...` (trailing text)

**5. Test Your Output**:
Before emitting, mentally verify your JSON would pass:
```python
import json
json.loads(your_output)  # Must succeed without error
```

**Common Error Examples**:
❌ `Invalid \\escape` - You used `\\'` or other invalid escape sequence
❌ `Expecting ',' delimiter` - You double-escaped quotes inside strings (`\\\\\\"` instead of `\\"`)
❌ `Unterminated string` - You forgot to escape quotes or newlines

**Summary**: Single-escape quotes (`\\"`), no markdown fences, valid JSON only.
"""
    
    updated_count = 0
    
    # Find all agents with structured_outputs_required=true
    for agent_name, agent_config in agents_dict.items():
        if not isinstance(agent_config, dict):
            continue
            
        if not agent_config.get('structured_outputs_required', False):
            continue  # Skip agents without structured outputs
        
        system_message = agent_config.get('system_message', '')
        
        # Check if compliance already added
        if '[JSON OUTPUT COMPLIANCE]' in system_message:
            print(f"⏭️  {agent_name} already has JSON compliance")
            continue
        
        # Add compliance at the end (before final section if any, otherwise at end)
        # Most agents end with [OUTPUT FORMAT] or [EXAMPLE] sections
        # We'll add just before the last major section
        
        # Find last major section marker (starts with \n[)
        last_section_idx = system_message.rfind('\n[')
        
        if last_section_idx != -1:
            # Insert before last section
            before = system_message[:last_section_idx]
            after = system_message[last_section_idx:]
            agent_config['system_message'] = before + json_compliance + after
        else:
            # No section found, append to end
            agent_config['system_message'] = system_message + json_compliance
        
        updated_count += 1
        print(f"✅ Added JSON compliance to {agent_name}")
    
    # Write back
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Updated {updated_count} agents with JSON output compliance")
    print("This should fix all 'Invalid \\escape' and 'Expecting , delimiter' errors")

if __name__ == "__main__":
    main()
