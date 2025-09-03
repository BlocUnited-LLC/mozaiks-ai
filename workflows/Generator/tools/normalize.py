"""Normalization hook handlers.

Echo-style handler for `process_last_received_message`.
"""
from typing import Any, Dict, List, Union

MessageIn = Union[str, List[Dict[str, Any]]]
MessageOut = str


def echo_last_message(message: MessageIn) -> MessageOut:
    """PURPOSE: Minimal transformer for the last received message.

    If a list of messages is provided, extracts the last item's content (if
    present). Returns a string with an echo marker to confirm execution.

    PARAMETERS:
      message: Either a raw string or a list of message dicts.

    RETURNS:
      A string representing the (possibly) transformed last message.

    ERROR MODES:
      On unexpected structures, returns a generic echo marker.

    SIDE EFFECTS:
      None (pure function).
    """
    marker = "[last_echo] "

    if isinstance(message, str):
        return f"{marker}{message}"

    # If it's a list of dict messages, try to read the last one's content
    if isinstance(message, list) and message:
        last = message[-1]
        content = last.get("content") if isinstance(last, dict) else None
        if isinstance(content, str):
            return f"{marker}{content}"

    return f"{marker}(no_content)"
