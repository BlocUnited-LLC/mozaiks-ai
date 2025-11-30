"""
Script to add auto_invoke field guidance to ToolsManagerAgent system message.
"""
import json
from pathlib import Path

AUTO_INVOKE_GUIDANCE = """
[AUTO_INVOKE FIELD]
The `auto_invoke` field controls whether a tool is automatically invoked when an agent produces structured output.

**Default Behavior (when auto_invoke is not specified):**
- UI_Tool: `auto_invoke = true` (auto-invoked by default)
- Agent_Tool: `auto_invoke = false` (NOT auto-invoked by default)

**When to Set Explicitly:**
Set `auto_invoke: true` for Agent_Tools that MUST execute immediately after structured output to:
1. Cache structured output in context_variables for downstream agents
2. Perform side effects that downstream agents depend on
3. Trigger follow-up operations that can't be delayed

**When to Set Explicitly:**
Set `auto_invoke: false` for UI_Tools that should NOT auto-invoke (rare):
1. Tools that require explicit user interaction timing
2. Tools that should only execute on manual trigger

**Examples:**

1. **Agent_Tool with auto_invoke=true** (Pattern Selection):
```json
{
  "agent": "PatternAgent",
  "file": "pattern_selection.py",
  "function": "pattern_selection",
  "tool_type": "Agent_Tool",
  "auto_invoke": true,  // ← OVERRIDE default (Agent_Tools don't auto-invoke by default)
  "ui": {"component": null, "mode": null}
}
```
Why: PatternAgent's selection must be stored in context BEFORE lifecycle tool runs to inject pattern guidance.

2. **Agent_Tool with auto_invoke=true** (Workflow Strategy Caching):
```json
{
  "agent": "WorkflowStrategyAgent",
  "file": "workflow_strategy.py",
  "function": "workflow_strategy",
  "tool_type": "Agent_Tool",
  "auto_invoke": true,  // ← OVERRIDE default
  "ui": {"component": null, "mode": null}
}
```
Why: Strategy must be cached in context for WorkflowImplementationAgent to read modules.

3. **UI_Tool with default auto_invoke** (no explicit field needed):
```json
{
  "agent": "WorkflowImplementationAgent",
  "file": "module_agents_plan.py",
  "function": "module_agents_plan",
  "tool_type": "UI_Tool",
  // auto_invoke not specified → defaults to true for UI_Tool
  "ui": {"component": "ActionPlan", "mode": "artifact"}
}
```
Why: UI_Tools auto-invoke by default to render UI components immediately.

**Decision Tree:**
- Agent produces structured output → Runtime emits structured_output_ready event
- Is auto_invoke=true? (explicit) → Tool executes immediately
- Is auto_invoke=false? (explicit) → Tool does NOT execute
- Is auto_invoke unspecified?
  - tool_type=UI_Tool → Tool executes immediately (default true)
  - tool_type=Agent_Tool → Tool does NOT execute (default false)

**CRITICAL RULES:**
1. If an Agent_Tool needs to cache context for downstream agents, set `auto_invoke: true`
2. If an Agent_Tool performs side effects that must happen immediately, set `auto_invoke: true`
3. If a UI_Tool should NOT auto-invoke, set `auto_invoke: false` (rare)
4. For most tools, omit auto_invoke and use defaults (true for UI_Tool, false for Agent_Tool)

**Output Format:**
Include `auto_invoke` field (bool or null) in every ToolSpec entry:
- null: Use default behavior (true for UI_Tool, false for Agent_Tool)
- true: Force auto-invocation regardless of tool_type
- false: Prevent auto-invocation regardless of tool_type
"""

def main():
    """Add auto_invoke guidance to ToolsManagerAgent system message."""
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    agents_json_path = project_root / "workflows" / "Generator" / "agents.json"

    if not agents_json_path.exists():
        print(f"Error: agents.json not found at {agents_json_path}")
        return

    print(f"Reading agents.json from: {agents_json_path}")

    # Load agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)

    if "ToolsManagerAgent" not in agents_data['agents']:
        print("Error: ToolsManagerAgent not found in agents.json")
        return

    agent = agents_data['agents']['ToolsManagerAgent']
    current_message = agent['system_message']

    print(f"\nUpdating ToolsManagerAgent...")
    print(f"  Current message length: {len(current_message)} chars")

    # Check if auto_invoke guidance already exists
    if "[AUTO_INVOKE FIELD]" in current_message:
        print(f"  Auto_invoke guidance already exists, skipping")
        return

    # Find a good insertion point - right before [OUTPUT FORMAT] section
    if "[OUTPUT FORMAT]" in current_message:
        parts = current_message.split("[OUTPUT FORMAT]", 1)
        new_message = parts[0] + AUTO_INVOKE_GUIDANCE + "\n[OUTPUT FORMAT]" + parts[1]
    else:
        # Fallback: add at end
        new_message = current_message + "\n\n" + AUTO_INVOKE_GUIDANCE

    agent['system_message'] = new_message

    print(f"  New message length: {len(new_message)} chars")
    print(f"  [OK] Auto_invoke guidance added")

    # Create backup
    backup_path = agents_json_path.with_suffix('.json.backup4')
    print(f"\nCreating backup at: {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    # Write updated agents.json
    print(f"Writing updated agents.json...")
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    print("\n[OK] ToolsManagerAgent updated with auto_invoke guidance!")


if __name__ == "__main__":
    main()
