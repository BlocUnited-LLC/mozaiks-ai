"""
Add Python import constraint teaching to file generator agents.

This script updates UIFileGenerator, AgentToolsFileGenerator, and HookAgent
to teach them about the critical import constraint for dynamically loaded tools:
- Relative imports DON'T work (module isn't part of a package)
- Absolute imports with sys.path manipulation DO work

Context: module_agents_plan.py import error revealed this gap in agent knowledge.
"""

import json
from pathlib import Path

AGENTS_FILE = Path("workflows/Generator/agents.json")

IMPORT_CONSTRAINT_SECTION = """
[PYTHON IMPORT CONSTRAINTS] (CRITICAL - DYNAMIC TOOL LOADING)
When tools are dynamically loaded by the runtime, relative imports don't work because the module isn't being imported as part of a package.

CORRECT PATTERN (Absolute import with sys.path):
```python
import sys
from pathlib import Path
_tools_dir = Path(__file__).parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))
from action_plan import action_plan  # Absolute import
```

WRONG PATTERN (will fail at runtime):
```python
from .action_plan import action_plan  # Relative import - BREAKS
```

WHY: The runtime loads tools dynamically from workflows/{workflow}/tools/ directory. Python's dynamic import system doesn't recognize these as packages, so relative imports fail with "attempted relative import with no known parent package". Always use absolute imports with sys.path manipulation when tools need to import other tools.
"""

TARGET_AGENTS = [
    "UIFileGenerator",
    "AgentToolsFileGenerator", 
    "HookAgent"
]

def add_import_constraint_teaching():
    """Add import constraint section after [RUNTIME PYTHON PRIMITIVE] or [OBJECTIVE] section."""
    
    with open(AGENTS_FILE, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)
    
    for agent_name in TARGET_AGENTS:
        if agent_name not in agents_data['agents']:
            print(f"⚠️  Agent {agent_name} not found, skipping")
            continue
        
        system_message = agents_data['agents'][agent_name]['system_message']
        
        # Check if already present
        if "PYTHON IMPORT CONSTRAINTS" in system_message:
            print(f"✅ {agent_name} already has import constraint teaching")
            continue
        
        # Find insertion point (after [RUNTIME PYTHON PRIMITIVE] or [OBJECTIVE])
        if "[RUNTIME PYTHON PRIMITIVE]" in system_message:
            # For UIFileGenerator - insert after [RUNTIME PYTHON PRIMITIVE] section
            insertion_marker = "\n\n[UI EVENT CONTRACT]"
            if insertion_marker in system_message:
                system_message = system_message.replace(
                    insertion_marker,
                    IMPORT_CONSTRAINT_SECTION + insertion_marker
                )
            else:
                print(f"⚠️  Could not find insertion point in {agent_name}")
                continue
        elif "[OBJECTIVE]" in system_message:
            # For AgentToolsFileGenerator and HookAgent - insert after [OBJECTIVE] section
            insertion_marker = "\n\n[CONTEXT]"
            if insertion_marker in system_message:
                system_message = system_message.replace(
                    insertion_marker,
                    IMPORT_CONSTRAINT_SECTION + insertion_marker
                )
            else:
                print(f"⚠️  Could not find insertion point in {agent_name}")
                continue
        else:
            print(f"⚠️  Could not find suitable insertion point in {agent_name}")
            continue
        
        # Update agent
        agents_data['agents'][agent_name]['system_message'] = system_message
        print(f"✅ Updated {agent_name} with import constraint teaching")
    
    # Write back
    with open(AGENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Updated {AGENTS_FILE}")

if __name__ == "__main__":
    add_import_constraint_teaching()
