# ==============================================================================
# FILE: Generator/tools/after_orchestrator_echo.py  
# DESCRIPTION: Runs after OrchestratorAgent messages only
# ==============================================================================
import logging
biz_log = logging.getLogger("business.tools.after_orchestrator")


def echo_after_orchestrator(manager, message_history):
    """
    Log information after OrchestratorAgent messages only.
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
    
    # Only log if it's from OrchestratorAgent
    if sender == "OrchestratorAgent":
        char_count = len(str(content))
        
        biz_log.info(
            "after_orchestrator_echo | sender=%s | chars=%s | orchestrator_response=true",
            sender,
            char_count
        )
