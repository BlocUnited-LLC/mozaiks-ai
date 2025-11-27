# Semantic Context Injection Strategy

## Overview
To ensure cohesion across the Generator agents without introducing stateful dependencies, we have implemented a "Semantic Context Injection" mechanism in the `update_agent_state_pattern.py` hooks.

## Mechanism
The runtime hooks now perform the following steps before injecting the standard pattern guidance:
1.  **Retrieve Upstream Context**: Using `_get_upstream_context(agent, key)`, the hook fetches the structured output of previous agents from the `context_variables`.
2.  **Generate Semantic Summary**: The hook parses the upstream JSON (e.g., `WorkflowStrategy`, `TechnicalBlueprint`) and generates a concise text summary of the key decisions (Phases, UI Components, Tools, Hooks).
3.  **Inject into Prompt**: This summary is prepended to the system message as a `[UPSTREAM CONTEXT]` block, explicitly instructing the agent to align its output with these decisions.

## Implemented Injections

| Agent | Upstream Source | Injected Context | Purpose |
| :--- | :--- | :--- | :--- |
| **WorkflowArchitectAgent** | `WorkflowStrategy` | Defined Phases | Ensure UI components and lifecycle hooks align with the strategy phases. |
| **WorkflowImplementationAgent** | `WorkflowStrategy`, `TechnicalBlueprint` | Phases, UI Components | Ensure agents are created for all phases and support the defined UI components. |
| **UIFileGenerator** | `TechnicalBlueprint` | UI Components | Ensure React components are generated exactly as specified in the blueprint. |
| **AgentToolsFileGenerator** | `PhaseAgents` | Agent Tools | Ensure Python tools are generated for all tools defined in the agent specs. |
| **HookAgent** | `TechnicalBlueprint`, `PhaseAgents` | Lifecycle & System Hooks | Ensure hooks are generated for all lifecycle and system hooks defined upstream. |

## Benefits
- **Stateless Cohesion**: Agents "remember" and respect previous decisions without database lookups.
- **Reduced Hallucination**: Explicit constraints prevent agents from inventing new phases or components that weren't planned.
- **Pattern Alignment**: The semantic context works *alongside* the pattern guidance, ensuring both structural correctness and specific content alignment.
