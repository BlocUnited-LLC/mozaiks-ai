# ==============================================================================
# FILE: workflows/Generator/tools/conversation_analyzer.py
# DESCRIPTION: Hook to analyze the full conversation before agents reply
# ==============================================================================

from typing import List, Dict, Any, Optional

def analyze_full_conversation(
    messages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """AG2 Hook: Analyzes the full conversation history before any agent replies.
    
    This hook fires when an agent is about to generate a reply and needs to
    process the entire conversation context. Useful for conversation analysis
    and context understanding.
    
    Args:
        messages: The full conversation history
        
    Returns:
        List of message dictionaries (potentially modified)
    """
    message_count = len(messages) if messages else 0
    
    # Simple conversation analysis
    if messages:
        last_message = messages[-1] if messages else None
        last_content = last_message.get('content', '') if isinstance(last_message, dict) else str(last_message)
        word_count = len(last_content.split()) if last_content else 0
        
        print(f"📚 CONVERSATION ANALYZER: Processing {message_count} messages, last message has {word_count} words")
    else:
        print(f"📚 CONVERSATION ANALYZER: No messages to analyze")
    
    # Return messages unchanged
    return messages
