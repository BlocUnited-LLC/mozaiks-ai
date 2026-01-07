# AG2 Pattern Guidance (Prompt-Friendly)

This is the **runtime/generator prompt injection** summary for the 9 AG2 orchestration patterns used by MozaiksAI.

- Full reference: `docs/source_of_truth/pattern_guidance_SOT.md`
- Pattern examples: `docs/pattern_examples/pattern_<id>_*.yaml` (multi-doc YAML; sections like `PatternSelection`, `WorkflowStrategy`, `StateArchitecture`, `UXArchitecture`, `AgentRoster`, etc.)

---

## Pattern IDs

| ID | Pattern | Best for |
|---:|---|---|
| 1 | Context-Aware Routing | Multi-domain classification + specialist routing |
| 2 | Escalation | Tiered support with confidence thresholds |
| 3 | Feedback Loop | Iterative refine → review → revise until approved |
| 4 | Hierarchical | Exec → manager → specialist delegation stacks |
| 5 | Organic | Collaborative “swarm” style ideation/synthesis |
| 6 | Pipeline | Sequential stage-by-stage processing |
| 7 | Redundant | Parallel variants + evaluator/selector |
| 8 | Star | Hub-and-spoke coordination with a central controller |
| 9 | Triage with Tasks | Decompose into tasks, then execute tasks in order |

---

## Selection Heuristics (quick rules)

- “Route/categorize different request types” → **1**
- “Escalate when confidence is low / tier 1 → tier 2” → **2**
- “Review/approve/revise until it’s right” → **3**
- “A manager breaks work down for specialists” → **4**
- “Brainstorm/collaborate across roles, emergent flow” → **5**
- “Step-by-step stages with clear ordering” → **6**
- “Run multiple approaches in parallel then judge/merge” → **7**
- “One coordinator delegates to many spokes and consolidates” → **8**
- “Turn request into a task list and execute tasks” → **9**

---

## Pattern Notes (what makes each pattern distinct)

### 1) Context-Aware Routing
- Topology: router → specialist (branching) → user
- Key mechanism: **classification + conditional handoffs** (`OnContextCondition`)

### 2) Escalation
- Topology: triage → tier1 → tier2 → expert
- Key mechanism: **confidence threshold** triggers handoff to the next tier

### 3) Feedback Loop
- Topology: drafter → reviewer → reviser (repeat) → finalizer
- Key mechanism: **quality gate** (`needs_revision` / “approved”) controls loop

### 4) Hierarchical
- Topology: leader → managers → specialists → leader (synthesis)
- Key mechanism: **delegation + synthesis up the chain**

### 5) Organic
- Topology: group chat collaboration
- Key mechanism: **emergent coordination**; avoid over-constraining handoffs

### 6) Pipeline
- Topology: stage1 → stage2 → stage3 …
- Key mechanism: **linear** sequencing with clear inputs/outputs per step

### 7) Redundant
- Topology: run N alternatives in parallel → evaluator selects/merges
- Key mechanism: **parallelism + evaluation**

### 8) Star
- Topology: hub ↔ spokes (hub delegates + consolidates)
- Key mechanism: **single “control plane”** agent coordinating multiple worker agents

### 9) Triage with Tasks
- Topology: triage → task manager → task executor(s)
- Key mechanism: **explicit task list** + execution tracking

