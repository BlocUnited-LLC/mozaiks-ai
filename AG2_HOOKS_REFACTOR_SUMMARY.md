# AG2 Hooks Refactor - Pattern Guidance Injection

## Critical Fix: Using AG2's Native Hook System ✅

### The Problem We Fixed

**What We Built Initially (WRONG):**
```json
// tools.json - lifecycle_tools
{
  "trigger": "after_agent",
  "agent": "PatternAgent",
  "file": "inject_pattern_guidance.py",
  "function": "inject_pattern_guidance"
}
```

**Why It Was Wrong:**
- ❌ Used MozaiksAI's lifecycle_tools (custom layer)
- ❌ Only stored data in `context_variables`
- ❌ Agents had to manually read from context (error-prone)
- ❌ Not using AG2's native hook system
- ❌ Pattern guidance wasn't injected into system messages

---

### The Correct Approach (AG2 Hooks)

**What We Built Now (CORRECT):**
```json
// hooks.json - AG2 native hooks
{
  "hook_type": "update_agent_state",
  "hook_agent": "WorkflowStrategyAgent",
  "filename": "update_agent_state_pattern.py",
  "function": "inject_workflow_strategy_guidance"
}
```

**Why This Is Correct:**
- ✅ Uses AG2's native `update_agent_state` hook
- ✅ Dynamically modifies `agent.system_message` at runtime
- ✅ Runs BEFORE agent processes messages
- ✅ Pattern guidance is automatically injected (no manual reading needed)
- ✅ Proper integration with AG2's hook system

---

## How AG2 Hooks Work

### Hook Signature
```python
def hook_function(agent, messages: List[Dict[str, Any]]) -> None:
    """
    AG2 update_agent_state hook signature.

    Args:
        agent: The ConversableAgent instance (can modify in-place)
        messages: List of messages the agent will process

    Returns:
        None (modifies agent in-place)
    """
    # Modify agent.system_message, agent.llm_config, etc.
    agent.system_message += "\n\n[INJECTED GUIDANCE]\n..."
```

### When It Runs
```
User Message
    ↓
PatternAgent selects pattern
    ↓
pattern_selection tool stores in context_variables
    ↓
WorkflowStrategyAgent turn begins
    ↓
🔥 update_agent_state HOOK RUNS HERE 🔥
    ↓
    - Reads PatternSelection from agent.context_variables
    - Loads pattern taxonomy
    - Injects guidance into agent.system_message
    ↓
WorkflowStrategyAgent processes messages WITH pattern guidance
```

---

## What We Built

### 1. Hook File
**File:** [workflows/Generator/tools/update_agent_state_pattern.py](workflows/Generator/tools/update_agent_state_pattern.py:1:0-1:0)

**Contains 4 hook functions:**
1. `inject_workflow_strategy_guidance()` - For WorkflowStrategyAgent
2. `inject_workflow_implementation_guidance()` - For WorkflowImplementationAgent
3. `inject_project_overview_guidance()` - For ProjectOverviewAgent
4. `inject_handoffs_guidance()` - For HandoffsAgent

**Each hook:**
- Extracts `PatternSelection` from `agent.context_variables`
- Loads `ag2_pattern_taxonomy.json`
- Finds the selected pattern by ID
- Builds pattern-specific guidance
- Injects into `agent.system_message`

### 2. Hook Registration
**File:** [workflows/Generator/hooks.json](workflows/Generator/hooks.json:15:39)

```json
{
  "hooks": [
    {
      "hook_type": "update_agent_state",
      "hook_agent": "WorkflowStrategyAgent",
      "filename": "update_agent_state_pattern.py",
      "function": "inject_workflow_strategy_guidance"
    },
    {
      "hook_type": "update_agent_state",
      "hook_agent": "WorkflowImplementationAgent",
      "filename": "update_agent_state_pattern.py",
      "function": "inject_workflow_implementation_guidance"
    },
    {
      "hook_type": "update_agent_state",
      "hook_agent": "ProjectOverviewAgent",
      "filename": "update_agent_state_pattern.py",
      "function": "inject_project_overview_guidance"
    },
    {
      "hook_type": "update_agent_state",
      "hook_agent": "HandoffsAgent",
      "filename": "update_agent_state_pattern.py",
      "function": "inject_handoffs_guidance"
    }
  ]
}
```

### 3. Removed Old Approach
**File:** [workflows/Generator/tools.json](workflows/Generator/tools.json:62:75)

Removed the lifecycle_tool entry for `inject_pattern_guidance`.

---

## Example: How It Works At Runtime

### Pipeline Pattern Example

**User Input:**
> "I need a workflow with sequential data processing stages"

**Execution Flow:**

1. **PatternAgent runs:**
   ```json
   {
     "selected_pattern": 6,
     "pattern_name": "Pipeline",
     "rationale": "Sequential processing with stage dependencies"
   }
   ```

2. **pattern_selection tool (auto-invoked):**
   ```python
   context_variables.data['PatternSelection'] = {
     "selected_pattern": 6,
     "pattern_name": "Pipeline",
     ...
   }
   ```

3. **WorkflowStrategyAgent turn begins:**
   ```python
   # 🔥 update_agent_state HOOK RUNS
   def inject_workflow_strategy_guidance(agent, messages):
       pattern = _get_pattern_from_context(agent)  # Pattern 6: Pipeline

       guidance = """
       [INJECTED PATTERN GUIDANCE - Pipeline]
       The PatternAgent has selected the **Pipeline** orchestration pattern.
       CRITICAL: Your phase design MUST align with this pattern's structure.

       **Phase Structure Recommendations:**
       Strict sequential handoff between stages

       **Recommended Phases:**
       1. **Input Phase** - Purpose: Validate and prepare input
       2. **Processing Stages** - Purpose: Sequential transformation stages
       3. **Output Phase** - Purpose: Finalize and deliver output

       **Pattern Characteristics:**
       - Unidirectional flow
       - Sequential processing stages
       - Progressive transformation
       - Clear stage boundaries
       """

       agent.system_message += guidance  # ✅ Injected into agent!
   ```

4. **WorkflowStrategyAgent processes messages:**
   - Agent's system message NOW contains pattern guidance
   - Agent designs phases aligned with Pipeline pattern
   - No need to manually check context_variables

5. **Same process repeats for:**
   - WorkflowImplementationAgent (gets agent coordination guidance)
   - ProjectOverviewAgent (gets mermaid diagram guidance)
   - HandoffsAgent (gets handoff rules guidance)

---

## Key Benefits

### Before (Lifecycle Tools)
```python
# Agent had to manually check context
def workflow_strategy(*, context_variables=None):
    guidance = context_variables.data.get('pattern_guidance', {})
    strategy_guidance = guidance.get('workflow_strategy', '')
    # ❌ Easy to forget
    # ❌ Inconsistent access
    # ❌ Not in system message
```

### After (AG2 Hooks)
```python
# Pattern guidance automatically in system message
def inject_workflow_strategy_guidance(agent, messages):
    agent.system_message += pattern_guidance
    # ✅ Always injected
    # ✅ Consistent
    # ✅ Part of system message
    # ✅ Agent sees it automatically
```

---

## Files Modified

### Created
- `workflows/Generator/tools/update_agent_state_pattern.py` (4 hook functions)

### Modified
- `workflows/Generator/hooks.json` (+4 hook entries)
- `workflows/Generator/tools.json` (removed lifecycle_tool entry)

### Deprecated
- `workflows/Generator/tools/inject_pattern_guidance.py` (old lifecycle tool approach)

---

## Testing Checklist

### Test 1: Verify Hooks Are Loaded
```bash
# Check logs for hook registration
grep "Loading hooks for workflow 'Generator'" logs/logs/mozaiks.log
grep "update_agent_state" logs/logs/mozaiks.log
```

Expected: 4 `update_agent_state` hooks registered for WorkflowStrategyAgent, WorkflowImplementationAgent, ProjectOverviewAgent, HandoffsAgent

### Test 2: Verify Pattern Guidance Injection
```bash
# Check logs for guidance injection
grep "Injected.*chars of pattern guidance" logs/logs/mozaiks.log
```

Expected:
```
✓ Injected 1234 chars of pattern guidance into WorkflowStrategyAgent
✓ Injected 1234 chars of pattern guidance into WorkflowImplementationAgent
✓ Injected 1234 chars of pattern guidance into ProjectOverviewAgent
✓ Injected 1234 chars of pattern guidance into HandoffsAgent
```

### Test 3: Verify Pattern Alignment
Run workflow and check that:
- ✅ WorkflowStrategyAgent phases match pattern structure
- ✅ WorkflowImplementationAgent agents match pattern coordination
- ✅ ProjectOverviewAgent diagram matches pattern visual structure
- ✅ HandoffsAgent handoffs match pattern communication flow

---

## Common Issues & Fixes

### Issue 1: Hook Not Running
**Symptom:** No "Injected...chars" logs

**Possible Causes:**
1. Hook not registered in hooks.json
2. Agent name mismatch (case-sensitive!)
3. Hook file not in tools/ directory

**Fix:** Verify hooks.json entries and file location

### Issue 2: Pattern Not Found
**Symptom:** "No pattern available for {agent}, skipping guidance injection"

**Possible Causes:**
1. PatternAgent didn't run
2. pattern_selection tool didn't execute
3. PatternSelection not in context_variables

**Fix:**
- Verify PatternAgent is in agent sequence
- Verify pattern_selection tool has `auto_invoke: true`
- Check logs for pattern_selection execution

### Issue 3: Context Access Error
**Symptom:** "Agent has no context_variables attribute"

**Possible Causes:**
1. Hook running at wrong time
2. Context not initialized yet

**Fix:** Verify hook_type is `update_agent_state` (not another hook type)

---

## Migration Notes

### What Changed
- **Old:** Lifecycle tools (MozaiksAI custom layer)
- **New:** AG2 hooks (native AG2 integration)

### Breaking Changes
- None for existing workflows (PatternAgent not yet in production)

### Backward Compatibility
- Old `inject_pattern_guidance.py` file can be removed
- No changes needed to agent system messages

---

## Next Steps

1. **Restart server** to load hooks:
   ```powershell
   .\scripts\startapp.ps1
   ```

2. **Test with clear pattern request:**
   ```
   "I need a workflow with sequential data processing stages:
   validate input → extract data → transform data → generate report"

   Expected: Pipeline pattern → sequential handoffs
   ```

3. **Verify in logs:**
   ```bash
   # Pattern selection
   grep "✓ Pattern selected" logs/logs/mozaiks.log

   # Hook execution
   grep "Injected.*pattern guidance" logs/logs/mozaiks.log

   # Agent alignment
   # Check that phases/agents/handoffs match selected pattern
   ```

---

## Documentation

**AG2 Hooks Reference:** https://docs.ag2.ai/latest/docs/contributor-guide/how-ag2-works/hooks/

**Hook Types:**
- `process_message_before_send` - Modify messages before sending
- `update_agent_state` - Modify agent state before processing ✅ (We use this)
- `process_last_received_message` - Modify received messages
- `process_all_messages_before_reply` - Modify all messages before reply

---

## Summary

✅ **Fixed:** Converted from lifecycle tools to AG2 native hooks
✅ **Proper Integration:** Using `update_agent_state` hook
✅ **Dynamic Injection:** Pattern guidance injected into system messages
✅ **No Manual Access:** Agents automatically receive guidance

**Status:** Complete, Ready for Testing
**Restart Required:** Yes (`.\scripts\startapp.ps1`)

