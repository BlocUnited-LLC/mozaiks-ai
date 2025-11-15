"""
Standardize agent prompt section headings across all Generator agents.

Standard structure:
1. [ROLE] - Agent identity and primary responsibility
2. [OBJECTIVE] - Key deliverables and goals
3. [CONTEXT] - Position in workflow, inputs/outputs
4. Domain-specific sections (varies by agent)
5. [GUIDELINES] - Compliance and legal requirements
6. [INSTRUCTIONS] - Step-by-step execution algorithm
7. [JSON OUTPUT COMPLIANCE] - Output formatting (if structured_outputs_required=true)
8. [OUTPUT FORMAT] - Expected output structure (if applicable)
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# Standard compliance text for GUIDELINES section
GUIDELINES_STANDARD = """You must follow these guidelines strictly for legal reasons. Do not stray from them.
Output Compliance: You must adhere to the specified "Output Format" and its instructions. Do not include any additional commentary in your output."""

# Standard JSON compliance text
JSON_COMPLIANCE_STANDARD = """(CRITICAL - REQUIRED FOR ALL STRUCTURED OUTPUTS)
You MUST follow this for legal purposes. Non-compliance will trigger immediate workflow termination.
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
  * WRONG: `"code": "def func():\\n    \\\\\\"\\\\\\"\\\\\\\"docstring\\\\\\"\\\\\\"\\\\\\\"\\n    pass"` (double-escaped)

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

**Summary**: Single-escape quotes (`\\"`), no markdown fences, valid JSON only."""

def ensure_core_sections(agent_name: str, sections: List[Dict], agent_config: Dict) -> tuple[List[Dict], List[str]]:
    """Ensure agent has all core sections, adding minimal stubs if missing."""
    changes = []
    headings = {s['heading'] for s in sections}
    
    # Core sections needed by ALL agents
    core_sections_needed = {
        '[ROLE]': 0,
        '[OBJECTIVE]': 1,
        '[CONTEXT]': 2,
        '[GUIDELINES]': -3,  # negative means insert from end
        '[INSTRUCTIONS]': -2,
    }
    
    # Add JSON OUTPUT COMPLIANCE only if structured_outputs_required=true
    if agent_config.get('structured_outputs_required', False):
        core_sections_needed['[JSON OUTPUT COMPLIANCE]'] = -1
    
    new_sections = []
    
    # Helper to create minimal stub sections
    def create_stub_section(heading: str) -> Dict:
        """Create a minimal stub section."""
        content_map = {
            '[ROLE]': f"You are the {agent_name} responsible for [TODO: define role].",
            '[OBJECTIVE]': "- [TODO: define objectives]",
            '[CONTEXT]': "- [TODO: define context and workflow position]",
            '[GUIDELINES]': GUIDELINES_STANDARD,
            '[INSTRUCTIONS]': "Step 1 - [TODO: define instructions]",
            '[JSON OUTPUT COMPLIANCE]': JSON_COMPLIANCE_STANDARD,
        }
        return {
            'id': heading.lower().replace('[', '').replace(']', '').replace(' ', '_').replace('-', '_'),
            'heading': heading,
            'content': content_map.get(heading, f"[TODO: define {heading}]")
        }
    
    # Build new sections list with proper ordering
    for heading, position in sorted(core_sections_needed.items(), key=lambda x: x[1] if x[1] >= 0 else 1000 + x[1]):
        if heading not in headings:
            stub = create_stub_section(heading)
            if position < 0:
                # Insert from end
                new_sections.append(stub)
            else:
                # Insert at specific position
                new_sections.insert(position, stub)
            changes.append(f"{agent_name}: Added missing {heading}")
            headings.add(heading)
    
    # Now merge with existing sections in proper order
    result_sections = []
    existing_added = set()
    
    # Add sections in standard order
    standard_order = ['[ROLE]', '[OBJECTIVE]', '[CONTEXT]']
    for heading in standard_order:
        # Add new stub if exists
        stub = next((s for s in new_sections if s['heading'] == heading), None)
        if stub:
            result_sections.append(stub)
            continue
        # Add existing section
        existing = next((s for s in sections if s['heading'] == heading), None)
        if existing:
            result_sections.append(existing)
            existing_added.add(heading)
    
    # Add all domain-specific sections (everything not in standard_order and not end sections)
    end_sections = ['[GUIDELINES]', '[INSTRUCTIONS]', '[JSON OUTPUT COMPLIANCE]', '[OUTPUT FORMAT]']
    for section in sections:
        if section['heading'] not in standard_order and section['heading'] not in end_sections and section['heading'] not in existing_added:
            result_sections.append(section)
            existing_added.add(section['heading'])
    
    # Add end sections in order
    for heading in end_sections:
        # Add new stub if exists
        stub = next((s for s in new_sections if s['heading'] == heading), None)
        if stub:
            result_sections.append(stub)
            continue
        # Add existing section
        existing = next((s for s in sections if s['heading'] == heading), None)
        if existing and existing['heading'] not in existing_added:
            result_sections.append(existing)
            existing_added.add(existing['heading'])
    
    return result_sections, changes

def standardize_headings(agents_path: Path) -> None:
    """Standardize agent prompt section headings."""
    
    # Load agents.json
    data = json.loads(agents_path.read_text(encoding='utf-8'))
    agents = data.get('agents', {})
    
    # Heading mappings for normalization
    NORMALIZE_HEADINGS = {
        '[RESPONSIBILITIES]': '[OBJECTIVE]',
        '[INPUTS]': '[CONTEXT]',
        '[OUTPUT]': '[OUTPUT FORMAT]',
        "[RUNTIME INTEGRATION - WHAT'S AUTOMATIC]": "[RUNTIME INTEGRATION]",
    }
    
    all_changes = []
    
    for agent_name, agent_config in agents.items():
        sections = agent_config.get('prompt_sections', [])
        if not sections:
            continue
            
        original_count = len(sections)
        modified_sections = []
        seen_headings = set()
        
        # First pass: normalize and deduplicate
        for section in sections:
            heading = section.get('heading', '')
            
            # Normalize heading
            normalized_heading = NORMALIZE_HEADINGS.get(heading, heading)
            
            # Skip duplicate JSON OUTPUT COMPLIANCE
            if normalized_heading == '[JSON OUTPUT COMPLIANCE]' and normalized_heading in seen_headings:
                all_changes.append(f"{agent_name}: Removed duplicate {heading}")
                continue
            
            # Update heading if normalized
            if normalized_heading != heading:
                section['heading'] = normalized_heading
                all_changes.append(f"{agent_name}: Renamed {heading} -> {normalized_heading}")
            
            seen_headings.add(section['heading'])
            modified_sections.append(section)
        
        # Second pass: ensure core sections exist
        final_sections, section_changes = ensure_core_sections(agent_name, modified_sections, agent_config)
        all_changes.extend(section_changes)
        
        # Update agent
        agent_config['prompt_sections'] = final_sections
        
        if len(final_sections) != original_count:
            all_changes.append(f"{agent_name}: Section count {original_count} -> {len(final_sections)}")
    
    # Write back to file
    agents_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    
    # Print summary
    print(f"Standardized {len(agents)} agents")
    print(f"\nChanges made ({len(all_changes)}):")
    for change in all_changes:
        print(f"  - {change}")

if __name__ == '__main__':
    agents_path = Path('workflows/Generator/agents.json')
    standardize_headings(agents_path)
    print("\n✓ Standardization complete")
