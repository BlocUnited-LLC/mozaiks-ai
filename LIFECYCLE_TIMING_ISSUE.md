# Lifecycle Tool Timing Issue - Generator Workflow

## Issue Summary
**Date:** 2025-10-14  
**Workflow:** Generator  
**Problem:** Workflow sequence confusion after action plan approval causes premature lifecycle trigger and empty TextEvent injection

## Root Cause

### The Problem Chain
1. User approves action plan in Mermaid diagram UI (00:27:39.143)
2. **Mermaid tool (`mermaid_sequence_diagram.py` line 496-504) manually triggers `before_agent` lifecycle for `ContextVariablesAgent`**
3. This triggers API key collection lifecycle tool (`collect_api_keys_from_action_plan`)
4. API keys collected successfully (00:27:39.146)
5. **Empty TextEvent injected** (00:27:39.443): `content='' sender='user' recipient='chat_manager'`
6. Empty TextEvent causes Mermaid lifecycle log to fire again (00:27:39.444)
7. Workflow confused about where it is in sequence
8. Hook signature TypeError occurs when trying to continue (already fixed)
9. System re-displays action plan instead of proceeding to ContextVariablesAgent

### Log Evidence
```
00:27:39.143 [ INFO] ✅ [INPUT] Respond callback invoked
00:27:39.145 [ INFO] [API_KEYS] Resumed workflow after API key collection
00:27:39.146 [ INFO] [LIFECYCLE] ✓ collect_api_keys_from_action_plan completed in 15.111s
00:27:39.443 [ INFO] [EVENT_TRACE] TextEvent from None: content_len=99 preview='uuid=UUID('0f79***') content='' sender='user' recipient='chat_manager'...'
00:27:39.444 [ INFO] [MERMAID] Triggered before_agent lifecycle for ContextVariablesAgent after plan acceptance
00:27:39.445 [ INFO] [AUTO_TOOL] Emitting chat.tool_response for agent=ProjectOverviewAgent tool=mermaid_sequence_diagram
```

## Technical Analysis

### Current Implementation
**File:** `workflows/Generator/tools/mermaid_sequence_diagram.py` (lines 481-509)

```python
lifecycle_triggered = False
if acceptance_state == "accepted" and context_variables and hasattr(context_variables, "get"):
    try:
        already_complete = bool(context_variables.get("api_keys_collection_complete"))
    except Exception:
        already_complete = False
    if not already_complete:
        try:
            from core.workflow.lifecycle_tools import get_lifecycle_manager
            lifecycle_manager = get_lifecycle_manager(lifecycle_workflow_name or "Generator")
            await lifecycle_manager.trigger_before_agent(
                agent_name="ContextVariablesAgent",
                context_variables=context_variables,
            )
            lifecycle_triggered = True
```

### Why This Is Problematic

1. **Violates Separation of Concerns:**
   - UI tools should handle user interaction and return data
   - Lifecycle orchestration should be managed by the workflow runtime
   - Mixing these responsibilities creates timing dependencies

2. **Creates Race Conditions:**
   - Manual trigger happens during UI tool response processing
   - Runtime may also trigger lifecycle naturally during workflow progression
   - Empty TextEvent suggests event queue confusion

3. **Breaks Workflow State Machine:**
   - Agent handoffs should progress through orchestration layer
   - Manual triggers bypass normal flow control
   - Context variables may be in inconsistent state during transition

4. **Causes Event Sequencing Issues:**
   - Empty TextEvent appears after lifecycle trigger
   - Mermaid tool response emitted out of sequence
   - ActionPlan re-displayed instead of proceeding forward

## Recommended Solution

### Option 1: Remove Manual Lifecycle Trigger (Preferred)

**Rationale:** The workflow orchestration should naturally trigger `before_agent` lifecycle when ContextVariablesAgent's turn begins. The manual trigger is redundant and causes timing issues.

**Implementation:**
1. Remove the lifecycle trigger code from `mermaid_sequence_diagram.py` (lines 481-509)
2. Rely on handoff rules to progress from ProjectOverviewAgent → ContextVariablesAgent
3. The `before_agent` lifecycle hook will fire automatically when ContextVariablesAgent starts

**Verification:**
- Check `workflows/Generator/handoffs.json` for handoff rule from ProjectOverviewAgent to ContextVariablesAgent
- Ensure rule condition checks `action_plan_acceptance == "accepted"`
- The lifecycle hook in `tools.json` will auto-fire when agent starts

**File:** `workflows/Generator/tools.json` (line 50-61)
```json
{
  "trigger": "before_agent",
  "agent": "ContextVariablesAgent",
  "file": "collect_api_keys.py",
  "function": "collect_api_keys_from_action_plan",
  "description": "Collect API keys for third-party services before context variable planning"
}
```

### Option 2: Make Trigger Async and Deferred

If manual trigger is truly necessary (unlikely), defer it:

```python
# Instead of awaiting immediately:
lifecycle_triggered = False
if acceptance_state == "accepted":
    # Set flag for runtime to handle
    try:
        context_variables.set("trigger_api_key_collection", True)
        lifecycle_triggered = True
    except Exception:
        pass
```

Then have orchestration layer check this flag and trigger appropriately.

**Problem:** This is more complex and still mixes concerns. Not recommended.

### Option 3: Move to Handoff Condition

Better approach if control is needed:

**File:** `workflows/Generator/handoffs.json`
```json
{
  "source_agent": "ProjectOverviewAgent",
  "target_agent": "ContextVariablesAgent",
  "handoff_type": "condition",
  "condition": "${action_plan_acceptance} == 'accepted'",
  "condition_type": "expression",
  "transition_target": "AgentTarget"
}
```

The `before_agent` lifecycle will fire automatically when ContextVariablesAgent starts.

## Impact Assessment

### Current Behavior (Broken)
1. User approves plan
2. Mermaid tool manually triggers lifecycle
3. API keys collected
4. **Empty TextEvent causes confusion**
5. **Workflow gets stuck or re-displays action plan**
6. ContextVariablesAgent never starts properly

### Expected Behavior (After Fix)
1. User approves plan
2. Mermaid tool returns acceptance state
3. **Handoff rule triggers: ProjectOverviewAgent → ContextVariablesAgent**
4. **Before ContextVariablesAgent starts, lifecycle hook auto-fires**
5. API keys collected
6. **ContextVariablesAgent proceeds with structured output**
7. Workflow continues to next phase

## Testing Required

### Test Case 1: Action Plan Acceptance Flow
1. Start Generator workflow
2. Approve action plan
3. **Verify:** No empty TextEvent in logs
4. **Verify:** Lifecycle hook fires once (not twice)
5. **Verify:** API keys collected
6. **Verify:** ContextVariablesAgent receives control
7. **Verify:** No action plan re-display

### Test Case 2: Lifecycle Hook Deduplication
1. Check `already_complete` flag works correctly
2. Verify lifecycle doesn't fire twice
3. Confirm no race conditions

### Test Case 3: Agent Progression
1. Verify handoff condition evaluates correctly
2. Confirm ContextVariablesAgent starts after approval
3. Validate structured output emitted properly

## Files to Modify

### Primary Fix:
- **workflows/Generator/tools/mermaid_sequence_diagram.py**
  - Remove lines 481-509 (manual lifecycle trigger)
  - Rely on orchestration to trigger ContextVariablesAgent

### Verify These Files:
- **workflows/Generator/handoffs.json**
  - Ensure handoff rule exists: ProjectOverviewAgent → ContextVariablesAgent
  - Condition should be: `${action_plan_acceptance} == "accepted"`

- **workflows/Generator/tools.json**
  - Lifecycle hook already correctly configured (line 50-61)
  - No changes needed

## Risk Assessment

### Low Risk (Recommended):
Remove manual trigger and rely on orchestration

**Why Safe:**
- Lifecycle hook already exists in tools.json
- Handoff rules should naturally progress workflow
- Separation of concerns improves reliability

### Medium Risk:
Keep manual trigger but add guards

**Concerns:**
- Timing dependencies remain
- Event sequencing still fragile
- Harder to debug and maintain

## Next Steps

1. **Verify handoff configuration** - Check that ProjectOverviewAgent → ContextVariablesAgent handoff exists
2. **Remove manual lifecycle trigger** - Delete problematic code from mermaid_sequence_diagram.py
3. **Test workflow progression** - Verify ContextVariablesAgent starts correctly
4. **Validate API key collection** - Confirm lifecycle hook fires once at correct time
5. **Monitor logs** - Ensure no empty TextEvents or duplicate lifecycle triggers

## Related Issues
- HOOK_SIGNATURE_FIX.md - Hook signature TypeError (already fixed)
- This lifecycle timing issue was the underlying cause of the workflow confusion
