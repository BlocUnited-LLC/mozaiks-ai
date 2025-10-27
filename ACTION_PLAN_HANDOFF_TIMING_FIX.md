# Action Plan Approval Handoff Timing Fix

**Date**: 2025-01-13  
**Status**: ✅ Fixed  
**File**: `workflows/Generator/handoffs.json`

---

## Problem

After user approves the ActionPlan, the workflow was reverting to user instead of continuing to ContextVariablesAgent.

### Root Cause

**Handoff evaluation timing issue with auto-tool agents:**

1. **ProjectOverviewAgent** outputs structured JSON (MermaidSequenceDiagramCall)
2. **Handoff rules are evaluated IMMEDIATELY** → `action_plan_acceptance` = "pending" (default)
3. **Auto-tool handler intercepts** and calls `mermaid_sequence_diagram` tool
4. **Tool displays ActionPlan UI** and waits for user response
5. **User approves** → tool sets `action_plan_acceptance = "accepted"`  
6. ❌ **But handoff already evaluated to False!** → Reverts to user

### Log Evidence

```log
02:25:10.074 [HANDOFFS][EVAL] source=ProjectOverviewAgent target=ContextVariablesAgent 
expr='${action_plan_acceptance} == "accepted"' 
vars={'action_plan_acceptance': 'pending'} -> False
```

This happens **BEFORE** the mermaid tool completes and sets the variable.

---

## Solution

Changed the handoff from **conditional** (evaluated during agent output) to **after_work with condition** (evaluated after tool completes).

### Before

```json
{
  "source_agent": "ProjectOverviewAgent",
  "target_agent": "user",
  "handoff_type": "after_work",
  "condition": null,
  "transition_target": "RevertToUserTarget"
},
{
  "source_agent": "ProjectOverviewAgent",
  "target_agent": "ContextVariablesAgent",
  "handoff_type": "condition",                    ← Evaluated BEFORE tool completes
  "condition_type": "expression",
  "condition": "${action_plan_acceptance} == \"accepted\"",
  "transition_target": "AgentTarget"
}
```

**Problem**: Conditional handoffs are evaluated when agent speaks, not when tool completes.

### After

```json
{
  "source_agent": "ProjectOverviewAgent",
  "target_agent": "ContextVariablesAgent",
  "handoff_type": "after_work",                   ← Evaluated AFTER tool completes ✅
  "condition_type": "expression",
  "condition": "${action_plan_acceptance} == \"accepted\"",
  "transition_target": "AgentTarget"
},
{
  "source_agent": "ProjectOverviewAgent",
  "target_agent": "user",
  "handoff_type": "after_work",
  "condition": null,
  "transition_target": "RevertToUserTarget"
}
```

**Solution**: `after_work` handoff with condition evaluates AFTER the auto-tool completes, ensuring `action_plan_acceptance` has been updated.

---

## How It Works Now

### Execution Flow

1. **ProjectOverviewAgent** outputs MermaidSequenceDiagramCall JSON
2. **Auto-tool handler** intercepts and calls `mermaid_sequence_diagram` tool
3. **Tool shows ActionPlan UI** and waits for approval
4. **User clicks "Approve"** → sends `{action: "accept_workflow", plan_acceptance: true}`
5. **Tool receives response** and sets `context_variables.set("action_plan_acceptance", "accepted")`
6. **Tool completes** and returns
7. ✅ **After-work handoffs are evaluated** → Condition checks `action_plan_acceptance == "accepted"` → **True!**
8. **Workflow continues** to ContextVariablesAgent

### Handoff Evaluation Order

**After-work handoffs are evaluated in order:**

1. **First**: `ProjectOverviewAgent` → `ContextVariablesAgent` (with condition)
   - Check: `${action_plan_acceptance} == "accepted"` → **True**
   - **Match!** → Hand off to ContextVariablesAgent ✅

2. **Second**: `ProjectOverviewAgent` → `user` (no condition)
   - Only evaluated if first handoff didn't match
   - Acts as fallback

---

## Key Insight

**Auto-tool agents need after-work handoffs, not conditional handoffs**, when the decision depends on tool execution results.

### Rule of Thumb

- **Use `condition` handoff**: When decision is based on agent's TEXT output or pre-existing context
- **Use `after_work` with `condition`**: When decision depends on TOOL results (especially for auto-tool agents)

### Why This Matters

Auto-tool agents have this flow:
```
Agent speaks → Handoffs evaluated → Tool auto-invoked → Tool completes
```

If handoff checks a variable **set by the tool**, it must use `after_work` to wait for tool completion.

---

## Testing

### Before Fix
1. User approves ActionPlan
2. Workflow reverts to user (waiting for next input)
3. User has to manually trigger continuation

### After Fix
1. User approves ActionPlan  
2. Workflow automatically continues to ContextVariablesAgent ✅
3. No user intervention required

### Verification
```bash
# Check logs after approval
grep "action_plan_acceptance" logs/logs/mozaiks.log

# Expected: Should see "accepted" value
# Then: Should see handoff to ContextVariablesAgent evaluate to True
```

---

## Related Patterns

This same pattern applies to any auto-tool agent where:
- Agent outputs structured JSON
- Auto-tool handler invokes tool
- Tool sets context variables
- Next agent depends on those variables

**Examples**:
- ActionPlanArchitect → approval → next agent
- API key collection → validation → next agent  
- User input collection → processing → next agent

**Solution**: Always use `after_work` handoff with condition for these cases.

---

**Status**: ✅ Fixed and tested  
**Impact**: Workflow now continues automatically after ActionPlan approval

