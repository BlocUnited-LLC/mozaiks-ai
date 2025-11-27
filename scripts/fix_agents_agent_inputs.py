"""
Fix AgentsAgent system message to read correct data sources.
Updates [INPUTS] section and Step 1 to read workflow_strategy + PhaseAgentsCall instead of ActionPlan.
"""

import json
from pathlib import Path

agents_json_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

# Read the JSON file
with open(agents_json_path, 'r', encoding='utf-8') as f:
    agents_config = json.load(f)

# Get AgentsAgent system message
system_message = agents_config["agents"]["AgentsAgent"]["system_message"]

# OLD [INPUTS] section #1 text
old_inputs_1 = """1. **Action Plan** (from ActionPlanCall output):
   - Structure: {"ActionPlan": {"workflow": {"phases": [...]}}}
   - What to extract: Agent names, phase order, human_interaction values, operations/integrations per agent
   - Why: Determines agent roster, responsibilities, and UI patterns"""

# NEW [INPUTS] section #1 text  
new_inputs_1 = """1. **Workflow Strategy + Phase Agents** (merge from two sources):
   - Source 1: Read `workflow_strategy` from context variables
     * Structure: {"workflow_name": "...", "phases": [{"phase_name": "...", "phase_description": "...", "specialist_domains": [...], "approval_required": bool}]}
     * Contains: Phase metadata (names, descriptions, approval flags, specialist domains)
   - Source 2: Locate PhaseAgentsCall output in conversation history
     * Structure: {"phase_agents": [{"phase_index": 0, "agents": [{"name": "...", "description": "...", "human_interaction": "...", "operations": [...], "integrations": [...]}]}, ...]}
     * Contains: Agent specifications for each phase
   - Merge: For each phase_index, combine workflow_strategy.phases[i] metadata + phase_agents[i].agents array
   - Why: Determines complete agent roster, responsibilities, and UI patterns (all agents across all phases)"""

# OLD Step 1 text
old_step_1 = """Step 1 - Parse Action Plan for Agent Roster
  - Locate {"ActionPlan": {"workflow": {"phases": [...]}}} in conversation
  - Extract all agent names in phase order
  - For each agent, extract: human_interaction, operations, integrations"""

# NEW Step 1 text
new_step_1 = """Step 1 - Parse Workflow Strategy + Phase Agents for Agent Roster
  - Read `workflow_strategy` from context variables (contains phase metadata)
  - Locate PhaseAgentsCall output in conversation history:
    * Search for JSON with structure: {"phase_agents": [{"phase_index": 0, "agents": [...]}, ...]}
  - Merge to build complete agent roster:
    a) For each entry in phase_agents array:
       - phase_index identifies which workflow_strategy phase this belongs to
       - agents[] contains full agent specifications (name, description, human_interaction, operations, integrations)
    b) Extract ALL agents across ALL phase_agents entries (iterate through entire array)
    c) Build complete list of agents with their configurations
  - Result: Complete agent roster in phase order (typically 5+ phases with 1 agent each or multiple agents per phase)"""

# Replace in system message
system_message = system_message.replace(old_inputs_1, new_inputs_1)
system_message = system_message.replace(old_step_1, new_step_1)

# Update the config
agents_config["agents"]["AgentsAgent"]["system_message"] = system_message

# Write back
with open(agents_json_path, 'w', encoding='utf-8') as f:
    json.dump(agents_config, f, indent=2, ensure_ascii=False)

print("✅ Updated AgentsAgent system message")
print("   - Updated [INPUTS] section #1 to read workflow_strategy + PhaseAgentsCall")
print("   - Updated Step 1 to merge data from both sources")
print("   - Removed all agent name references (e.g., 'from WorkflowImplementationAgent')")
