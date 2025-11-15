"""Update each Generator agent with agent-specific [RUNTIME INTEGRATION] content"""

import json
import sys
from pathlib import Path

# Agent-specific RUNTIME INTEGRATION
AGENT_RUNTIME_CAPABILITIES = {
    "InterviewAgent": """Your job is purely conversational intake. You ask questions and capture responses.

The runtime handles ALL automation infrastructure:
- Your responses are automatically persisted to the database
- Context variables are injected into your prompt before each turn
- Your final "NEXT" token triggers automatic handoff to the next agent
- No tool calling, no structured outputs - just natural conversation

Focus ONLY on asking clear questions and detecting ambiguous terminology.""",

    "PatternAgent": """Your job is purely pattern selection. You analyze requirements and output a pattern number (1-9).

The runtime handles ALL downstream coordination:
- Your selected pattern is automatically stored in context variables
- Pattern-specific guidance is automatically injected into downstream agents via update_agent_state hooks
- Your structured output triggers automatic handoff to the next agent
- No workflow design, no implementation details - just pattern selection

Focus ONLY on selecting the optimal AG2 orchestration pattern based on the users automation needs and workflow characteristics.""",

    "WorkflowStrategyAgent": """Your job is purely strategic blueprint design. You define WHAT phases exist and WHEN approvals are needed.

The runtime handles ALL implementation:
- Phase structure is automatically passed to downstream agents for technical design
- Approval gates become handoff conditions compiled by the runtime
- Lifecycle operations you define become hooks executed by the runtime
- Pattern-specific guidance is automatically injected via update_agent_state hooks

Focus ONLY on high-level workflow strategy: trigger type, phases, approval checkpoints, and business-specific lifecycle operations. DO NOT design agents, tools, or handoffs - that's downstream work.""",

    "WorkflowArchitectAgent": """Your job is purely technical architecture. You design agents, phases, and agent specifications based on upstream strategic blueprint.

The runtime handles ALL orchestration:
- Your phase_agents output is automatically passed to downstream agents
- Agent human_interaction settings become runtime handoff conditions
- Agent operations become tool definitions compiled by downstream agents
- Pattern-specific guidance is automatically injected via update_agent_state hooks

Focus ONLY on WHO does the work (agent names, roles, specialist domains) and HOW they interact (context vs approval). DO NOT design tool schemas or handoff conditions - that's downstream work.""",

    "WorkflowImplementationAgent": """Your job is purely action plan compilation. You translate upstream strategy + architecture into a complete execution plan.

The runtime handles ALL workflow execution:
- Your ActionPlan output triggers UI tool rendering (Mermaid diagram)
- Phase structure is automatically used by downstream agents for tool/handoff generation
- Approval gates become context variable triggers and UI interactions
- Pattern-specific guidance is automatically injected via update_agent_state hooks

Focus ONLY on compiling a complete, validated ActionPlan that mirrors upstream phase structure exactly. DO NOT design tools or context variables - that's downstream work.""",

    "ProjectOverviewAgent": """Your job is purely diagram generation. You create Mermaid sequence diagrams visualizing the workflow.

The runtime handles ALL rendering and persistence:
- Your Mermaid code is automatically rendered in the UI via diagram renderer component
- Diagram is persisted to database and associated with the workflow
- Pattern-specific guidance is automatically injected via update_agent_state hooks
- Your structured output triggers automatic handoff to downstream agents

Focus ONLY on generating valid Mermaid syntax that accurately reflects upstream ActionPlan phases and pattern structure.""",

    "ContextVariablesAgent": """Your job is purely context variable schema design. You define WHAT variables exist and WHEN they update.

The runtime handles ALL variable lifecycle:
- Your definitions are compiled into context_variables.json by downstream agents
- Runtime initializes variables from DB/environment/static JSON automatically
- DerivedContextManager processes agent_text and ui_response triggers automatically
- Pattern-specific guidance is automatically injected via update_agent_state hooks

Focus ONLY on defining variable names, types, sources, and triggers. DO NOT implement variable update logic - the runtime handles that.""",

    "ToolsManagerAgent": """Your job is purely tool schema definition. You define WHAT tools exist and their input/output contracts.

The runtime handles ALL tool execution:
- Your tool manifest is compiled into tools.json by downstream agents
- Runtime registers tools on agents automatically
- AutoToolEventHandler executes async UI tools automatically
- Pattern-specific guidance is automatically injected via update_agent_state hooks

Focus ONLY on tool metadata: names, types (UI_Tool vs Agent_Tool), parameters, and which agents own them. DO NOT implement tool functions - that's downstream work.""",

    "UIFileGenerator": """Your job is purely UI tool code generation. You create React components and Python tool stubs from upstream tool schemas.

The runtime handles ALL tool integration:
- Your generated files are written to disk automatically
- Runtime discovers and imports tool modules automatically
- use_ui_tool() in Python stubs sends events to frontend automatically
- Frontend UIToolRenderer displays your React components automatically

Focus ONLY on generating syntactically correct React/Python code that matches upstream tool schemas. DO NOT design the schema itself - that's upstream work.""",

    "AgentToolsFileGenerator": """Your job is purely Agent_Tool code generation. You create Python tool functions from upstream tool schemas.

The runtime handles ALL tool registration:
- Your generated files are written to disk automatically
- Runtime imports and registers tools on agents automatically
- Tool invocation (sync or async) is handled by runtime based on auto_tool_mode
- Tools are available to agents via AG2's native tool calling

Focus ONLY on generating syntactically correct Python functions that implement business logic. DO NOT design tool schemas - that's upstream work.""",

    "StructuredOutputsAgent": """Your job is purely Pydantic schema design. You define structured output models and registry mappings from upstream agent roster.

The runtime handles ALL validation:
- Your models are compiled into Python classes by downstream agents
- Runtime validates agent outputs against your schemas automatically
- Validation failures trigger agent re-generation with error feedback
- Validated outputs enable auto-invocation for UI tools

Focus ONLY on defining field names, types, and which agents emit which schemas. DO NOT implement validation logic - the runtime handles that.""",

    "AgentsAgent": """Your job is purely agent configuration compilation. You generate system messages and agent settings from upstream workflow design.

The runtime handles ALL agent instantiation:
- Your agent definitions are compiled into agents.json by downstream agents
- Runtime creates AG2 ConversableAgent instances automatically
- System messages, tools, and structured outputs are wired automatically
- Agents are registered in GroupChat and handoffs are configured automatically

Focus ONLY on crafting comprehensive system messages and setting flags (auto_tool_mode, structured_outputs_required). DO NOT implement agent behavior - system messages guide that.""",

    "HookAgent": """Your job is purely lifecycle hook implementation. You write custom before_chat, after_chat, and update_agent_state hooks when needed.

The runtime handles ALL hook execution:
- Your hooks are automatically imported and registered on the workflow
- Runtime calls hooks at the correct lifecycle moments
- Hooks receive full runtime context (chat_id, enterprise_id, agent instances)
- Hook exceptions are caught and logged automatically

Focus ONLY on implementing custom business logic for hooks when needed. Most workflows don't need custom hooks - the runtime provides standard lifecycle behavior.""",

    "HandoffsAgent": """Your job is purely handoff rule definition. You define WHO hands off to WHOM under WHAT conditions from upstream workflow design.

The runtime handles ALL handoff execution:
- Your rules are compiled into handoffs.json by downstream agents
- Runtime creates AG2 OnContextCondition/StringLLMCondition primitives automatically
- Handoffs are registered on agents and evaluated automatically
- Routing logic executes based on context variables and LLM evaluation

Focus ONLY on defining source→target agent pairs and conditions. DO NOT implement routing logic - the runtime compiles and executes it.""",

    "OrchestratorAgent": """Your job is purely orchestration config compilation. You define startup mode, initial message, and visual agents from upstream workflow design.

The runtime handles ALL workflow execution:
- Your config is compiled into orchestration.json by downstream agents
- Runtime launches the workflow with your specified settings
- GroupChat is initialized with your recipient and visual_agents
- Workflow runs until TERMINATE or max_turns reached

Focus ONLY on final configuration parameters. DO NOT design workflow logic - that's been defined by upstream agents.""",

    "DownloadAgent": """Your job is purely download trigger. You emit a structured output that triggers file generation.

The runtime handles ALL file operations:
- Your DownloadRequest output auto-invokes the file generation tool
- Tool gathers all upstream agent outputs from persistence automatically
- Files are written to temp directory automatically
- UI renders download component with download links automatically

Focus ONLY on emitting the trigger with a concise agent_message. DO NOT list files or create summaries - the tool handles that.""",
}

def update_runtime_capabilities():
    """Update [RUNTIME INTEGRATION] for each agent"""
    
    agents_json_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"
    
    with open(agents_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if "agents" not in data:
        print("❌ agents key not found")
        return False
    
    agents = data["agents"]
    updated_count = 0
    
    for agent_name, agent_config in agents.items():
        if agent_name not in AGENT_RUNTIME_CAPABILITIES:
            print(f"⚠️  No specific content defined for {agent_name}, skipping")
            continue
        
        # Find [RUNTIME INTEGRATION] section
        runtime_section = None
        for section in agent_config.get("prompt_sections", []):
            if section["id"] == "runtime_integrations":
                runtime_section = section
                break
        
        if not runtime_section:
            print(f"⚠️  No [RUNTIME INTEGRATION] section found in {agent_name}, skipping")
            continue
        
        # Update content
        runtime_section["content"] = AGENT_RUNTIME_CAPABILITIES[agent_name]
        updated_count += 1
        print(f"✅ Updated {agent_name}")
    
    # Write back
    with open(agents_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n🎉 Successfully updated {updated_count} agents with agent-specific [RUNTIME INTEGRATION]")
    return True

if __name__ == "__main__":
    success = update_runtime_capabilities()
    sys.exit(0 if success else 1)
