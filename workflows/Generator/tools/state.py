"""State hook handlers.

Echo-style handler for `update_agent_state` used to validate hook registration.
"""
from typing import Any, Dict, List

from typing import Any, Dict, Union
from autogen import ConversableAgent, Agent


def echo_update_state(agent: "ConversableAgent", messages: List[Dict[str, Any]]) -> None:
    """PURPOSE: Minimal state updater for `update_agent_state`.

    Appends a small marker to the agent's system message (if the API is
    available) that there was an api used and it will cost the user money.

    PARAMETERS:
      agent: The agent whose state may be updated.
      messages: The full message list (unused here; kept for signature parity).

    RETURNS:
      None.

    ERROR MODES:
      Silently no-ops if the agent lacks an `update_system_message` method.

    SIDE EFFECTS:
      Mutates agent.system_message via `update_system_message` when available.
    """
    marker = " [state_echo]"
    try:
        current = getattr(agent, "system_message", "") or ""
        new_msg = f"{current}{marker}".strip()
        if hasattr(agent, "update_system_message"):
            agent.update_system_message(new_msg)  # type: ignore[attr-defined]
    except Exception:
        # Best-effort: do not raise during echo testing
        return
