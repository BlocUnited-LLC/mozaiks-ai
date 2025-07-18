# ==============================================================================
# FILE: workflows/Generator/tools/latest_message_inspector.py
# DESCRIPTION: Hook to inspect the latest message received by agents
# ==============================================================================

from typing import Dict, Any

def inspect_latest_message(
    sender,
    message: Dict[str, Any],
    recipient,
    request_reply: bool = False,
    silent: bool = False,
    sender_type: str = "agent"
) -> Dict[str, Any]:
    """AG2 Hook: Inspects the latest message received by any agent.
    
    This hook fires when an agent receives a message and needs to process it.
    Useful for message inspection, content analysis, and debugging message flow.
    """
    sender_name = getattr(sender, 'name', 'Unknown')
    recipient_name = getattr(recipient, 'name', 'Unknown')
    content = message.get('content', '') if isinstance(message, dict) else str(message)
    content_preview = content[:50] + '...' if len(content) > 50 else content
    
    # Note: using all parameters for AG2 interface compatibility
    print(f"📩 MESSAGE INSPECTOR: {recipient_name} received from {sender_name}: '{content_preview}' (reply: {request_reply}, silent: {silent}, type: {sender_type})")
    
    return message
