"""
Script to standardize Generator agent prompt_sections to canonical structure.
Canonical sections: role, objective, context, runtime_integrations, guidelines, instructions, examples (optional), json_output_compliance, output_format
"""

import json
from pathlib import Path
from typing import List, Dict, Any

AGENTS_JSON_PATH = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"


def load_agents() -> Dict:
    """Load agents.json file."""
    with open(AGENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_agents(data: Dict) -> None:
    """Save agents.json file with validation."""
    with open(AGENTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Validate JSON
    with open(AGENTS_JSON_PATH, 'r', encoding='utf-8') as f:
        json.load(f)
    print(f"✓ Saved and validated {AGENTS_JSON_PATH}")


def fix_workflow_implementation_headings(sections: List[Dict]) -> bool:
    """Merge WorkflowImplementationAgent non-standard headings into canonical sections."""
    modified = False
    
    # Find non-standard sections
    critical_contract_idx = next((i for i, s in enumerate(sections) if s.get("id") == "critical_contract"), None)
    agent_design_idx = next((i for i, s in enumerate(sections) if s.get("id") == "agent_design_patterns"), None)
    example_transform_idx = next((i for i, s in enumerate(sections) if s.get("id") == "example_transformation"), None)
    validation_idx = next((i for i, s in enumerate(sections) if s.get("id") == "validation_checklist"), None)
    final_directive_idx = next((i for i, s in enumerate(sections) if s.get("id") == "final_directive"), None)
    
    # Find canonical sections
    guidelines_idx = next((i for i, s in enumerate(sections) if s.get("id") == "guidelines"), None)
    examples_idx = next((i for i, s in enumerate(sections) if s.get("id") == "examples"), None)
    instructions_idx = next((i for i, s in enumerate(sections) if s.get("id") == "instructions"), None)
    
    # 1. Move CRITICAL CONTRACT to [GUIDELINES]
    if critical_contract_idx is not None and guidelines_idx is not None:
        current_guidelines = sections[guidelines_idx]["content"]
        critical_content = sections[critical_contract_idx]["content"]
        sections[guidelines_idx]["content"] = f"""{current_guidelines}

**Critical Contract**:
{critical_content}"""
        modified = True
    
    # 2. Create/update [EXAMPLES] with AGENT DESIGN PATTERNS + EXAMPLE TRANSFORMATION
    if agent_design_idx is not None and example_transform_idx is not None:
        agent_design_content = sections[agent_design_idx]["content"]
        example_transform_content = sections[example_transform_idx]["content"]
        
        combined_examples = f"""{agent_design_content}

{example_transform_content}"""
        
        if examples_idx is not None:
            sections[examples_idx]["content"] = combined_examples
        else:
            # Insert examples section before guidelines
            sections.insert(guidelines_idx, {
                "id": "examples",
                "heading": "[EXAMPLES]",
                "content": combined_examples
            })
        modified = True
    
    # 3. Append VALIDATION CHECKLIST + FINAL DIRECTIVE to end of [INSTRUCTIONS]
    if validation_idx is not None and final_directive_idx is not None and instructions_idx is not None:
        current_instructions = sections[instructions_idx]["content"]
        validation_content = sections[validation_idx]["content"]
        final_directive_content = sections[final_directive_idx]["content"]
        
        sections[instructions_idx]["content"] = f"""{current_instructions}

**{validation_content}

**{final_directive_content}"""
        modified = True
    
    # 4. Remove non-standard sections
    indices_to_remove = [critical_contract_idx, agent_design_idx, example_transform_idx, 
                         validation_idx, final_directive_idx]
    for idx in sorted([i for i in indices_to_remove if i is not None], reverse=True):
        sections.pop(idx)
        modified = True
    
    return modified


def fix_all_example_headings(agent_name: str, sections: List[Dict]) -> bool:
    """Fix any agent with [EXAMPLE - ...] headings to use canonical [EXAMPLES]."""
    modified = False
    
    # Find all sections with EXAMPLE in heading
    example_sections = [(i, s) for i, s in enumerate(sections) 
                       if "[EXAMPLE" in s.get("heading", "")]
    
    if not example_sections:
        return False
    
    # Find or create canonical examples section
    examples_idx = next((i for i, s in enumerate(sections) if s.get("id") == "examples"), None)
    guidelines_idx = next((i for i, s in enumerate(sections) if s.get("id") == "guidelines"), None)
    
    # Combine all example content
    combined_content = "\n\n".join([s["content"] for _, s in example_sections])
    
    if examples_idx is not None:
        # Update existing
        sections[examples_idx]["content"] = combined_content
    else:
        # Create new examples section before guidelines
        insert_pos = guidelines_idx if guidelines_idx is not None else len(sections) - 2
        sections.insert(insert_pos, {
            "id": "examples",
            "heading": "[EXAMPLES]",
            "content": combined_content
        })
    
    # Remove all non-standard example sections (in reverse order)
    for idx, _ in sorted(example_sections, reverse=True):
        sections.pop(idx)
    
    modified = True
    return modified


def main():
    """Standardize all generator agent prompts."""
    print("Loading agents.json...")
    data = load_agents()
    agents = data["agents"]
    
    # Track changes
    changed_agents = []
    
    # 1. Fix WorkflowImplementationAgent non-standard headings
    if "WorkflowImplementationAgent" in agents:
        print("\nProcessing WorkflowImplementationAgent...")
        sections = agents["WorkflowImplementationAgent"]["prompt_sections"]
        if fix_workflow_implementation_headings(sections):
            changed_agents.append("WorkflowImplementationAgent")
            print("  ✓ Merged non-standard headings into canonical sections")
    
    # 2. Fix all agents with [EXAMPLE - ...] headings
    agents_with_examples = [
        "ContextVariablesAgent", "ToolsManagerAgent", "StructuredOutputsAgent",
        "AgentsAgent", "HookAgent", "HandoffsAgent", "OrchestratorAgent"
    ]
    
    for agent_name in agents_with_examples:
        if agent_name in agents:
            print(f"\nProcessing {agent_name}...")
            sections = agents[agent_name]["prompt_sections"]
            if fix_all_example_headings(agent_name, sections):
                if agent_name not in changed_agents:
                    changed_agents.append(agent_name)
                print(f"  ✓ Fixed [EXAMPLE] headings to [EXAMPLES]")
    
    # Save changes
    if changed_agents:
        print(f"\n✓ Updated {len(changed_agents)} agents: {', '.join(changed_agents)}")
        save_agents(data)
        print("\n✓ All agents standardized successfully!")
    else:
        print("\n✓ No changes needed - all agents already standardized")


if __name__ == "__main__":
    main()
