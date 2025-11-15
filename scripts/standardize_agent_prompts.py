"""
Standardize all Generator agent prompt_sections to canonical structure.

Canonical structure:
- role, objective, context, runtime_integrations, guidelines, instructions, 
  examples (optional), json_output_compliance, output_format

This script:
1. Fixes [INPUTS] → [CONTEXT] heading inconsistencies
2. Completes [TODO] placeholders with proper content
3. Validates JSON after each change
"""

import json
import pathlib
from typing import Dict, Any, List

AGENTS_JSON = pathlib.Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"


def load_agents() -> Dict[str, Any]:
    """Load agents.json with UTF-8 encoding."""
    return json.loads(AGENTS_JSON.read_text(encoding="utf-8"))


def save_agents(data: Dict[str, Any]) -> None:
    """Save agents.json with UTF-8 encoding and validation."""
    # Validate before saving
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    json.loads(json_str)  # Parse to ensure validity
    AGENTS_JSON.write_text(json_str, encoding="utf-8")
    print(f"✓ Saved and validated {AGENTS_JSON}")


def find_section(sections: List[Dict], section_id: str) -> Dict | None:
    """Find section by id."""
    return next((s for s in sections if s["id"] == section_id), None)


def update_section(sections: List[Dict], section_id: str, heading: str, content: str) -> None:
    """Update or create a section."""
    section = find_section(sections, section_id)
    if section:
        section["heading"] = heading
        section["content"] = content
    else:
        sections.append({"id": section_id, "heading": heading, "content": content})


def fix_inputs_to_context(agent_name: str, sections: List[Dict]) -> bool:
    """Fix [INPUTS] → [CONTEXT] heading."""
    section = find_section(sections, "inputs")
    if section:
        section["id"] = "context"
        section["heading"] = "[CONTEXT]"
        print(f"  ✓ Fixed [INPUTS] → [CONTEXT] for {agent_name}")
        return True
    return False


def complete_project_overview_agent(sections: List[Dict]) -> None:
    """Complete ProjectOverviewAgent instructions and output_format."""
    instructions_content = """**Step 1 - Read Action Plan**:
- Locate action_plan from context variables
- Extract: workflow.pattern, workflow.phases[], workflow.description
- Note: phase_name, agents[], approval_required for each phase

**Step 2 - Locate Pattern Guidance**:
- Scroll to bottom of system message to find [INJECTED PATTERN GUIDANCE - {PatternName}] section
- Read: Mermaid topology description, participant structure, flow logic, example code
- Understand pattern's canonical diagram structure

**Step 3 - Map Phases to Mermaid Topology**:
- Follow pattern's canonical flow logic from injected guidance
- Replace pattern example agents with actual ActionPlan agent names
- Add phase-specific interactions based on workflow.phases[]
- Insert approval gates where phase.approval_required=true

**Step 4 - Generate Mermaid Participants**:
- Create participant declarations for User and all unique agent names from phases
- Use clear display names: `participant AgentName as Display Label`
- For approval agents, use labels like "Marketing Approval" or "Compliance Reviewer"

**Step 5 - Build Interaction Sequence**:
- Follow pattern's canonical flow (Pipeline: sequential, Hierarchical: 3-level, Star: hub-and-spoke, etc.)
- Add phase annotations using Notes: `Note over Agent: Phase 1: Planning`
- Add approval gates using alt blocks when approval_required=true
- Ensure final phase → User handoff

**Step 6 - Validate Diagram**:
- Ensure all agents from action_plan.workflow.phases[].agents[] appear as participants
- Ensure approval gates match phase.approval_required flags
- Ensure pattern topology matches injected guidance structure

**Step 7 - Output JSON**:
- Emit ProjectOverviewCall as valid JSON with mermaid_code field
- NO markdown fences, NO explanatory text, ONLY the JSON object"""

    output_format_content = """Output MUST be a valid JSON object matching the ProjectOverviewCall schema with NO additional text:

```json
{
  "mermaid_code": "<Mermaid sequence diagram code as string>",
  "agent_message": "<Summary of diagram generation>"
}
```

**Required Fields**:
- mermaid_code: Valid Mermaid sequence diagram string (starts with "sequenceDiagram")
- agent_message: Brief summary (e.g., "Generated 5-phase Pipeline workflow diagram")

**Mermaid Syntax Reminder**:
- Start with: sequenceDiagram
- Participants: `participant User`, `participant AgentName as Display Name`
- Interactions: `Agent1->>Agent2: Message`
- Notes: `Note over Agent: Phase 1: Planning`
- Conditionals: `alt Approved / else Rejected / end`
- Loops: `loop Description / end`

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""

    update_section(sections, "instructions", "[INSTRUCTIONS]", instructions_content)
    update_section(sections, "output_format", "[OUTPUT FORMAT]", output_format_content)
    print("  ✓ Completed ProjectOverviewAgent instructions and output_format")


def complete_context_variables_agent(sections: List[Dict]) -> None:
    """Complete ContextVariablesAgent instructions."""
    # This agent already has good content, just needs [INPUTS] → [CONTEXT] which is handled separately
    pass


def complete_runtime_agents_agent(sections: List[Dict]) -> None:
    """Complete RuntimeAgentsAgent instructions."""
    instructions_content = """**Step 1 - Gather Upstream Artifacts**:
- Locate workflow_strategy from context variables (phases[], pattern, lifecycle_operations[])
- Locate PhaseAgentsCall output in conversation history (phase_agents[] with agent specifications)
- Locate structured outputs registry (which agents require structured_outputs_required=true)
- Locate tools manifest (which agents own UI_Tool vs Agent_Tool)
- Locate context variables plan (exposed variables per agent, coordination tokens)

**Step 2 - Merge Phase Data**:
- For each phase_index, combine:
  * workflow_strategy.phases[i] metadata (phase_name, approval_required, specialist_domains)
  * phase_agents[i].agents[] specifications (name, description, operations, integrations, human_interaction)
- Result: Complete agent roster with roles and capabilities

**Step 3 - Determine auto_tool_mode for Each Agent**:
- Scan tools manifest for entries where agent field == current agent name
- IF agent owns >=1 tool with tool_type="UI_Tool" → set auto_tool_mode=true (REQUIRED for async UI tools)
- ELSE → set auto_tool_mode=false

**Step 4 - Determine structured_outputs_required for Each Agent**:
- Find registry entry where agent field == current agent name
- IF agent_definition != null → set structured_outputs_required=true
- ELSE → set structured_outputs_required=false

**Step 5 - Generate System Messages for Each Agent**:
- Include sections: [ROLE], [OBJECTIVE], [CONTEXT], [RUNTIME INTEGRATION], [GUIDELINES], [INSTRUCTIONS]
- Add [CONTEXT VARIABLES] if agent has exposed variables from ContextVariablesPlan
- Add [COORDINATION TOKEN] if agent must emit coordination tokens (from ContextVariablesPlan triggers)
- Add [TOOL INTEGRATION] if agent owns tools (reference React components for UI_Tools, Python paths for Agent_Tools)
- Add [JSON OUTPUT COMPLIANCE] for all structured output agents
- Add [OUTPUT FORMAT] defining expected output structure

**Step 6 - Build RuntimeAgentsCall**:
- Construct agents[] array with: name, display_name, system_message, max_consecutive_auto_reply, auto_tool_mode, structured_outputs_required
- Add agent_message summarizing compilation (e.g., "Compiled 8 runtime agents with system messages")

**Step 7 - Validate Agent Roster**:
- Ensure all agents from phase_agents[] appear in output
- Ensure auto_tool_mode=true for all UI_Tool owners
- Ensure structured_outputs_required matches registry
- Ensure coordination tokens are documented in system messages

**Step 8 - Output JSON**:
- Emit RuntimeAgentsCall as valid JSON matching schema
- NO markdown fences, NO explanatory text, ONLY the JSON object"""

    output_format_content = """Output MUST be a valid JSON object matching the RuntimeAgentsCall schema with NO additional text:

```json
{
  "agents": [
    {
      "name": "<PascalCaseAgentName>",
      "display_name": "<Display Name>",
      "system_message": "<Complete system message with all sections>",
      "max_consecutive_auto_reply": <int>,
      "auto_tool_mode": true|false,
      "structured_outputs_required": true|false
    }
  ],
  "agent_message": "<Summary of agent compilation>"
}
```

**Required Fields**:
- agents: Array of agent configuration objects
- name: PascalCase agent name
- display_name: Human-readable name
- system_message: Complete multi-section system message
- max_consecutive_auto_reply: Integer (typically 5-20)
- auto_tool_mode: true if agent owns UI_Tools, false otherwise
- structured_outputs_required: true if agent emits structured JSON
- agent_message: Summary (e.g., "Compiled 8 runtime agents")

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""

    update_section(sections, "instructions", "[INSTRUCTIONS]", instructions_content)
    update_section(sections, "output_format", "[OUTPUT FORMAT]", output_format_content)
    print("  ✓ Completed RuntimeAgentsAgent instructions and output_format")


def complete_hook_agent(sections: List[Dict]) -> None:
    """Complete HookAgent objective, context, instructions, and output_format."""
    objective_content = """- Author custom lifecycle hook implementations when workflow requires custom validation, audit, or synchronization logic
- Generate Python hook functions (before_chat, after_chat, update_agent_state) with proper signatures
- Ensure hooks are production-ready with error handling and logging
- Flag when default runtime hooks are sufficient (most workflows don't need custom hooks)"""

    context_content = """- Input: workflow_strategy lifecycle_operations[] (custom business logic requirements)
- Output: HookImplementationCall with hook_files[] containing Python code
- Downstream: Hook files are written to workflows/{WorkflowName}/hooks/ directory
- Runtime: Hooks are imported and registered automatically on workflow initialization
- Note: Only generate hooks when workflow_strategy explicitly defines custom lifecycle_operations"""

    instructions_content = """**Step 1 - Read Lifecycle Operations**:
- Locate workflow_strategy from context variables
- Extract lifecycle_operations[] array
- IF empty → emit HookImplementationCall with empty hook_files[] and message "No custom hooks required"
- ELSE → proceed to Step 2

**Step 2 - Categorize Hook Requirements**:
- Group lifecycle_operations by trigger type:
  * before_chat: Runs once before workflow starts (validation, initialization)
  * after_chat: Runs once after workflow completes (cleanup, audit logging)
  * before_agent: Runs before specific agent's turn (pre-agent validation)
  * after_agent: Runs after specific agent's turn (post-agent audit)
  * update_agent_state: Runs to inject dynamic content into agent system messages

**Step 3 - Generate Hook Functions**:
- For EACH unique trigger type needed:
  * Generate async Python function with proper signature
  * Include runtime context parameters: chat_id, enterprise_id, user_id, agents dict, context_variables
  * Implement business logic from lifecycle_operation description
  * Add error handling with try/except and logging
  * Add docstring explaining hook purpose and usage

**Step 4 - Apply Hook Signatures**:
- before_chat: `async def before_chat(chat_id: str, enterprise_id: str, user_id: str, **runtime) -> None`
- after_chat: `async def after_chat(chat_id: str, enterprise_id: str, user_id: str, **runtime) -> None`
- update_agent_state: `async def update_agent_state(agent_name: str, system_message: str, **runtime) -> str`

**Step 5 - Build HookImplementationCall**:
- Construct hook_files[] array with: filename, hook_type, py_content
- Add agent_message summarizing hooks (e.g., "Generated 2 custom lifecycle hooks")

**Step 6 - Validate Hook Code**:
- Ensure all hooks have proper async signatures
- Ensure error handling is present
- Ensure hooks reference real context variables and runtime parameters

**Step 7 - Output JSON**:
- Emit HookImplementationCall as valid JSON matching schema
- NO markdown fences, NO explanatory text, ONLY the JSON object"""

    output_format_content = """Output MUST be a valid JSON object matching the HookImplementationCall schema with NO additional text:

```json
{
  "hook_files": [
    {
      "filename": "<hook_name>.py",
      "hook_type": "before_chat|after_chat|update_agent_state",
      "py_content": "<Python hook function code>"
    }
  ],
  "agent_message": "<Summary of hook generation>"
}
```

**Required Fields**:
- hook_files: Array of hook file objects (can be empty [] if no custom hooks needed)
- filename: Hook file name (e.g., "validate_budget.py", "audit_decisions.py")
- hook_type: One of "before_chat", "after_chat", "update_agent_state"
- py_content: Complete Python code for hook function
- agent_message: Summary (e.g., "Generated 2 custom lifecycle hooks" or "No custom hooks required")

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""

    update_section(sections, "objective", "[OBJECTIVE]", objective_content)
    update_section(sections, "context", "[CONTEXT]", context_content)
    update_section(sections, "instructions", "[INSTRUCTIONS]", instructions_content)
    update_section(sections, "output_format", "[OUTPUT FORMAT]", output_format_content)
    print("  ✓ Completed HookAgent objective, context, instructions, and output_format")


def complete_handoffs_agent(sections: List[Dict]) -> None:
    """Complete HandoffsAgent instructions and output_format."""
    instructions_content = """**Step 1 - Read Action Plan and Context Variables**:
- Locate action_plan from context variables (workflow.phases[], flow_type, approval_trigger, transitions)
- Locate ContextVariablesPlan (definitions with triggers, agents with exposed variables)
- Extract phase sequencing and agent roster

**Step 2 - Build Sequential Phase Handoffs**:
- For EACH phase transition (Phase N → Phase N+1):
  * Identify last agent in current phase and first agent in next phase
  * Create handoff_rule with handoff_type="after_work" for unconditional sequential flow
  * Set condition_type=null, condition_scope=null, condition=null

**Step 3 - Add Conditional Handoffs for Derived Variables**:
- Scan ContextVariablesPlan.definitions for derived variables with triggers
- For EACH agent_text trigger (agent emits coordination token):
  * Create handoff with handoff_type="condition", condition_type="expression", condition_scope=null
  * Set condition="${variable_name} == true" or match trigger.match.equals value
- For EACH ui_response trigger (UI tool updates variable):
  * Create handoff with handoff_type="condition", condition_type="expression", condition_scope="pre"
  * Set condition="${variable_name} == <expected_value>"

**Step 4 - Add Approval Gate Handoffs**:
- For phases with approval_required=true:
  * Create user→next_agent handoff with condition_scope="pre" (waits for UI interaction)
  * Create user→TERMINATE handoff for rejection path
  * Use alt/else pattern from approval triggers

**Step 5 - Add Workflow Termination Handoffs**:
- Identify final phase's last agent
- Create handoff to TERMINATE after completion
- Ensure all rejection paths also route to TERMINATE

**Step 6 - Validate Handoff Rules**:
- Ensure all source_agent and target_agent values match canonical agent names from action_plan
- Ensure condition_scope="pre" for all ui_response triggers
- Ensure condition_scope=null for all agent_text triggers
- Ensure no orphaned agents (all agents have at least one incoming handoff except first agent)

**Step 7 - Output JSON**:
- Emit HandoffsCall as valid JSON matching schema
- NO markdown fences, NO explanatory text, ONLY the JSON object"""

    output_format_content = """Output MUST be a valid JSON object matching the HandoffsCall schema with NO additional text:

```json
{
  "handoff_rules": [
    {
      "source_agent": "<AgentName>|user",
      "target_agent": "<AgentName>|TERMINATE",
      "handoff_type": "after_work|condition",
      "condition_type": "expression|string_llm|null",
      "condition_scope": "pre|null",
      "condition": "<expression string>|null",
      "transition_target": "AgentTarget"
    }
  ],
  "agent_message": "<Summary of handoff rules>"
}
```

**Required Fields**:
- handoff_rules: Array of handoff rule objects
- source_agent: Agent name or "user" (PascalCase)
- target_agent: Agent name or "TERMINATE" (PascalCase)
- handoff_type: "after_work" (unconditional) or "condition" (conditional)
- condition_type: "expression" (context var), "string_llm" (LLM eval), or null
- condition_scope: "pre" (ui_response triggers) or null (agent_text triggers / after_work)
- condition: Expression string (e.g., "${approved} == true") or null
- transition_target: Always "AgentTarget"
- agent_message: Summary (e.g., "Generated 12 handoff rules for 5-phase workflow")

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""

    update_section(sections, "instructions", "[INSTRUCTIONS]", instructions_content)
    update_section(sections, "output_format", "[OUTPUT FORMAT]", output_format_content)
    print("  ✓ Completed HandoffsAgent instructions and output_format")


def complete_orchestrator_agent(sections: List[Dict]) -> None:
    """Complete OrchestratorAgent instructions and output_format."""
    instructions_content = """**Step 1 - Read Action Plan and Agent Definitions**:
- Locate action_plan from context variables (workflow.workflow_name, workflow.pattern)
- Locate agent definitions roster (all agents across all phases)
- Locate tools manifest (identify UI_Tool owners for visual_agents)

**Step 2 - Determine Startup Configuration**:
- Set workflow_name from action_plan.workflow.workflow_name
- Set orchestration_pattern from action_plan.workflow.pattern
- Set max_turns based on workflow complexity (20 for most workflows, 30 for complex iterative patterns)
- Set human_in_the_loop=true (default for all workflows with user interaction)

**Step 3 - Determine Startup Mode**:
- IF workflow.trigger == "chat" → startup_mode="AgentDriven", initial_message=<greeting from first agent>
- ELSE → startup_mode="UserDriven", initial_message=null
- Set initial_message_to_user=null (deprecated field)

**Step 4 - Identify Initial Recipient**:
- Set recipient to first agent in action_plan.workflow.phases[0].agents[0].name
- This agent will execute first turn in the workflow

**Step 5 - Build Visual Agents List**:
- Scan tools manifest for agents that own UI_Tool entries
- Add these agent names to visual_agents[] (these agents render UI components)
- Include any agents with human_interaction="context" or "approval"

**Step 6 - Build OrchestratorCall**:
- Construct orchestration config with all fields
- Add agent_message summarizing config (e.g., "Orchestration config for Marketing Content Creator")

**Step 7 - Output JSON**:
- Emit OrchestratorCall as valid JSON matching schema
- NO markdown fences, NO explanatory text, ONLY the JSON object"""

    output_format_content = """Output MUST be a valid JSON object matching the OrchestratorCall schema with NO additional text:

```json
{
  "workflow_name": "<WorkflowName>",
  "max_turns": <int>,
  "human_in_the_loop": true,
  "startup_mode": "AgentDriven|UserDriven",
  "orchestration_pattern": "<PatternName>",
  "initial_message_to_user": null,
  "initial_message": "<greeting string>|null",
  "recipient": "<FirstAgentName>",
  "visual_agents": ["<AgentName1>", "<AgentName2>"],
  "agent_message": "<Summary of orchestration config>"
}
```

**Required Fields**:
- workflow_name: From action_plan (PascalCase)
- max_turns: Integer (typically 20-30)
- human_in_the_loop: Boolean (true for workflows with user interaction)
- startup_mode: "AgentDriven" (agent speaks first) or "UserDriven" (user speaks first)
- orchestration_pattern: From action_plan.workflow.pattern
- initial_message_to_user: Always null (deprecated)
- initial_message: Greeting string for AgentDriven mode, null for UserDriven
- recipient: First agent name from action_plan.workflow.phases[0].agents[0]
- visual_agents: Array of agent names that own UI_Tools or require human interaction
- agent_message: Summary (e.g., "Orchestration config for Content Pipeline workflow")

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""

    update_section(sections, "instructions", "[INSTRUCTIONS]", instructions_content)
    update_section(sections, "output_format", "[OUTPUT FORMAT]", output_format_content)
    print("  ✓ Completed OrchestratorAgent instructions and output_format")


def complete_download_agent(sections: List[Dict]) -> None:
    """Complete DownloadAgent instructions and output_format."""
    instructions_content = """**Step 1 - Verify Workflow Completion**:
- Confirm all upstream agents have completed (action plan, tools, context variables, agents, handoffs, orchestration)
- Verify workflow artifacts are ready for download

**Step 2 - Output DownloadRequest**:
- Emit DownloadRequest JSON with concise agent_message
- Runtime will auto-invoke generate_and_download tool
- Tool gathers all agent outputs from persistence automatically
- Files are created and download UI is rendered

**Step 3 - Keep It Simple**:
- DO NOT list files (tool handles that)
- DO NOT provide summaries (tool provides that)
- ONLY emit trigger with brief context message"""

    output_format_content = """Output MUST be a valid JSON object matching the DownloadRequest schema with NO additional text:

```json
{
  "agent_message": "<Brief context message for UI>"
}
```

**Required Fields**:
- agent_message: Brief message (e.g., "Your workflow is ready for download")

**What Happens Next**:
- Runtime auto-invokes generate_and_download tool
- Tool gathers all upstream agent outputs from persistence
- Files are written to temp directory
- UI renders FileDownloadCenter component with download links

**CRITICAL**: Output ONLY the raw JSON object. NO markdown fences, NO explanatory text, NO commentary."""

    update_section(sections, "instructions", "[INSTRUCTIONS]", instructions_content)
    update_section(sections, "output_format", "[OUTPUT FORMAT]", output_format_content)
    print("  ✓ Completed DownloadAgent instructions and output_format")


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
    
    # 3. Merge VALIDATION CHECKLIST + FINAL DIRECTIVE into [INSTRUCTIONS]
    instructions_idx = next((i for i, s in enumerate(sections) if s.get("id") == "instructions"), None)
    if validation_idx is not None and final_directive_idx is not None and instructions_idx is not None:
        current_instructions = sections[instructions_idx]["content"]
        validation_content = sections[validation_idx]["content"]
        final_directive_content = sections[final_directive_idx]["content"]
        
        sections[instructions_idx]["content"] = f"""{current_instructions}

**Validation Checklist**:
{validation_content}

**Final Steps**:
{final_directive_content}"""
        modified = True
    
    # 4. Remove non-standard sections
    indices_to_remove = [critical_contract_idx, agent_design_idx, example_transform_idx, 
                         validation_idx, final_directive_idx]
    for idx in sorted([i for i in indices_to_remove if i is not None], reverse=True):
        sections.pop(idx)
        modified = True
    
    return modified


def fix_context_variables_agent_headings(sections: List[Dict]) -> bool:
    """Merge ContextVariablesAgent [EXAMPLE] into canonical [EXAMPLES]."""
    modified = False
    
    # Find the example section (may have different id)
    example_idx = next((i for i, s in enumerate(sections) 
                       if "[EXAMPLE" in s.get("heading", "")), None)
    examples_idx = next((i for i, s in enumerate(sections) if s.get("id") == "examples"), None)
    guidelines_idx = next((i for i, s in enumerate(sections) if s.get("id") == "guidelines"), None)
    
    if example_idx is not None:
        example_content = sections[example_idx]["content"]
        
        if examples_idx is not None:
            # Update existing examples
            sections[examples_idx]["content"] = example_content
        else:
            # Create examples section before guidelines
            if guidelines_idx is not None:
                sections.insert(guidelines_idx, {
                    "id": "examples",
                    "heading": "[EXAMPLES]",
                    "content": example_content
                })
            else:
                # Add at end before json_output_compliance
                json_idx = next((i for i, s in enumerate(sections) if s.get("id") == "json_output_compliance"), None)
                if json_idx:
                    sections.insert(json_idx, {
                        "id": "examples",
                        "heading": "[EXAMPLES]",
                        "content": example_content
                    })
        
        # Remove the non-standard example section
        sections.pop(example_idx)
        modified = True
    
    return modified


def fix_all_example_headings(agent_name: str, sections: List[Dict]) -> bool:
    """Fix any agent with [EXAMPLE - ...] headings to use [EXAMPLES]."""
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
    
    # Fix WorkflowImplementationAgent non-standard headings
    if "WorkflowImplementationAgent" in agents:
        print("\nProcessing WorkflowImplementationAgent...")
        sections = agents["WorkflowImplementationAgent"]["prompt_sections"]
        if fix_workflow_implementation_headings(sections):
            changed_agents.append("WorkflowImplementationAgent")
            print("  ✓ Merged non-standard headings into canonical sections")
    
    # Fix ContextVariablesAgent, ToolsManagerAgent, StructuredOutputsAgent, AgentsAgent, HookAgent, HandoffsAgent, OrchestratorAgent
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
                print(f"  ✓ Fixed [EXAMPLE] headings for {agent_name}")
    
    # Fix ContextVariablesAgent
    """Merge non-standard WorkflowArchitectAgent headings into canonical sections."""
    modified = False
    
    # Find sections
    separation_idx = next((i for i, s in enumerate(sections) if s.get("id") == "separation_of_concerns_critical"), None)
    tool_scope_idx = next((i for i, s in enumerate(sections) if s.get("id") == "tool_scope_system_critical"), None)
    pattern_hook_idx = next((i for i, s in enumerate(sections) if s.get("id") == "pattern_hook_integration"), None)
    context_idx = next((i for i, s in enumerate(sections) if s.get("id") == "context"), None)
    guidelines_idx = next((i for i, s in enumerate(sections) if s.get("id") == "guidelines"), None)
    runtime_idx = next((i for i, s in enumerate(sections) if s.get("id") == "runtime_integrations"), None)
    
    if separation_idx is not None and tool_scope_idx is not None and pattern_hook_idx is not None:
        # Extract content
        separation_content = sections[separation_idx]["content"]
        tool_scope_content = sections[tool_scope_idx]["content"]
        pattern_hook_content = sections[pattern_hook_idx]["content"]
        
        # 1. Append SEPARATION OF CONCERNS to [CONTEXT]
        if context_idx is not None:
            current_context = sections[context_idx]["content"]
            enhanced_context = f"""{current_context}

**Separation of Concerns**:

**WorkflowArchitect Agent (YOU)**: Pattern → Technical Primitives (WHAT runtime needs)
- Determine WHAT tools each phase requires (tool names, types, scopes)
- Determine WHAT context variables are needed (names, types, triggers)
- Determine WHAT lifecycle operations pattern requires (hooks, timing)
- Flag shared vs phase_specific tools for singleton compilation

**Implementation Agent (DOWNSTREAM)**: Blueprint → Agent Design (WHO uses WHAT and HOW)
- Read your technical_blueprint from context
- Design agents with tool usage descriptions (WHEN to call, HOW to interpret)
- Map blueprint.required_tools → agent.operations[] with usage patterns

**Spec Agents (COMPILATION)**: Blueprint → JSON Manifests
- Tool spec agent: Compiles technical_blueprint.tools → tools.json
- Context spec agent: Compiles technical_blueprint.context_variables → context_variables.json
- Handoff spec agent: Reads phases + pattern coordination → handoffs.json

**Pattern Hook Integration**:
Pattern-specific requirements are injected via update_agent_state hook:
- Hook function: inject_workflow_architect_guidance
- Location: workflows/Generator/tools/update_agent_state_pattern.py
- Content: Pattern ID → tools/vars/ops requirements per phase
- Example: "PHASE 1 (Planning): Tools: [analyze_request (shared), route_to_specialist (phase_specific)], Context Variables: [routing_started, current_domain], ..."

You read this injected guidance and adapt it to the specific workflow phases from workflow_strategy."""
            sections[context_idx]["content"] = enhanced_context
            modified = True
        
        # 2. Append TOOL SCOPE SYSTEM to [GUIDELINES]
        if guidelines_idx is not None:
            current_guidelines = sections[guidelines_idx]["content"]
            enhanced_guidelines = f"""{current_guidelines}

**Tool Scope Rules**:
Tools have two scopes that determine compilation strategy:

**shared (Module-Level Singleton)**:
- Used by MULTIPLE agents across MULTIPLE phases
- Compiled ONCE at module level, imported by all agents
- Examples: validate_email, send_notification, format_currency, log_event
- Flag these in required_tools with scope="shared"

**phase_specific (Agent-Owned)**:
- Used by SINGLE agent in SINGLE phase
- Compiled per-agent, not shared
- Examples: submit_feedback (ReviewAgent only), route_to_specialist (RouterAgent only)
- Flag these in required_tools with scope="phase_specific"

**Decision Rule**:
- If tool is generic utility (validation, formatting, notification) → shared
- If tool is agent-specific action (submit, route, analyze_specific_domain) → phase_specific
- If uncertain, default to shared (safer for future reuse)"""
            sections[guidelines_idx]["content"] = enhanced_guidelines
            modified = True
        
        # 3. Remove the non-standard sections (in reverse order to preserve indices)
        for idx in sorted([separation_idx, tool_scope_idx, pattern_hook_idx], reverse=True):
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
    
    # Fix WorkflowArchitectAgent non-standard headings
    if "WorkflowArchitectAgent" in agents:
        print("\nProcessing WorkflowArchitectAgent...")
        sections = agents["WorkflowArchitectAgent"]["prompt_sections"]
        if fix_workflow_architect_headings(sections):
            changed_agents.append("WorkflowArchitectAgent")
            print("  ✓ Merged non-standard headings into [RUNTIME INTEGRATION]")
    
    # Fix ContextVariablesAgent
    if "ContextVariablesAgent" in agents:
        print("\nProcessing ContextVariablesAgent...")
        sections = agents["ContextVariablesAgent"]["prompt_sections"]
        if fix_inputs_to_context("ContextVariablesAgent", sections):
            changed_agents.append("ContextVariablesAgent")
        complete_context_variables_agent(sections)
    
    # Fix RuntimeAgentsAgent
    if "AgentsAgent" in agents:
        print("\nProcessing AgentsAgent...")
        sections = agents["AgentsAgent"]["prompt_sections"]
        if fix_inputs_to_context("AgentsAgent", sections):
            changed_agents.append("AgentsAgent")
        complete_runtime_agents_agent(sections)
        if "AgentsAgent" not in changed_agents:
            changed_agents.append("AgentsAgent")
    
    # Complete ProjectOverviewAgent
    if "ProjectOverviewAgent" in agents:
        print("\nProcessing ProjectOverviewAgent...")
        sections = agents["ProjectOverviewAgent"]["prompt_sections"]
        complete_project_overview_agent(sections)
        changed_agents.append("ProjectOverviewAgent")
    
    # Complete HookAgent
    if "HookAgent" in agents:
        print("\nProcessing HookAgent...")
        sections = agents["HookAgent"]["prompt_sections"]
        complete_hook_agent(sections)
        changed_agents.append("HookAgent")
    
    # Complete HandoffsAgent
    if "HandoffsAgent" in agents:
        print("\nProcessing HandoffsAgent...")
        sections = agents["HandoffsAgent"]["prompt_sections"]
        complete_handoffs_agent(sections)
        changed_agents.append("HandoffsAgent")
    
    # Complete OrchestratorAgent
    if "OrchestratorAgent" in agents:
        print("\nProcessing OrchestratorAgent...")
        sections = agents["OrchestratorAgent"]["prompt_sections"]
        complete_orchestrator_agent(sections)
        changed_agents.append("OrchestratorAgent")
    
    # Complete DownloadAgent
    if "DownloadAgent" in agents:
        print("\nProcessing DownloadAgent...")
        sections = agents["DownloadAgent"]["prompt_sections"]
        complete_download_agent(sections)
        changed_agents.append("DownloadAgent")
    
    # Save changes
    if changed_agents:
        print(f"\n✓ Updated {len(changed_agents)} agents: {', '.join(changed_agents)}")
        save_agents(data)
        print("\n✓ All agents standardized successfully!")
    else:
        print("\n✓ No changes needed - all agents already standardized")


if __name__ == "__main__":
    main()
