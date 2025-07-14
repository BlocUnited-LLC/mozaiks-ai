# ==============================================================================
# FILE: Generator/tools/after_agent_echo.py  
# DESCRIPTION: Runs after every agent message and logs sender + char count
# ==============================================================================
import logging
biz_log = logging.getLogger("business.tools.after_agent")


def echo_after_each(manager, message_history):
    """
    Log information after each agent message.
    Args:
        manager: The group chat manager instance
        message_history: List of messages in the conversation
    """
    if not message_history:
        return
    
    # Get the last message
    last_msg = message_history[-1]
    
    if isinstance(last_msg, dict):
        sender = last_msg.get("sender", "unknown")
        content = last_msg.get("content", "")
    else:
        sender = getattr(last_msg, "sender", "unknown")
        content = getattr(last_msg, "content", "")
    
    char_count = len(str(content))
    
    biz_log.info(
        "after_agent_echo | sender=%s | chars=%s | total_messages=%s",
        sender,
        char_count,
        len(message_history)
    )
