# ==============================================================================
# FILE: Generator/tools/after_orchestrator_echo.py  
# DESCRIPTION: Runs after OrchestratorAgent messages only
# ==============================================================================
import logging
from typing import Any, List, Dict

biz_log = logging.getLogger("business.tools.after_orchestrator")

# AG2-compatible configuration for agent-specific lifecycle hooks
TRIGGER = "after_each_agent"  # Base trigger
TRIGGER_AGENT = "OrchestratorAgent"  # Only trigger for this specific agent


def echo_after_orchestrator(manager: Any, message_history: List[Dict[str, Any]]) -> None:
    """
    Log information after OrchestratorAgent messages only.
    
    This lifecycle hook demonstrates agent-specific triggering.
    
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
