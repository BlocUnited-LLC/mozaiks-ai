# Agent Taxonomy Stateless Strategy

> **Last Updated**: 2025-06-27  
> **Status**: Implemented  
> **Concept**: Stateless propagation of Agent Roles (`agent_type`) through the AgentGenerator Workflow.

---

## Executive Summary

The **Agent Role Taxonomy** (`intake`, `router`, `worker`, `evaluator`, `orchestrator`) is implemented as a strictly **stateless** data flow. 

Just like the Human Interaction model, the Agent Taxonomy relies entirely on **Structured Outputs** passed through the conversation history. No agent relies on external state, hidden variables, or side-loaded configuration files.

## The Stateless Data Flow

The taxonomy flows linearly through the AgentGenerator chain, with each agent deriving or consuming the `agent_type` based solely on upstream JSON outputs.

### Step 1: Derivation (The Origin)
**Agent**: `WorkflowImplementationAgent`  
**Input**: `WorkflowStrategy` (Pattern) + `TechnicalBlueprint` (UI Contracts)  
**Logic**: Pure function derivation based on pattern and module purpose.
- IF first agent + user-facing entry point → `intake`
- IF routing logic + no user interaction → `router`  
- IF `human_interaction`="approval" or "iterative" → `evaluator`
- IF hub/coordinator in Star/Hierarchical/Redundant → `orchestrator`
- ELSE → `worker` (default)

**Output**: `ModuleAgents` JSON
```json
{
  "module_agents": [
    {
      "agents": [
        {
          "agent_name": "TriageAgent",
          "agent_type": "intake"
        },
        {
          "agent_name": "ResearchWorker", 
          "agent_type": "worker"
        }
      ]
    }
  ]
}
```

### Step 2: Consumption - Triggers (The Logic)
**Agent**: `ContextVariablesAgent`  
**Input**: `ModuleAgents` (from Step 1)  
**Logic**: 
- Scan for `agent_type` values.
- `router` agents get routing-related context variable triggers.
- `evaluator` agents get approval/feedback context variable triggers.
**Output**: `ContextVariablesPlan` JSON
- Defines *what* the agent triggers, based on *who* the agent is.

### Step 3: Consumption - Prompts (The Instruction)
**Agent**: `AgentsAgent`  
**Input**: `ModuleAgents` (from Step 1)  
**Logic**:
- Read `agent_type`.
- Inject specific system prompt sections:
    - `intake` → "You are the first point of contact. Greet the user..."
    - `router` → "You are a Router. Analyze and route based on..."
    - `worker` → "You are a Worker. Execute your assigned task..."
    - `evaluator` → "You are a Reviewer. Evaluate quality..."
    - `orchestrator` → "You are a Coordinator. Manage your team..."
**Output**: `agents.json` (Runtime Configuration)
- The final runtime artifact now contains the taxonomy, persisted for the runtime to use.

## Stateless Guarantees

1.  **Zero Shared State**: Agents do not share Python objects or memory. They only read the JSON text emitted by previous agents in the chat history.
2.  **Deterministic**: Given the same `WorkflowStrategy` and `TechnicalBlueprint`, the `WorkflowImplementationAgent` will *always* produce the same `agent_type` assignments.
3.  **Self-Contained**: The logic for agent type assignment is embedded directly in the `WorkflowImplementationAgent`'s system prompt, not in an external library.

## Why This Matters

By keeping this stateless:
- **Resilience**: If the generation process is interrupted, it can be resumed or re-run deterministically.
- **Modularity**: We can change the definition of agent types in the `WorkflowImplementationAgent` prompt without breaking the `AgentsAgent` (as long as the JSON schema remains valid).
- **Transparency**: The `agent_type` is explicitly visible in the `ModuleAgents` output, making debugging easy. You can see exactly *why* an agent was designated as intake, router, worker, evaluator, or orchestrator.

---

## Agent Type to AG2 Pattern Mapping

| Pattern | Primary Agent Types |
|---------|---------------------|
| 1. Context-Aware Routing | `router` + `worker` (specialists) |
| 2. Escalation | `intake` + `worker` (tiered) |
| 3. Feedback Loop | `intake` + `worker` + `evaluator` |
| 4. Hierarchical | `orchestrator` (executive/managers) + `worker` (specialists) |
| 5. Organic | `worker` (all) - GroupChatManager handles routing |
| 6. Pipeline | `intake` + `worker` (stage agents) |
| 7. Redundant | `orchestrator` + `worker` (parallel) + `evaluator` |
| 8. Star | `orchestrator` (hub) + `worker` (spokes) |
| 9. Triage with Tasks | `intake` + `orchestrator` + `worker` |
