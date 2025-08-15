# ==============================================================================
# FILE: core/workflow/helpers.py
# DESCRIPTION: Centralized helper functions for workflow management.
# ==============================================================================
import re
from typing import Optional

def get_formatted_agent_name(agent_name: Optional[str]) -> str:
    """
    Centralized function to format agent names for consistent UI display and logging.
    - Converts CamelCase to Title Case
    - Removes the "Agent" suffix
    - Handles None or empty names gracefully
    """
    if not agent_name:
        return "Assistant"
    
    # Convert CamelCase to Title Case (e.g., "MyAgent" -> "My Agent")
    formatted = re.sub(r'([A-Z])', r' \1', agent_name).strip()
    
    # Remove "Agent" suffix and any extra whitespace
    formatted = formatted.replace("Agent", "").strip()
    
    # Return the formatted name or "Assistant" if formatting results in an empty string
    return formatted or "Assistant"
