"""Redaction hook handlers.

Contains simple echo-style handler(s) for testing 'process_message_before_send' hook wiring.
"""
from typing import Any, Dict, Union
from autogen import ConversableAgent, Agent

MessageType = Union[Dict[str, Any], str]

def echo_before_send(
    sender: "ConversableAgent",
    message: MessageType,
    recipient: "Agent",
    silent: bool,
) -> MessageType:
    """PURPOSE: Minimal no-op/echo handler for `process_message_before_send`.

    Adds a small test marker so you can verify that the hook executed, while
    preserving the original shape of the message (str or dict).

    PARAMETERS:
      sender: The agent sending the message.
      message: The outgoing message (dict with "content" or a raw string).
      recipient: The downstream agent.
      silent: Whether the send is silent.

    RETURNS:
      The updated message of the same type that came in.

    ERROR MODES:
      On any unexpected type, the message is returned unchanged.

    SIDE EFFECTS:
      None (pure transformation).
    """
    marker = "[before_send_echo] "

    if isinstance(message, dict):
        # Update the content field if present; otherwise, leave dict unchanged.
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = f"{marker}{content}"
        return message

    if isinstance(message, str):
        return f"{marker}{message}"

    return message
