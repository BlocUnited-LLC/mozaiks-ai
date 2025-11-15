"""Utility to migrate Generator agent system messages into structured sections.

This script rewrites workflows/Generator/agents.json so that each agent's
monolithic system_message string becomes a list of ordered prompt sections.
The runtime will re-compose these sections at agent construction time.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Dict, List

RE_AGENTS_JSON = Path("workflows") / "Generator" / "agents.json"
SECTION_PATTERN = re.compile(r"^\[(.+?)\]", re.MULTILINE)


def _heading_to_id(heading: str, *, index: int | None = None) -> str:
    """Convert a heading like "[OUTPUT FORMAT]" to snake_case identifier."""
    text = heading.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.replace("/", " or ")
    text = re.sub(r"[^0-9A-Za-z]+", "_", text)
    text = text.strip("_")
    text = text.lower() or "section"
    if index is not None:
        text = f"{text}_{index}"
    return text


def split_sections(system_message: str) -> List[Dict[str, str]]:
    """Split the system_message into ordered sections."""
    matches = list(SECTION_PATTERN.finditer(system_message))
    sections: List[Dict[str, str]] = []

    if not matches:
        content = system_message.strip()
        if content:
            sections.append({"id": "body", "heading": None, "content": content})
        return sections

    # Capture preamble before the first heading, if present.
    first_start = matches[0].start()
    preamble = system_message[:first_start].strip()
    if preamble:
        sections.append({"id": "preamble", "heading": None, "content": preamble})

    heading_counts: defaultdict[str, int] = defaultdict(int)

    for idx, match in enumerate(matches):
        heading = match.group(0).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(system_message)
        content = system_message[start:end].strip("\n")
        heading_counts[heading] += 1
        count = heading_counts[heading]
        section_id = _heading_to_id(heading, index=count if count > 1 else None)
        sections.append({
            "id": section_id,
            "heading": heading,
            "content": content.strip()
        })

    return sections


def transform_agents(payload: Dict[str, Dict[str, Dict]]) -> Dict[str, Dict]:
    agents = payload.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("agents.json does not contain an 'agents' object")

    transformed: Dict[str, Dict] = OrderedDict()
    for agent_name, agent_config in agents.items():
        if not isinstance(agent_config, dict):
            transformed[agent_name] = agent_config
            continue

        system_message = agent_config.get("system_message")
        if not isinstance(system_message, str):
            transformed[agent_name] = agent_config
            continue

        sections = split_sections(system_message)
        new_config = OrderedDict()
        new_config["prompt_sections"] = sections
        for key, value in agent_config.items():
            if key == "system_message":
                continue
            new_config[key] = value
        transformed[agent_name] = new_config

    return {"agents": transformed}


def main() -> None:
    if not RE_AGENTS_JSON.exists():
        raise FileNotFoundError(f"Could not locate {RE_AGENTS_JSON}")

    data = json.loads(RE_AGENTS_JSON.read_text(encoding="utf-8"))
    transformed = transform_agents(data)
    RE_AGENTS_JSON.write_text(
        json.dumps(transformed, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
