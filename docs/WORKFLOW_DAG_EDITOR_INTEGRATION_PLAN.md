# Workflow Visual DAG Editor Integration Plan

> Goal: Add an interactive, round‑trip, versioned visual DAG (graph) editor for workflow configurations (JSON-first, agents + handoffs) with real‑time collaboration readiness, safe persistence, validation, and hot reload—without breaking existing execution paths; provide a migration path from legacy YAML.

---
## 1. Scope Overview
Provide a graphical React Flow–based editor enabling users to:
- Visualize current workflow graph (agents as nodes, handoffs as edges)
- Add / remove / connect agents visually
- Edit handoff conditions & attributes
+ Preview and validate changes (dry run)
+ Persist changes back to JSON (single `workflow.json` or segmented `agents.json`/`handoffs.json`) with versioning and rollback; optionally support YAML round-trip during migration
+ Observe live runtime status overlay (phase 4+)

Non-goals (initial phases): Multi-user conflict-free concurrent edits (deferred), arbitrary code editing, execution simulation sandbox.

---
## 2. High-Level Architecture Additions
```
+-------------------+         WebSocket / REST         +---------------------------+
|  React Flow UI    |  <---------------------------->  |  Workflow Graph Service   |
|  (ChatUI)         |   graph.snapshot / diff.apply    |  (FastAPI extension)      |
+---------+---------+                                  +------------+--------------+
          |                                                       |
          | YAML diff ops                                         | YAML load/save (atomic)
          |                                                       v
          |                                          +-----------------------------+
          |                                          | workflow.json (or agents.json / handoffs.json) |
          |                                          +-----------------------------+
          |                                                       |
          |                                            Hot reload (existing AG2)
          v                                                       v
+---------------------+                               +---------------------------+
| Status Overlay Feed |  <-- execution events ---     |  Runtime Workflow Engine  |
+---------------------+                               +---------------------------+
```

---
## 3. Repository Components
| Area | Purpose | Action |
|------|---------|--------|
| `workflows/Generator/` (and other workflow dirs later) | Source YAML (agents, handoffs) | Read / write via new service layer |
| `core/data/` | Existing models (WorkflowStatus, persistence) | Reuse; add graph data models module |
| `core/transport/` | WebSocket event emission | Add new event types (graph.*) |
| `core/workflow/` | Workflow registry init / reload | Extend to support explicit reload trigger after edits |
| `core/observability/` | Logging & metrics | Add counters for graph edits, validation failures |
| `ChatUI/src/workflows/Generator/components/` | New React components for editor UI | Add `WorkflowGraphEditor.jsx` / panel integration |
| `ChatUI/src/services/` | API client layer | Add `workflowGraphApi.js` |
| `ChatUI/src/context/` | Maybe store graph/editor state | Optional Zustand or context provider |
| `docs/` | Add this plan + future user guide | New docs (this file + user guide) |
| `requirements.txt` | Add backend libs (ruamel.yaml, deepdiff, filelock, pydantic if not present) | Deferred until implementation |
| `package.json` (ChatUI) | Add frontend libs (react-flow, dagre, zustand, js-yaml, monaco-editor) | Deferred until implementation |

---
## 4. New Files to Add
Backend (Python):
- `core/workflow/graph_models.py` — Pydantic/dataclass definitions (AgentNode, HandoffEdge, WorkflowGraph, DiffOperation)
- `core/workflow/graph_loader.py` — Load YAML → internal graph; compute checksum & version discovery
- `core/workflow/graph_serializer.py` — Apply operations → validate → write YAML (atomic temp + rename)
- `core/workflow/graph_validator.py` — Structural, semantic validations (cycles, orphan agents, conditions)
- `core/workflow/graph_versioning.py` — Version & audit log management (`.workflow_versions/<workflow>/...`)
- `core/workflow/graph_diff.py` — DeepDiff/structured diff utilities (optional; for preview)
- `core/workflow/graph_endpoints.py` — FastAPI router (GET graph, POST diff, POST validate, POST rollback)
- `core/workflow/graph_events.py` — Emit WebSocket events (snapshot, diff_applied, rejected, rollback)

Frontend (React):
- `ChatUI/src/workflows/Generator/components/WorkflowGraphEditor.jsx`
- `ChatUI/src/workflows/Generator/components/GraphSidebar.jsx`
- `ChatUI/src/workflows/Generator/state/useWorkflowGraphStore.js`
- `ChatUI/src/workflows/Generator/services/workflowGraphApi.js`
- `ChatUI/src/workflows/Generator/types/graphTypes.js`

Documentation:
- `docs/WORKFLOW_DAG_EDITOR_USER_GUIDE.md` (later)

Auxiliary:
- `.workflow_versions/` (directory created on demand)

---
## 5. MIT / Permissive Library Selections
Frontend:
- `react-flow` (MIT) – core graph canvas & diff events
- `dagre` (MIT) – auto layout (deterministic)
- `zustand` (MIT) – local state store
- `js-yaml` (MIT) – client-side YAML parse for preview (optional)
- `monaco-editor` (MIT) – side-by-side raw YAML & diff viewer (optional Phase 3)

Backend:
- `ruamel.yaml` (MIT) – round-trip safe YAML (preserves comments/order)
- `deepdiff` (MIT) – structural diff for preview / validation aid
- `filelock` (MIT) – atomic file edit coordination
- `pydantic` (MIT) – payload validation (likely already present via FastAPI)
- `networkx` (BSD-3) – optional cycle / reachability checks (permissive)
- Hashing: built-in `hashlib.blake2b` (avoid extra dependency) or `xxhash` (BSD-2) if performance needed later.

---
## 6. Data & Operation Model
### 6.1 Internal Graph Structures
```python
AgentNode { id, name, role?, model?, metadata? }
HandoffEdge { id, from_agent, to_agent, condition="default", priority?, label? }
WorkflowGraph { workflow_name, version:int, checksum:str, agents: {id->AgentNode}, edges: {id->HandoffEdge}, created_at, last_modified_at }
```

### 6.2 Diff Operation Schema
```json
{
  "workflow": "Generator",
  "base_version": 7,
  "operations": [
    {"op":"add_agent", "id":"Researcher", "spec":{...}},
    {"op":"remove_agent", "id":"LegacyCritic"},
    {"op":"add_handoff", "id":"h_983", "from":"Planner", "to":"Engineer", "condition":"default"},
    {"op":"update_handoff", "id":"h_983", "patch": {"condition":"on_approval"}},
    {"op":"remove_handoff", "id":"h_old"}
  ]
}
```
Return payload:
```json
{ "success": true, "new_version": 8, "warnings": [], "graph": { ... }, "applied_ops": 5 }
```

---
## 7. Workflow YAML Round-Trip Strategy
- Load: parse `workflow.json` (or segmented `agents.json` & `handoffs.json`) into in-memory graph
- Preserve: Use ruamel to maintain comments and ordering
- Apply ops: mutate model
- Re-serialize: Write `workflow.json` (or segmented JSON files) back (only if changed) via temp files (`workflow.json.tmp`) then atomic rename
- Compute checksum: `blake2b(json_dumps(agents_section, sort_keys=True).encode() + b'\n---\n' + json_dumps(handoffs_section, sort_keys=True).encode()).hexdigest()[:16]`
- Version bump: increment stored version in audit log file or sidecar `workflow_meta.json`

### 7.1 Version & Audit Storage Options
Option A (Sidecar JSON) — `workflows/Generator/workflow_meta.json`:
```json
{ "version": 8, "checksum": "a1c9d3f8e4ab1122", "history_dir": ".workflow_versions/Generator" }
```
Option B (Derive from history count) — simpler but requires listing directory. (Choose A for constant time.)

### 7.2 Atomicity
1. Acquire `filelock` on `workflows/Generator/.edit.lock`
2. Re-read current meta → verify `base_version`
3. Apply + validate
4. Write temp files & flush
5. Move into place
6. Update meta & append audit JSON in `.workflow_versions/Generator/<timestamp>-v<version>.json`
7. Release lock

---
## 8. Validation Pipeline
Order:
1. Schema validation (Pydantic) of diff ops
2. Referential integrity (edge endpoints exist)
3. Uniqueness (agent IDs, edge IDs)
4. Optional cycle policy (fail or warn) — configurable
5. Entry & termination coverage (ensure at least one viable start node)
6. Handoff condition normalization / whitelist (`default`, `on_approval`, predicate syntax)
7. Resulting YAML round-trip hash stable
8. Size / complexity limits (prevent pathological graphs)

Return warnings separately from errors for non-fatal advisories (e.g., isolated subgraph).

---
## 9. Transport & Event Schema Additions
WebSocket events (namespace: `workflow.graph`):
- `workflow.graph.snapshot` → full graph (initial load / reconnect)
- `workflow.graph.diff_applied` → { version, applied_ops, graph }
- `workflow.graph.rejected` → { reason, errors, base_version }
- `workflow.graph.rollback` → { restored_version, graph }
- `workflow.graph.status_overlay` (phase 4) → { agent_states: {id: state}, active_edges: [edgeId] }

Minimal required integration: modify `simple_transport.py` (or equivalent) to multiplex these event kinds; add helper send function.

---
## 10. Backend Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/workflow/{name}/graph` | Return current graph + version + checksum |
| POST | `/workflow/{name}/graph/diff` | Apply diff operations |
| POST | `/workflow/{name}/graph/validate` | Dry-run diff (no write) |
| POST | `/workflow/{name}/graph/rollback` | Roll back to prior version |
| GET | `/workflow/{name}/graph/history` | List recent versions (metadata only) |

Auth / security (future): require user role (admin/editor) for mutating routes.

---
## 11. Frontend Integration Flow
1. On panel open → fetch `GET /graph` → store in `useWorkflowGraphStore`
2. Render nodes & edges via React Flow (deterministic layout after dagre pass)
3. Edge / node modifications trigger `onNodesChange` / `onEdgesChange` → convert to operations
4. Batch operations (debounce ~400ms) → POST diff (optimistic UI) OR store as draft until user clicks Save
5. On response success → update local version/state; else revert & show error diff
6. Listen on WebSocket for `diff_applied` to sync external changes (multi-user future)

---
## 12. Diff Mapping Logic (Frontend)
Changes from React Flow are normalized into ops:
- Node added → `add_agent`
- Node removed → `remove_agent`
- Edge added → `add_handoff`
- Edge removed → `remove_handoff`
- Edge label / condition edit (via side panel form) → `update_handoff`
- Agent property edit (role/model) → `update_agent` (add op type during phase 2)

Position changes are cosmetic (store locally only, optionally persisted in metadata if desired later).

---
## 13. AG2 Alignment
AG2 currently consumes YAML definitions (agents, handoffs). This design:
- Keeps YAML canonical → no shadow JSON state
- Performs hot reload by invoking existing registry refresh (extend existing initializer with `reload_workflow(name)`)
- Avoids introducing a second representation (unlike adopting a foreign JSON schema like Waldiez)

Waldiez Consideration:
- Provides its own graph JSON schema; adopting it would require bidirectional YAML↔Waldiez transformations & risk data loss for custom fields
- Adds maintenance overhead & divergence
Decision: Stay native with minimal, explicit operations over existing YAML.

---
## 14. Security & Integrity
| Concern | Mitigation |
|---------|------------|
| Stale write (lost update) | base_version + checksum verification |
| Partial write / crash | temp file + atomic rename + lock |
| Malicious operation injection | Pydantic validation & allowed op whitelist |
| YAML corruption | Round-trip parse check before commit |
| Privilege escalation | Future: role gating, audit log entries |

Audit Entry Example:
```json
{
  "version": 12,
  "timestamp": "2025-09-01T12:44:22Z",
  "author": "user_123",
  "ops": ["add_handoff Planner→Engineer"],
  "pre_checksum": "a1c9..",
  "post_checksum": "bb42..",
  "warnings": []
}
```

---
## 15. Performance Considerations
- Typical graph size small (tens of nodes) → YAML parsing negligible
- Cache last loaded graph + checksum; skip reload if unchanged
- Debounce diff application to reduce write churn
- Future: Switch to memory snapshot plus async flush if edits surge

---
## 16. Failure Modes & Fallbacks
| Failure | User Impact | Fallback |
|---------|-------------|----------|
| Validation error | Edit rejected | Present error list; keep draft |
| Lock timeout | Save delayed | Retry with exponential backoff UI prompt |
| YAML parse error post-write (should not occur) | Reload failure | Automatic rollback to previous version |
| Hot reload exception | Live graph stale | Mark graph as "pending reload" + retry async |

---
## 17. Phased Implementation Plan
| Phase | Deliverables | Est. Effort |
|-------|--------------|-------------|
| 1 | Backend graph loader + GET /graph + basic models + snapshot WS | 0.5–1 day |
| 2 | Diff apply (add/remove agents/edges) + versioning + atomic writes + diff_applied event | 2 days |
| 3 | Validation suite + dry-run endpoint + audit + rollback | 1–1.5 days |
| 4 | Live status overlay (agent state / active edges) | 1 day |
| 5 | UI enhancements: draft mode, monaco diff, warnings panel | 1–2 days |
| 6 | Optional multi-user collaborative (Y.js) | Future |

---
## 18. Testing Strategy
Unit:
- graph_loader: parse + checksum stable
- graph_validator: edge cases (cycle, orphan, invalid condition)
- graph_serializer: atomic write & rollback simulation
- diff apply: sequence of ops produces expected state

Integration:
- Apply diff → hot reload triggers (mock registry)
- Concurrent apply (simulate stale base_version) → rejection path
- Rollback restores YAML content & version decrement

Frontend Testing:
- React Flow change events produce correct op batches
- Optimistic UI revert on server rejection
- WebSocket snapshot resync

Regression Guard:
- Golden YAML fixtures hashed; modifications validated in CI

---
## 19. Logging & Metrics
Add logs (`perf_logger` or new `graph_logger`):
- graph_load(duration, version)
- diff_apply(version_before, version_after, op_count)
- validation_failed(errors_count)
- rollback_performed(target_version)

Metrics (runtime logging + WorkflowStats counters):
- diff_apply_latency
- graph_validation_failures
- concurrent_edit_conflicts

---
## 20. Minimal Example Event Payloads
`snapshot`:
```json
{ "event":"workflow.graph.snapshot", "workflow":"Generator", "version":5, "graph": {"agents":[...], "edges":[...]}, "checksum":"af31c2d9" }
```
`diff_applied`:
```json
{ "event":"workflow.graph.diff_applied", "workflow":"Generator", "from_version":5, "to_version":6, "applied_ops":3 }
```
`rejected`:
```json
{ "event":"workflow.graph.rejected", "workflow":"Generator", "base_version":5, "current_version":6, "errors":["Version mismatch"] }
```

---
## 21. Open Questions / Decisions Needed
| Topic | Options | Recommendation |
|-------|---------|----------------|
| Cycle policy | forbid / warn | Start: forbid (simplify) |
| Agent position persistence | metadata vs ignore | Ignore initially |
| Edge condition grammar | simple tokens / expression | Start with token whitelist |
| Multi-workflow support | one graph module vs per-workflow meta | Single module parameterized by name |
| Auth integration | none / header token / role service | Future role-based guard |

---
## 22. Risk Assessment
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| YAML corruption | Low | High | Round-trip & temp file strategy |
| Race edits | Medium | Medium | Version+checksum guard |
| Over-complex validation early | Medium | Low | Iterative validator layering |
| User confusion on rejections | Medium | Medium | Clear error UI with guidance |
| Library bloat | Low | Low | Limit initial deps to core set |

---
## 23. Rollout Plan
1. Branch creation: `feature/workflow-dag-editor`
2. Phase 1 backend + snapshot endpoint & unit tests
3. Phase 1 frontend read-only graph
4. Internal review → proceed to Phase 2
5. Enable diff apply behind feature flag (env var `ENABLE_GRAPH_EDIT=1`)
6. Add validation & rollback (Phase 3), remove flag after soak
7. Documentation + user guide publishing
8. Optional: integrate CI test gating for YAML schema changes

---
## 24. Maintenance Guidelines
- Keep graph models minimal; extend via metadata dict for optional fields
- Backwards compatibility: ignore unknown fields in YAML
- Defer non-critical ops (rename_agent) until core stable
- Periodically prune history older than N days (configurable)

---
## 25. Summary
This plan introduces a controlled, versioned graph editing layer directly over existing YAML definitions, leveraging MIT-licensed tooling (React Flow + ruamel.yaml) and minimal backend primitives (diff apply, validation, rollback). It preserves AG2 alignment by keeping YAML canonical, avoids translation overhead (e.g., Waldiez schema), and stages complexity to ensure reliability before advanced features.

---
**Next Action (if approved):** Implement Phase 1 backend modules (`graph_models`, `graph_loader`, `graph_endpoints`) and read-only React Flow view.
