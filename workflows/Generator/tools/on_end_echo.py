# ==============================================================================
# FILE: Generator/tools/on_end_echo.py 
# DESCRIPTION: Simple Echo tool that runs once when the group-chat finishes
# ==============================================================================
import logging
biz_log = logging.getLogger("business.tools.on_end")


def echo_on_end(manager, message_history):
    """
    Log when group chat ends.
    Args:
        manager: The group chat manager instance
        message_history: List of messages in the conversation
    """
    # Get chat_id from manager if available
    chat_id = getattr(manager, 'chat_id', 'unknown')
    
    message_count = len(message_history) if message_history else 0
    
    # Get final sender if available
    final_sender = "none"
    if message_history:
        last_msg = message_history[-1]
        final_sender = last_msg.get("sender", "unknown") if isinstance(last_msg, dict) else "unknown"
    
    biz_log.info(
        "on_end_echo | chat_id=%s | total_messages=%s | final_sender=%s",
        chat_id,
        message_count,
        final_sender
    )
