"""
Analyze content within prompt_sections for non-canonical nested headings.
These are headings that appear INSIDE the content field, not as section IDs.
"""
import json
import re
from pathlib import Path

def find_nested_headings(content):
    """Extract all [HEADING] patterns from content text."""
    if not content:
        return []
    
    # Match patterns like [HEADING] or [HEADING - SUBHEADING]
    pattern = r'\[([A-Z][A-Z\s\-/]+)\]'
    matches = re.findall(pattern, content)
    return matches

def analyze_content_headings():
    agents_path = Path("workflows/Generator/agents.json")
    
    with open(agents_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    agents = data.get("agents", {})
    
    print("=" * 80)
    print("NESTED HEADINGS WITHIN SECTION CONTENT ANALYSIS")
    print("=" * 80)
    print()
    
    all_nested_headings = set()
    agents_with_nested = {}
    
    for agent_name, agent_config in agents.items():
        prompt_sections = agent_config.get("prompt_sections", [])
        
        nested_by_section = {}
        
        for section in prompt_sections:
            section_id = section.get("id", "NO_ID")
            content = section.get("content", "")
            
            nested_headings = find_nested_headings(content)
            
            if nested_headings:
                nested_by_section[section_id] = nested_headings
                all_nested_headings.update(nested_headings)
        
        if nested_by_section:
            agents_with_nested[agent_name] = nested_by_section
    
    # Print results
    if agents_with_nested:
        print(f"⚠️  {len(agents_with_nested)} AGENTS HAVE NESTED HEADINGS IN CONTENT:\n")
        
        for agent_name, sections in agents_with_nested.items():
            print(f"\n{'=' * 80}")
            print(f"AGENT: {agent_name}")
            print(f"{'=' * 80}")
            
            for section_id, headings in sections.items():
                print(f"\n  Section ID: {section_id}")
                print(f"  Nested headings found ({len(headings)}):")
                for heading in headings:
                    print(f"    • [{heading}]")
    else:
        print("✅ NO NESTED HEADINGS FOUND IN CONTENT\n")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"Total agents analyzed: {len(agents)}")
    print(f"Agents with nested headings: {len(agents_with_nested)}")
    print(f"Total unique nested headings: {len(all_nested_headings)}")
    
    if all_nested_headings:
        print("\nAll unique nested headings found:")
        for heading in sorted(all_nested_headings):
            print(f"  • [{heading}]")

if __name__ == "__main__":
    analyze_content_headings()
