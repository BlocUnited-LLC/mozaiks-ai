# ==============================================================================
# FILE: workflows/Generator/tools/message_sender_tracker.py
# DESCRIPTION: Hook to track when agents are about to send messages
# ==============================================================================

from typing import Dict, Any

def track_message_sending(
    sender,
    message: Dict[str, Any],
    recipient,
    request_reply: bool = False,
    silent: bool = False,
    sender_type: str = "agent"
) -> Dict[str, Any]:
    """AG2 Hook: Tracks when any agent is about to send a message to another agent.
    
    This hook fires right before an agent sends a message, allowing us to
    track message flow and communication patterns between agents.
    """
    sender_name = getattr(sender, 'name', 'Unknown')
    recipient_name = getattr(recipient, 'name', 'Unknown')
    
    # Note: using all parameters for AG2 interface compatibility
    print(f"📤 SENDER TRACKER: {sender_name} → {recipient_name} (reply: {request_reply}, silent: {silent}, type: {sender_type})")
    
    return message
    sender_name = getattr(sender, 'name', 'Unknown')
    recipient_name = getattr(recipient, 'name', 'Unknown')
    
    print(f"📤 SENDER TRACKER: {sender_name} → {recipient_name} (silent: {silent})")
    
    # Return message unchanged
    return message
