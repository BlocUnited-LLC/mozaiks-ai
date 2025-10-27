"""
Remove agent_modes from Generator workflow architecture.

This script updates:
1. ToolsManagerAgent system message - removes agent_modes emission logic
2. AgentsAgent system message - changes from READ to DETERMINE auto_tool_mode
3. StructuredOutputsAgent system message - removes agent_modes references
"""

import json
import re
from pathlib import Path

def update_tools_manager_agent(agents_data):
    """Remove agent_modes logic from ToolsManagerAgent system message."""
    system_message = agents_data['agents']['ToolsManagerAgent']['system_message']
    
    # Remove AUTO_TOOL_MODE DETERMINATION section entirely
    system_message = re.sub(
        r'\[AUTO_TOOL_MODE DETERMINATION\].*?\n\n\n\[RUNTIME SYSTEM CAPABILITIES',
        '[RUNTIME SYSTEM CAPABILITIES',
        system_message,
        flags=re.DOTALL
    )
    
    # Update OBJECTIVE to remove auto_tool_mode determination mention
    system_message = system_message.replace(
        '- Convert the approved Action Plan into an exact ToolSpec manifest for downstream code generation and runtime loading.\n- **CRITICAL**: Determine auto_tool_mode for each agent based on their tool ownership (automated, not manual configuration).',
        '- Convert the approved Action Plan into an exact ToolSpec manifest for downstream code generation and runtime loading.'
    )
    
    # Update CONTEXT VARIABLE COORDINATION section
    system_message = system_message.replace(
        '2. YOUR OUTPUT CONTRACT:\n   - Generate tools.json manifest mapping operations → Agent_Tool entries\n   - Map UI responsibilities → UI_Tool entries with component/mode specifications\n   - **Determine auto_tool_mode for each agent** (based on tool ownership)\n   - Your manifest is consumed by downstream code generation agents',
        '2. YOUR OUTPUT CONTRACT:\n   - Generate tools.json manifest mapping operations → Agent_Tool entries\n   - Map UI responsibilities → UI_Tool entries with component/mode specifications\n   - Your manifest is consumed by downstream code generation agents'
    )
    
    # Update GUIDELINES section 1
    system_message = system_message.replace(
        '1. Emit exactly one JSON object with the top-level keys: tools (array of ToolSpec) and lifecycle_tools (array of LifecycleToolSpec, optional).',
        '1. Emit exactly one JSON object with the top-level keys: tools (array of ToolSpec) and lifecycle_tools (array of LifecycleToolSpec, optional, can be empty array or omitted).'
    )
    
    # Remove agent_modes from OUTPUT FORMAT example
    old_example = '''  ],
  "agent_modes": [
    { "agent": "InterviewAgent", "auto_tool_mode": false },
    { "agent": "ContextExtractionAgent", "auto_tool_mode": true },
    { "agent": "PromptAgent", "auto_tool_mode": true },
    { "agent": "VideoAgent", "auto_tool_mode": true },
    { "agent": "ThumbnailAgent", "auto_tool_mode": true },
    { "agent": "StoryboardAgent", "auto_tool_mode": true },
    { "agent": "ShareApprovalAgent", "auto_tool_mode": true },
    { "agent": "BlotatoAgent", "auto_tool_mode": false }
  ]
}'''
    
    new_example = '''  ]
}'''
    
    system_message = system_message.replace(old_example, new_example)
    
    agents_data['agents']['ToolsManagerAgent']['system_message'] = system_message
    print("✅ Updated ToolsManagerAgent system message")


def update_agents_agent(agents_data):
    """Change AgentsAgent from READ agent_modes to DETERMINE auto_tool_mode."""
    system_message = agents_data['agents']['AgentsAgent']['system_message']
    
    # Replace entire AUTO_TOOL_MODE READING section with AUTO_TOOL_MODE DETERMINATION
    old_section = re.search(
        r'\[AUTO_TOOL_MODE READING\].*?\n\n\[CONTEXT\]',
        system_message,
        re.DOTALL
    )
    
    if old_section:
        new_section = '''[AUTO_TOOL_MODE DETERMINATION] (CRITICAL - ANALYZE TOOLS ARRAY)
You MUST determine auto_tool_mode for each agent by analyzing the tools manifest:

**DETERMINATION RULE:**
- Locate tools.json manifest in conversation (output from ToolsManagerAgent)
- For EACH agent you configure:
  1. Scan tools array for entries where agent field == current agent name
  2. Check if ANY tool has tool_type="UI_Tool"
  3. IF agent owns ≥1 UI_Tool → set auto_tool_mode=true (REQUIRED for async UI tools)
  4. IF agent owns ONLY Agent_Tool entries → set auto_tool_mode=false (default)
  5. IF agent owns NO tools → set auto_tool_mode=false (no tools to invoke)

**WHY UI TOOLS REQUIRE auto_tool_mode=true:**
- UI_Tool functions are ALWAYS async (they use `await use_ui_tool(...)`)
- AG2's native calling (auto_tool_mode=false) does NOT await async functions
- AutoToolEventHandler (auto_tool_mode=true) properly awaits async UI tools
- This is a technical requirement based on AG2's architecture

**EXAMPLE ANALYSIS:**
```
tools.json contains:
{
  "tools": [
    {"agent": "ActionPlanArchitect", "tool_type": "UI_Tool", ...},
    {"agent": "ProjectOverviewAgent", "tool_type": "UI_Tool", ...},
    {"agent": "ToolsManagerAgent", "tool_type": "Agent_Tool", ...}
  ]
}

Your determination:
- ActionPlanArchitect: Has UI_Tool → auto_tool_mode=true
- ProjectOverviewAgent: Has UI_Tool → auto_tool_mode=true  
- ToolsManagerAgent: Only Agent_Tool → auto_tool_mode=false
```

[CONTEXT]'''
        
        system_message = system_message.replace(old_section.group(0), new_section)
    
    # Update CONTEXT section to remove agent_modes reference
    system_message = system_message.replace(
        '- Inputs: Action Plan, ContextVariablesPlan, Tool Registry (tools manifest with agent_modes), structured outputs registry, handoff logic requirements.',
        '- Inputs: Action Plan, ContextVariablesPlan, Tool Registry (tools manifest), structured outputs registry, handoff logic requirements.'
    )
    
    # Update guideline 9
    system_message = system_message.replace(
        '9. Read auto_tool_mode from tools.json agent_modes object (set by ToolsManagerAgent); never re-calculate it yourself.',
        '9. Determine auto_tool_mode by analyzing tools.json manifest (scan tools array for UI_Tool ownership).'
    )
    
    # Update Step 2 instructions
    old_step2 = '''Step 2 - Gather Candidate Agents and Read agent_modes
  - Extract agent names from Action Plan phases.agents lists
  - For EACH agent, extract the human_interaction field value ("none", "context", or "approval")
  - Locate tools.json manifest in conversation (from ToolsManagerAgent)
  - Extract agent_modes object mapping agent names to auto_tool_mode boolean values
  - For each agent, look up their auto_tool_mode from agent_modes (default to false if not found)
  - Include Generator workflow meta-agents (ToolsManagerAgent, UIFileGenerator, etc.)'''
    
    new_step2 = '''Step 2 - Gather Candidate Agents and Determine auto_tool_mode
  - Extract agent names from Action Plan phases.agents lists
  - For EACH agent, extract the human_interaction field value ("none", "context", or "approval")
  - Locate tools.json manifest in conversation (from ToolsManagerAgent)
  - For each agent, determine auto_tool_mode:
    a) Scan tools array for entries where agent field == current agent name
    b) Check if ANY tool has tool_type="UI_Tool"
    c) IF yes → auto_tool_mode=true; IF no → auto_tool_mode=false
  - Include Generator workflow meta-agents (ToolsManagerAgent, UIFileGenerator, etc.)'''
    
    system_message = system_message.replace(old_step2, new_step2)
    
    # Update Step 4 auto_tool_mode assignment
    system_message = system_message.replace(
        '  - auto_tool_mode: Read from agent_modes object in tools.json (determined by ToolsManagerAgent based on tool ownership)',
        '  - auto_tool_mode: Determined by analyzing tools array (agent owns ≥1 UI_Tool → true, otherwise → false)'
    )
    
    agents_data['agents']['AgentsAgent']['system_message'] = system_message
    print("✅ Updated AgentsAgent system message")


def update_structured_outputs_agent(agents_data):
    """Remove agent_modes references from StructuredOutputsAgent."""
    system_message = agents_data['agents']['StructuredOutputsAgent']['system_message']
    
    # Update tools.json structure example in UPSTREAM ARTIFACT ANALYSIS section
    old_structure = '''**1. FROM tools.json manifest** (ToolsManagerAgent output):
- Structure: {"tools": [...], "agent_modes": {"AgentName": true/false}}
- What to read:
  * agent_modes object: Maps agent names to auto_tool_mode boolean
  * tools array: Each entry has agent, tool_type ("UI_Tool" | "Agent_Tool"), file, function, ui config'''
    
    new_structure = '''**1. FROM tools.json manifest** (ToolsManagerAgent output):
- Structure: {"tools": [...], "lifecycle_tools": [...]}
- What to read:
  * tools array: Each entry has agent, tool_type ("UI_Tool" | "Agent_Tool"), file, function, ui config
  * For each agent, determine tool ownership by scanning tools array'''
    
    system_message = system_message.replace(old_structure, new_structure)
    
    # Update HOW TO DETERMINE section Step 1
    old_step1 = '''**Step 1: Lookup auto_tool_mode**
- Locate tools.json manifest in conversation
- Read agent_modes object: {"AgentName": true/false}
- Extract auto_tool_mode value for current agent
- IF agent not in agent_modes → default to false'''
    
    new_step1 = '''**Step 1: Determine auto_tool_mode**
- Locate tools.json manifest in conversation
- Scan tools array for entries where agent field == current agent name
- Check if ANY tool has tool_type="UI_Tool"
- IF yes → auto_tool_mode=true; IF no → auto_tool_mode=false'''
    
    system_message = system_message.replace(old_step1, new_step1)
    
    agents_data['agents']['StructuredOutputsAgent']['system_message'] = system_message
    print("✅ Updated StructuredOutputsAgent system message")


def main():
    """Execute all updates."""
    print("🔧 Removing agent_modes from Generator workflow...")
    
    # Load agents.json
    agents_path = Path(__file__).parent.parent / "workflows/Generator/agents.json"
    with open(agents_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    # Apply updates
    update_tools_manager_agent(agents_data)
    update_agents_agent(agents_data)
    update_structured_outputs_agent(agents_data)
    
    # Save updated agents.json
    with open(agents_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print("\n✅ All system message updates complete!")
    print("\n📝 Next steps:")
    print("  1. Update workflow_converter.py to remove agent_modes logic")
    print("  2. Test Generator workflow")


if __name__ == "__main__":
    main()
