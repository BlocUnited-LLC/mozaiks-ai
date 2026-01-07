# Repo Packaging Guide (Source of Truth)

## MozaiksAI Building Blocks (Runtime Engine + Workflow Packs)

These are the building blocks for MozaiksAI.

- **Runtime Engine** (The Base)
  - `core/` (transport, orchestration, persistence, observability, tokens)
  - `ChatUI/` (generic React chat + artifact surfaces)
  - `shared_app.py`, `run_server.py`
  - `scripts/` (`start-dev.ps1`, `start-app.ps1`, etc.)

- **Workflows** (Modular Capabilities)
  - **AG2 Workflow** (`workflows/{workflow_name}/`):
    - An atomic, functional group chat (e.g., "FrontendGenerator", "ValueEngine").
    - **Configuration manifests**
      - `agents.json` — Agent definitions and roles
      - `context_variables.json` — Workflow-scoped context settings
      - `handoffs.json` — Inter-agent handoff rules (Standard Edges)
      - `orchestrator.json` — Orchestration behavior and termination conditions
      - `structured_outputs.json` — Output schemas for agents
      - `tools.json` — Tool manifests with argument schemas
      - `ui_config.json` — UI surface declarations
    - **Micro-Orchestrator** (`workflows/{workflow_name}/_pack/`)
      - `manifest.json` — Defines the Children pack identity
      - `workflow_graph.json` — Defines Children GroupChats and decomposition logic (replaces signals.json)
      - `shared_context.json` — Context shared between children and other children
    - **Tool implementations**
      - `workflows/{workflow_name}/tools/` — Python stub files (`.py`) implementing tool callables
    - **UI components** (optional)
      - `ChatUI/src/workflows/{workflow_name}/components/` — JavaScript stub files (`.js`) for custom UI components tied to the tool callables
  - **Workflow Pack** (`workflows/_pack/`):
    - The "Meta" layer that orchestrates multiple AG2 Workflows.
    - **Macro-Orchestrator**
      - `manifest.json` — Defines the Parent pack identity
      - `workflow_graph.json` — Defines the **macro dependency graph** between workflows
      - `shared_context.json` — Context shared between parent and other parents

      **Macro Dependency Graph Semantics**

      - **Nodes**: Workflow IDs (e.g., `ValueEngine`, `AgentGenerator`, `AppGenerator`, `Governance`, `InvestmentAdvice`).
      - **Edges**: Directed dependencies `{ "from": "ValueEngine", "to": "AgentGenerator", "kind": "control" }`.
      - **Gating Rule** (conceptual):
        - For a given workflow `W`, let `parents(W)` be all nodes with edges `X -> W`.
        - `W` is **eligible to start** when every `X ∈ parents(W)` has at least one chat run whose status is `completed`.
      - **Example (Foundry Pack)**:
        - `ValueEngine -> AgentGenerator -> AppGenerator -> Governance` (sequential chain).
        - `InvestmentAdvice` has **no incoming edges** (can run at any time).
      - **PackRun (runtime view, not a config file)**:
        - At runtime, the orchestrator can maintain a `PackRun` record per enterprise/app:

          ```json
          {
            "pack_run_id": "...",
            "enterprise_id": "...",
            "workflows": {
              "ValueEngine":      { "chat_id": "ce1", "status": "completed" },
              "AgentGenerator":   { "chat_id": "ce2", "status": "completed" },
              "AppGenerator":     { "chat_id": "ce3", "status": "running" },
              "Governance":       { "chat_id": null,  "status": "not_started" },
              "InvestmentAdvice": { "chat_id": "ce4", "status": "completed" }
            }
          }
          ```

        - **Scheduler loop** (future runtime behavior): for each workflow in `not_started`, if the gating rule passes given this `PackRun`, the orchestrator creates a new chat session and marks it `running`.
      
---

## Target Repos 

### 1. `mozaiksai-clean` (clean for additional Workflows)
**Goal**: Runtime engine that anyone can embed into their app and point at their own declarative Workflow Packs.

- **Include**
  - Runtime Engine: `core/`, `ChatUI/`, `shared_app.py`, `run_server.py`
  - Workflows: EMPTY (Ready for `_pack/` and workflow folders)

---

### 2. `ag2-groupchat-generator` (Current Repo)
**Goal**: Ship the 'AgentGenerator' as a standalone product for AG2.ai or other vendors: "Design declarative AG2 groupchats here, then download artifacts."

- **Include**
  - Runtime Engine: `core/`, `ChatUI/`, `shared_app.py`, `run_server.py`
  - Workflow Pack: **AgentGenerator Pack**
    - `workflows/_pack/` (Manifest pointing to AgentGenerator workflow)
    - `workflows/AgentGenerator/` (The AgentGenerator workflow itself)
    - `ChatUI/src/workflows/AgentGenerator/components/`

---

### 3. `mozaiks` (planned)
**Goal**: The Mozaiks "foundry" backend to go from idea → workflows → app integration plan.

- **Include**
  - Runtime Engine: `core/`, `ChatUI/`, `shared_app.py`, `run_server.py`
  - Workflow Pack: **Foundry Pack** (Meta-Pack)
    - `workflows/_pack/` (Defines the graph: Value → Generator → App)
    - `workflows/ValueEngine/` (Step 1: Concept & Value Prop)
    - `workflows/Generator/` (Step 2: Agent Architecture - Dependent on ValueEngine)
    - `workflows/AppGenerator/` (Step 3: Integration Plan - Dependent on Generator)
      - *Note: May spawn child flows like Frontend/Backend/DB*
    - `workflows/Governance/` (Independent/Parallel: Audit & Compliance)

---

### 4. `mozaikscore` (planned)
**Goal**: The base app every Mozaiks-built app generated by the user runs on: user accounts, subscriptions, core pages, plugin system, and embedded runtime.

- **Include**
  - Runtime Engine: `core/`, `ChatUI/`, `shared_app.py`, `run_server.py`
  - Workflow Pack: **User's Generated Pack**
    - `workflows/_pack/` (Generated manifest)
    - `workflows/{generated_workflow_1}/`
    - `workflows/{generated_workflow_2}/`
    - `ChatUI/src/workflows/...`

---