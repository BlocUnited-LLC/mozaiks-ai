"""Transform hook handlers.

Echo-style handler for `process_all_messages_before_reply`.
"""
from typing import Any, Dict, List


def echo_all_messages(messages: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
    """PURPOSE: Minimal transformer for the full message list before reply.

    Appends a small marker to each message's content (if string) to confirm the
    hook executed. Changes are temporary for the reply phase.

    PARAMETERS:
      messages: The full list of message dicts.

    RETURNS:
      The updated list of message dicts.

    ERROR MODES:
      Best-effort: non-string contents are left unchanged.

    SIDE EFFECTS:
      None (returns a new list of dicts with in-place content updates for simplicity).
    """
    marker = " [all_echo]"
    for msg in messages:
        try:
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                msg["content"] = msg["content"] + marker
        except Exception:
            # Keep going even if a single message is malformed
            continue
    return messages
