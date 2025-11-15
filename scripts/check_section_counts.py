"""Check section counts for all agents."""
import json
from pathlib import Path

agents_path = Path(__file__).parent.parent / "workflows" / "Generator" / "agents.json"

with open(agents_path, "r", encoding="utf-8") as f:
    data = json.load(f)

agents = data["agents"]

print("\nAgent Section Counts:")
print("=" * 60)
for name, agent in agents.items():
    section_count = len(agent["prompt_sections"])
    section_headings = [s.get("heading", "NO HEADING") for s in agent["prompt_sections"]]
    print(f"{name}: {section_count} sections")
    print(f"  Headings: {', '.join(section_headings)}")
    print()
