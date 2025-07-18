# ==============================================================================
# FILE: workflows/Generator/tools/conversation_analyzer.py
# DESCRIPTION: Hook to analyze the full conversation before agents reply
# ==============================================================================

from typing import List, Dict, Any, Optional

def analyze_full_conversation(
    messages: List[Dict[str, Any]],
    sender,
    config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """AG2 Hook: Analyzes the full conversation history before any agent replies.
    
    This hook fires when an agent is about to generate a reply and needs to
    process the entire conversation context. Useful for conversation analysis
    and context understanding.
    """
    sender_name = getattr(sender, 'name', 'Unknown')
    message_count = len(messages) if messages else 0
    
    # Note: config parameter included for AG2 interface compatibility
    config_status = "provided" if config else "none"
    print(f"📚 CONVERSATION ANALYZER: {sender_name} analyzing {message_count} messages before reply (config: {config_status})")
    
    return messages
