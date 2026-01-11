# Prompt Section Architecture

## Overview

MozaiksAI Generator workflow uses a modular prompt architecture where agent prompts are composed from multiple sources:

1. **Agent-Specific Sections** (defined in `agents.json`)
2. **Universal Sections** (injected via hooks at runtime)
3. **Dynamic Sections** (injected based on pattern selection or context)

This architecture reduces duplication, ensures consistency, and allows prompts to evolve independently.

---

## Section Categories

### Agent-Specific Sections (in `agents.json` and generated agents)

These sections are UNIQUE to each agent and define their core identity:

| Section ID | Purpose | Required |
|------------|---------|----------|
| `role` | Agent identity and primary responsibility | Yes |
| `objective` | Key deliverables (2-4 bullets) | Yes |
| `context` | Upstream inputs, position in workflow | Yes |
| `instructions` | Step-by-step execution algorithm | Yes |
| `examples` | Concrete usage examples (runtime agents) | No |
| `output_format` | JSON schema and examples | Yes |

**Note on Generator vs Runtime:**
- **Generator agents** use `pattern_guidance_and_examples` with `{{PATTERN_GUIDANCE_AND_EXAMPLES}}` placeholder for dynamic pattern injection
- **Runtime agents** (generated workflows) use `examples` with static content

**Hook-Injected Sections** (NOT in agents.json, added at runtime):
- Compliance requirements → `hook_universal_prompts.py`
- Agentic best practices → `hook_universal_prompts.py`
- Runtime context → `hook_universal_prompts.py` (design agents only)
- JSON output compliance → `hook_universal_prompts.py` (structured output agents)
- Semantic reference rules → `hook_universal_prompts.py` (cross-referencing agents)
- Validation checklist → `hook_universal_prompts.py` (artifact-producing agents)

### Universal Sections (injected via hooks)

These sections apply to ALL or specific agents and are injected via `update_agent_state` hooks:

| Section | Hook File | Applies To | Content |
|---------|-----------|------------|----------|
| `[COMPLIANCE REQUIREMENTS]` | `hook_universal_prompts.py` | All agents | Legal/output compliance header |
| `[AGENTIC BEST PRACTICES]` | `hook_universal_prompts.py` | All agents | Universal agent behaviors |
| `[MOZAIKS RUNTIME CONTEXT]` | `hook_universal_prompts.py` | All agents | Platform capabilities (what NOT to recreate) |
| `[JSON OUTPUT COMPLIANCE]` | `hook_universal_prompts.py` | Structured output agents | JSON formatting/escaping rules |
| `[SEMANTIC REFERENCE RULES]` | `hook_universal_prompts.py` | Downstream agents | Cross-reference accuracy |
| `[CROSS-REFERENCE VALIDATION]` | `hook_universal_prompts.py` | File generation agents | Pre-emit validation checklist |
| `[FILE GENERATION INSTRUCTIONS]` | `hook_file_generation.py` | UIFileGenerator, AgentToolsFileGenerator | Code quality rules |

### Dynamic Sections (injected based on context)

These sections are injected based on pattern selection or runtime context:

| Section | Hook File | Trigger | Content |
|---------|-----------|---------|---------|
| `[PATTERN GUIDANCE AND EXAMPLES]` | `update_agent_state_pattern.py` | Pattern-specific | Module topology, agent examples |

---

## Hook Execution Order

Hooks execute in the order defined in `hooks.json`:

1. **`hook_universal_prompts.py`** → All universal behavior, compliance, and runtime context (all agents)
2. **Pattern-specific hooks** → Dynamic pattern guidance (specific agents)
3. **`hook_file_generation.py`** → Code generation rules (file generators only)

---

## Prompt Composition Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  agents.json (base prompt sections)                             │
│  ├─ [ROLE]                                                      │
│  ├─ [OBJECTIVE]                                                 │
│  ├─ [CONTEXT]                                                   │
│  ├─ [INSTRUCTIONS]                                              │
│  ├─ [PATTERN GUIDANCE AND EXAMPLES] → {{placeholder}}           │
│  └─ [OUTPUT FORMAT]                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  hook_universal_prompts.py (single consolidated hook)           │
│  ├─ UNIVERSAL (all agents):                                     │
│  │   ├─ [COMPLIANCE REQUIREMENTS]                               │
│  │   ├─ [AGENTIC BEST PRACTICES]                                │
│  │   └─ [MOZAIKS RUNTIME CONTEXT]                               │
│  └─ CONDITIONAL (specific agents):                              │
│      ├─ [JSON OUTPUT COMPLIANCE] (structured output agents)     │
│      ├─ [SEMANTIC REFERENCE RULES] (downstream agents)          │
│      └─ [CROSS-REFERENCE VALIDATION] (file gen agents)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  update_agent_state_pattern.py (dynamic injection)              │
│  └─ Substitutes {{PATTERN_GUIDANCE_AND_EXAMPLES}} → content     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  hook_file_generation.py (file generators only)                 │
│  └─ Appends [FILE GENERATION INSTRUCTIONS]                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Final Composed Prompt (system_message)                         │
│  Ready for AG2 ConversableAgent instantiation                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Placeholder Substitution

The following placeholders in `agents.json` are replaced at runtime:

| Placeholder | Replaced With | Source Hook |
|-------------|---------------|-------------|
| `{{PATTERN_GUIDANCE_AND_EXAMPLES}}` | Pattern-specific guidance | `update_agent_state_pattern.py` |

---

## Benefits of This Architecture

1. **Reduced Duplication**: Universal rules defined once, injected everywhere
2. **Consistent Behavior**: All agents follow same agentic best practices
3. **Easy Maintenance**: Update one hook file to fix all agents
4. **Separation of Concerns**:
   - `agents.json` = WHAT agent does (identity, logic)
   - Hooks = HOW agent behaves (compliance, practices, runtime awareness)
5. **Hot-Swappable**: Change hooks without editing agent definitions
6. **Testable**: Each hook can be tested independently
7. **Prevents Reinventing the Wheel**: Runtime context tells agents what platform already provides
8. **Minimal Files**: Single consolidated `hook_universal_prompts.py` handles all universal/shared sections

---

## Runtime Context: What the Platform Provides

The `[MOZAIKS RUNTIME CONTEXT]` section (in `hook_universal_prompts.py`) injects awareness of MozaiksAI platform capabilities so Generator agents don't design workflows that recreate them:

| Capability | Handled By | Agents Should NOT Create |
|------------|------------|-------------------------|
| Chat Transport | `core/transport/websocket.py` + ChatUI | UserProxy agents, message transport |
| Persistence | `AG2PersistenceManager` | Database schemas, history tracking |
| Token Tracking | `MozaiksPay` (core/tokens) | Usage analytics, cost attribution |
| Multi-Tenant Isolation | Runtime enforcement | Tenant validation, scoped queries |
| Observability | `core/observability` | Logging infrastructure, metrics |
| UI Component Delivery | ChatUI artifacts | React components, form state |
| Event System | `core/events` | Pub/sub, event dispatching |

This prevents common anti-patterns like creating "ChatAgent", "PersistenceAgent", or "TokenTracker" agents.

---

## File Locations

```
workflows/Generator/
├── agents.json                          # Agent-specific sections
├── hooks.json                           # Hook registration
└── tools/
    ├── hook_universal_prompts.py        # ALL universal/shared sections (consolidated)
    ├── hook_file_generation.py          # Code generation rules
    └── update_agent_state_pattern.py    # Dynamic pattern guidance
```
