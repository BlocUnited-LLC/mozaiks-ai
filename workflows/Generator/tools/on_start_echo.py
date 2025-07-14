# ==============================================================================
# FILE: Generator/tools/on_start_echo.py  
# DESCRIPTION: Simple Echo tool that runs once at the very beginning of the group-chat
# ==============================================================================
import logging
biz_log = logging.getLogger("business.tools.on_start")


def echo_on_start(manager, message_history):
    """
    Log group chat start information.
    Note: message_history will be empty at start, but we still accept the parameter
    to maintain consistent hook signature.
    """
    # Get agent names from the manager's groupchat
    agent_names = []
    if hasattr(manager, 'groupchat') and hasattr(manager.groupchat, 'agents'):
        agent_names = [a.name for a in manager.groupchat.agents]
    elif hasattr(manager, 'agents'):
        agent_names = [a.name for a in manager.agents]
    
    # Get chat_id if available
    chat_id = getattr(manager, 'chat_id', 'unknown')
    
    biz_log.info(
        "on_start_echo | chat_id=%s | agents=%s | message_count=%s",
        chat_id,
        agent_names,
        len(message_history) if message_history else 0
    )
