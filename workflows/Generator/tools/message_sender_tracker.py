# ==============================================================================
# FILE: workflows/Generator/tools/message_sender_tracker.py
# DESCRIPTION: Hook to track when agents are about to send messages
# ==============================================================================

from typing import Dict, Any, Union
from autogen import ConversableAgent, Agent

def track_message_sending(
    sender: ConversableAgent,
    message: Union[Dict[str, Any], str],
    recipient: Agent,
    silent: bool
) -> Union[Dict[str, Any], str]:
    """AG2 Hook: Tracks when any agent is about to send a message to another agent.
    
    This hook fires right before an agent sends a message, allowing us to
    track message flow and communication patterns between agents.
    
    Args:
        sender: The agent that is sending the message
        message: The message being sent (dict or string)
        recipient: The agent that will receive the message
        silent: Whether the message is being sent silently
        
    Returns:
        The message (potentially modified)
    """
    sender_name = getattr(sender, 'name', 'Unknown') if sender else 'Unknown'
    recipient_name = getattr(recipient, 'name', 'Unknown') if recipient else 'Unknown'
    
    print(f"📤 SENDER TRACKER: {sender_name} → {recipient_name} (silent: {silent})")
    
    # Return message unchanged
    return message