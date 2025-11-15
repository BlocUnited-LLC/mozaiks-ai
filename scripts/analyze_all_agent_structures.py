"""
Comprehensive analysis of all Generator agent prompt_sections structures.
Identifies canonical vs non-canonical headings for standardization.
"""
import json
from pathlib import Path
from collections import defaultdict

# Canonical structure
CANONICAL_SECTIONS = {
    "role", "objective", "context", "runtime_integrations", 
    "guidelines", "instructions", "examples", 
    "json_output_compliance", "output_format"
}

def analyze_agents():
    agents_path = Path("workflows/Generator/agents.json")
    
    with open(agents_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    agents = data.get("agents", {})
    
    print("=" * 80)
    print("COMPREHENSIVE AGENT PROMPT SECTIONS ANALYSIS")
    print("=" * 80)
    print()
    
    all_section_ids = set()
    all_headings = set()
    non_canonical_by_agent = {}
    
    for agent_name, agent_config in agents.items():
        prompt_sections = agent_config.get("prompt_sections", [])
        
        print(f"\n{'=' * 80}")
        print(f"AGENT: {agent_name}")
        print(f"{'=' * 80}")
        print(f"Total sections: {len(prompt_sections)}")
        print()
        
        section_ids = []
        headings = []
        non_canonical = []
        
        for section in prompt_sections:
            section_id = section.get("id", "NO_ID")
            heading = section.get("heading", "NO_HEADING")
            
            section_ids.append(section_id)
            headings.append(heading)
            all_section_ids.add(section_id)
            all_headings.add(heading)
            
            # Check if canonical
            if section_id not in CANONICAL_SECTIONS:
                non_canonical.append({
                    "id": section_id,
                    "heading": heading,
                    "has_content": bool(section.get("content"))
                })
        
        # Print section structure
        print("Section IDs (in order):")
        for i, sid in enumerate(section_ids, 1):
            status = "✓" if sid in CANONICAL_SECTIONS else "✗ NON-CANONICAL"
            print(f"  {i}. {sid:<40} {status}")
        
        print()
        print("Headings (in order):")
        for i, h in enumerate(headings, 1):
            print(f"  {i}. {h}")
        
        if non_canonical:
            print()
            print(f"⚠️  NON-CANONICAL SECTIONS FOUND ({len(non_canonical)}):")
            for nc in non_canonical:
                content_status = "with content" if nc["has_content"] else "EMPTY"
                print(f"  • id={nc['id']}")
                print(f"    heading={nc['heading']}")
                print(f"    status={content_status}")
            non_canonical_by_agent[agent_name] = non_canonical
        else:
            print()
            print("✅ ALL SECTIONS ARE CANONICAL")
    
    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    
    print(f"Total agents analyzed: {len(agents)}")
    print(f"Total unique section IDs found: {len(all_section_ids)}")
    print(f"Total unique headings found: {len(all_headings)}")
    print()
    
    print("All section IDs found:")
    for sid in sorted(all_section_ids):
        status = "✓ canonical" if sid in CANONICAL_SECTIONS else "✗ NON-CANONICAL"
        print(f"  • {sid:<50} {status}")
    
    print()
    print("All headings found:")
    for h in sorted(all_headings):
        print(f"  • {h}")
    
    if non_canonical_by_agent:
        print()
        print(f"⚠️  {len(non_canonical_by_agent)} AGENTS HAVE NON-CANONICAL SECTIONS:")
        for agent_name, sections in non_canonical_by_agent.items():
            print(f"\n  {agent_name}:")
            for section in sections:
                print(f"    - {section['id']} ({section['heading']})")
    else:
        print()
        print("✅ ALL AGENTS HAVE CANONICAL STRUCTURE")
    
    print()

if __name__ == "__main__":
    analyze_agents()
