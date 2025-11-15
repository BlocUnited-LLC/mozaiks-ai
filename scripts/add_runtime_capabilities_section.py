"""
Add [RUNTIME INTEGRATION] section to all agents in agents.json.
This section educates agents about what the runtime automatically handles,
preventing them from generating redundant or conflicting logic.
"""

import json
from pathlib import Path

def add_runtime_capabilities():
    agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    with open(agents_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Generalized RUNTIME INTEGRATION content for all agents
    runtime_capabilities_content = """The MozaiksAI runtime AUTOMATICALLY handles these orchestration concerns. DO NOT generate logic for these features:

1. **Context Variable Lifecycle**: Runtime initializes context from DB/environment/static JSON, processes derived variables via DerivedContextManager when agent_text triggers fire, and updates variables when UI tools return ui_response triggers. Context variables are declaratively defined in context_variables.json and managed by the runtime.

2. **Handoff Routing**: Runtime compiles handoff rules from handoffs.json into AG2 OnContextCondition/StringLLMCondition primitives and executes routing logic automatically. Handoffs are declaratively defined and the runtime handles all transition logic.

3. **Tool Registration & Invocation**: Runtime automatically registers tools from tools.json, wires auto_tool_mode agents to AutoToolEventHandler for async execution, and publishes tool events/responses. Tools are declaratively defined and the runtime handles registration and invocation.

4. **Agent Instantiation**: Runtime creates AG2 ConversableAgent instances from agents.json, applies system messages, registers tools, enforces structured outputs, and manages conversation flow. Agent configuration is declarative and runtime-managed.

5. **UI Tool Integration**: Runtime sends UI_Tool events to frontend, renders components, captures user interactions, and updates context automatically. UI tools are declaratively defined in tools.json with ui_component metadata.

6. **Event Transport & Persistence**: Runtime manages WebSocket transport, MongoDB persistence via AG2PersistenceManager, event streaming, and observability hooks. All runtime infrastructure is pre-built.

7. **Multi-Tenancy & Token Tracking**: Runtime enforces enterprise_id and user_id boundaries, tracks token usage via MozaiksStream, and maintains session isolation. Tenancy is built into the platform.

**Critical Boundaries**:
- You work with DECLARATIVE configurations (JSON manifests) that the runtime interprets
- You do NOT implement runtime features, orchestration logic, or infrastructure code
- You do NOT create custom handlers for context updates, handoffs, tool invocation, or UI interactions
- You ONLY define WHAT should exist (agents, tools, context vars, handoffs) in declarative format

**What You CAN Define** (when appropriate for your role):
- Agent roles, capabilities, and system messages (agents.json)
- Tool schemas and metadata (tools.json)
- Context variable definitions and triggers (context_variables.json)
- Handoff rules and conditions (handoffs.json)
- Workflow phases and orchestration patterns (workflow strategy)
- Custom business logic specific to the workflow domain

**Golden Rule**: If it's about HOW the runtime executes workflows → it's already implemented. If it's about WHAT the workflow should do → define it declaratively."""
    
    # Agents that should get the section
    # (WorkflowStrategyAgent already has a specialized version)
    agents_to_update = [
        "InterviewAgent",
        "PatternAgent", 
        "WorkflowArchitectAgent",
        "WorkflowImplementationAgent",
        "ProjectOverviewAgent",
        "ContextVariablesAgent",
        "ToolsManagerAgent",
        "UIFileGenerator",
        "AgentToolsFileGenerator",
        "StructuredOutputsAgent",
        "AgentsAgent",
        "HookAgent",
        "HandoffsAgent",
        "OrchestratorAgent",
        "DownloadAgent"
    ]
    
    for agent_name in agents_to_update:
        if agent_name not in data["agents"]:
            print(f"⚠️  Agent {agent_name} not found")
            continue
        
        sections = data["agents"][agent_name]["prompt_sections"]
        
        # Check if already has runtime_integrations section
        has_runtime = any(
            s.get("id", "").startswith("runtime_integrations") 
            for s in sections
        )
        
        if has_runtime:
            print(f"⏭️  {agent_name} already has [RUNTIME INTEGRATION]")
            continue
        
        # Find position: after [CONTEXT] or before [GUIDELINES]
        insert_index = None
        
        # Try to insert after [CONTEXT]
        for i, section in enumerate(sections):
            if section.get("id") == "context":
                insert_index = i + 1
                break
        
        # Fallback: insert before [GUIDELINES]
        if insert_index is None:
            for i, section in enumerate(sections):
                if section.get("id") == "guidelines":
                    insert_index = i
                    break
        
        # Last fallback: insert after [OBJECTIVE]
        if insert_index is None:
            for i, section in enumerate(sections):
                if section.get("id") == "objective":
                    insert_index = i + 1
                    break
        
        # Ultimate fallback: insert at position 3 (after role, objective, context typically)
        if insert_index is None:
            insert_index = min(3, len(sections))
        
        # Create the new section
        new_section = {
            "id": "runtime_integrations",
            "heading": "[RUNTIME INTEGRATION]",
            "content": runtime_capabilities_content
        }
        
        # Insert it
        sections.insert(insert_index, new_section)
        print(f"✅ Added [RUNTIME INTEGRATION] to {agent_name} at position {insert_index}")
    
    # Write back
    with open(agents_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("\n✓ RUNTIME INTEGRATION section added to all agents")

if __name__ == "__main__":
    add_runtime_capabilities()
