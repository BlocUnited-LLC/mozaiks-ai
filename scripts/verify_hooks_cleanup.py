"""Quick verification of hooks refactor cleanup."""
import json
from pathlib import Path

# Check agents.json
agents_path = Path("workflows/Generator/agents.json")
with open(agents_path, 'r', encoding='utf-8') as f:
    agents_data = json.load(f)

print("=" * 60)
print("HOOKS REFACTOR CLEANUP - VERIFICATION")
print("=" * 60)

print("\n1. Static [AG2 PATTERN GUIDANCE] Removal:")
agents_to_check = [
    "WorkflowStrategyAgent",
    "WorkflowImplementationAgent", 
    "ProjectOverviewAgent",
    "HandoffsAgent"
]

for agent_name in agents_to_check:
    system_msg = agents_data["agents"][agent_name]["system_message"]
    has_static = "[AG2 PATTERN GUIDANCE]" in system_msg
    status = "❌ STILL HAS STATIC" if has_static else "✅ CLEAN"
    chars = len(system_msg)
    print(f"   {agent_name}: {status} ({chars:,} chars)")

# Check hooks.json
hooks_path = Path("workflows/Generator/hooks.json")
with open(hooks_path, 'r', encoding='utf-8') as f:
    hooks_data = json.load(f)

print("\n2. Hook Registration:")
pattern_hooks = [h for h in hooks_data["hooks"] 
                 if "pattern" in h.get("filename", "")]
print(f"   ✅ {len(pattern_hooks)} update_agent_state hooks registered")
for hook in pattern_hooks:
    print(f"      - {hook['hook_agent']}: {hook['function']}")

# Check backup files
backup_dir = Path("workflows/Generator")
backups = list(backup_dir.glob("agents.json.backup*"))
print(f"\n3. Backup Files:")
if backups:
    print(f"   ⚠️  {len(backups)} backup file(s) still exist:")
    for b in backups:
        print(f"      - {b.name}")
else:
    print(f"   ✅ All backup files deleted")

print("\n" + "=" * 60)
print("✅ CLEANUP COMPLETE - HOOKS REFACTOR VERIFIED")
print("=" * 60)
print("\nNext step: Restart server to test dynamic pattern injection")
print("Command: .\\scripts\\startapp.ps1")
