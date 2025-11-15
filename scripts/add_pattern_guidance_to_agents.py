"""
Script to update WorkflowStrategyAgent, WorkflowImplementationAgent, and ProjectOverviewAgent
system messages to reference pattern-specific guidance from context.
"""
import json
from pathlib import Path

# Pattern guidance instruction block for each agent
WORKFLOW_STRATEGY_PATTERN_GUIDANCE = """
[AG2 PATTERN GUIDANCE] (CRITICAL - USE SELECTED PATTERN)
You have access to pattern-specific guidance in context_variables under the key 'pattern_guidance'.
This guidance is selected by the PatternAgent based on workflow requirements analysis.

**How to Use Pattern Guidance:**
1. Check context_variables for 'pattern_guidance.workflow_strategy'
2. This contains:
   - Recommended phase structure for the selected AG2 pattern
   - Coordination patterns between phases
   - Pattern characteristics and when to use
3. ALIGN your phase design with the pattern guidance
4. Use the recommended phase names and purposes as templates
5. Adapt the guidance to the specific workflow requirements

**Pattern-Driven Phase Design:**
- **Phase Structure**: Follow the recommended phase structure from the pattern
- **Coordination**: Implement the coordination pattern specified
- **Agent Coordination**: Use the agents_needed patterns suggested
- **Approval Points**: Place approval phases according to pattern guidance

**Example:**
If pattern_guidance indicates Pipeline pattern (sequential processing):
- Create distinct sequential phases
- Each phase depends on previous output
- No parallel coordination needed
- Clear stage boundaries

If pattern_guidance indicates Hierarchical pattern:
- Create executive planning phase
- Add management coordination phases
- Include specialist execution phases
- Design aggregation phase

**Important:**
- Pattern guidance is injected AFTER PatternAgent runs
- Always check for pattern_guidance before designing phases
- Default to Organic (flexible) pattern if guidance is unavailable
- Ensure your phase structure reflects the selected pattern's characteristics
"""

WORKFLOW_IMPLEMENTATION_PATTERN_GUIDANCE = """
[AG2 PATTERN GUIDANCE] (CRITICAL - USE SELECTED PATTERN)
You have access to pattern-specific guidance in context_variables under the key 'pattern_guidance'.
This guidance is selected by the PatternAgent based on workflow requirements analysis.

**How to Use Pattern Guidance:**
1. Check context_variables for 'pattern_guidance.workflow_implementation'
2. This contains:
   - Agent coordination patterns for the selected AG2 pattern
   - Communication flow between agents
   - Required agent roles
   - AG2 features needed for this pattern
3. DESIGN agents that match the pattern's coordination structure
4. Use the required roles as templates for agent types
5. Implement communication flow as specified

**Pattern-Driven Agent Design:**
- **Agent Roles**: Create agents matching the required roles from pattern
- **Coordination**: Implement the coordination pattern specified (e.g., hub-and-spoke, sequential, hierarchical)
- **Communication Flow**: Structure agent interactions per the pattern's flow
- **Specialist Domains**: Use the specialist_domains from WorkflowStrategy to create targeted agents

**Example:**
If pattern_guidance indicates Star pattern (hub-and-spoke):
- Create one central coordinator agent
- Create multiple specialist spoke agents
- Spoke agents don't communicate with each other
- All communication flows through hub

If pattern_guidance indicates Pipeline pattern:
- Create sequential stage agents (Stage_1, Stage_2, etc.)
- Each agent processes output from previous stage
- No parallel agents within same phase
- Clear input/output contracts

If pattern_guidance indicates Hierarchical pattern:
- Create executive agent (high-level planning)
- Create manager agents (coordination)
- Create specialist agents (execution)
- Design proper delegation and aggregation

**Important:**
- Pattern guidance is injected AFTER PatternAgent runs
- Always check for pattern_guidance before designing agents
- Align agent structures with the selected pattern
- Use appropriate human_interaction modes per pattern needs
- Ensure operations and integrations match agent roles from pattern
"""

PROJECT_OVERVIEW_PATTERN_GUIDANCE = """
[AG2 PATTERN GUIDANCE] (CRITICAL - USE SELECTED PATTERN)
You have access to pattern-specific guidance in context_variables under the key 'pattern_guidance'.
This guidance is selected by the PatternAgent based on workflow requirements analysis.

**How to Use Pattern Guidance:**
1. Check context_variables for 'pattern_guidance.project_overview'
2. This contains:
   - Mermaid diagram structure for the selected AG2 pattern
   - Key visual elements to include
   - Example structure/template
   - Pattern coordination visualization tips
3. STRUCTURE your Mermaid diagram to reflect the pattern
4. Use the recommended diagram type (flowchart TD, graph TD, etc.)
5. Include the key visual elements specified

**Pattern-Driven Diagram Design:**
- **Diagram Type**: Use the recommended Mermaid diagram type from pattern
- **Key Elements**: Include visual elements specified (e.g., decision nodes, parallel branches, hierarchical levels)
- **Flow Direction**: Match the pattern's coordination flow
- **Example Structure**: Use the example as a template and adapt to workflow

**Example:**
If pattern_guidance indicates Pipeline pattern:
- Use flowchart LR (left-to-right horizontal flow)
- Show unidirectional arrows between stages
- Clear stage separation
- Progressive refinement visualization

If pattern_guidance indicates Star pattern:
- Use graph TD to show hub-and-spoke structure
- Central hub node with radial connections
- Bidirectional arrows between hub and spokes
- No spoke-to-spoke connections

If pattern_guidance indicates Feedback Loop pattern:
- Use flowchart TD with loop-back arrows
- Show quality gate decision points
- Loop arrows from review back to creation
- Exit condition clearly marked

**Important:**
- Pattern guidance is injected AFTER PatternAgent runs
- Always check for pattern_guidance before creating diagram
- Align diagram structure with the selected pattern
- Use visual conventions that match the pattern type
- Ensure diagram reflects agent coordination from WorkflowImplementation
"""


def main():
    """Update downstream agents with pattern guidance instructions."""
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    agents_json_path = project_root / "workflows" / "Generator" / "agents.json"

    if not agents_json_path.exists():
        print(f"Error: agents.json not found at {agents_json_path}")
        return

    print(f"Reading agents.json from: {agents_json_path}")

    # Load agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)

    # Agents to update
    agents_to_update = {
        "WorkflowStrategyAgent": WORKFLOW_STRATEGY_PATTERN_GUIDANCE,
        "WorkflowImplementationAgent": WORKFLOW_IMPLEMENTATION_PATTERN_GUIDANCE,
        "ProjectOverviewAgent": PROJECT_OVERVIEW_PATTERN_GUIDANCE
    }

    # Update each agent
    for agent_name, guidance_block in agents_to_update.items():
        if agent_name not in agents_data['agents']:
            print(f"Warning: {agent_name} not found in agents.json")
            continue

        agent = agents_data['agents'][agent_name]
        current_message = agent['system_message']

        print(f"\nUpdating {agent_name}...")
        print(f"  Current message length: {len(current_message)} chars")

        # Check if pattern guidance already exists
        if "[AG2 PATTERN GUIDANCE]" in current_message:
            print(f"  Pattern guidance already exists, skipping")
            continue

        # Add pattern guidance block at the end
        new_message = current_message + "\n\n" + guidance_block
        agent['system_message'] = new_message

        print(f"  New message length: {len(new_message)} chars")
        print(f"  [OK] Pattern guidance added")

    # Create backup
    backup_path = agents_json_path.with_suffix('.json.backup3')
    print(f"\nCreating backup at: {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    # Write updated agents.json
    print(f"Writing updated agents.json...")
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    print("\n[OK] All downstream agents updated with pattern guidance!")
    print(f"\nUpdated agents:")
    for agent_name in agents_to_update.keys():
        if agent_name in agents_data['agents']:
            print(f"  - {agent_name}: {len(agents_data['agents'][agent_name]['system_message'])} chars")


if __name__ == "__main__":
    main()
