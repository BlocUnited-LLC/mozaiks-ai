"""
pattern_selection tool - Stores AG2 pattern selection from PatternAgent in context.

This tool caches the selected pattern ID in context variables for consumption by
update_agent_state hooks that inject pattern-specific guidance into agent prompts.
"""

from typing import Dict, Any, Annotated, Optional
import logging

_logger = logging.getLogger("tools.pattern_selection")


def pattern_selection(
    *,
    PatternSelection: Annotated[Optional[Dict[str, Any]], "Pattern selection payload"],
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> str:
    """
    Cache pattern selection from PatternAgent in context.

    This tool stores the selected AG2 orchestration pattern in context_variables
    for use by update_agent_state hooks that inject pattern guidance into
    WorkflowStrategyAgent, WorkflowImplementationAgent, ProjectOverviewAgent, and HandoffsAgent.

    Args:
        PatternSelection: Pattern selection data from PatternAgent (selected_pattern ID + pattern_name)
        context_variables: AG2 context variables instance

    Returns:
        Status message confirming pattern storage
    """
    if not PatternSelection:
        _logger.warning("pattern_selection called with no PatternSelection data")
        return "❌ No pattern selection provided"

    if not context_variables:
        _logger.error("pattern_selection called without context_variables")
        return "❌ Context variables unavailable"

    # Extract pattern details
    selected_pattern = PatternSelection.get('selected_pattern')
    pattern_name = PatternSelection.get('pattern_name', 'Unknown')

    # Store in context for update_agent_state hooks
    context_variables.data['PatternSelection'] = PatternSelection

    _logger.info(
        f"✓ Pattern selection cached: {pattern_name} (ID: {selected_pattern})"
    )

    # Return status message
    return f"✓ Selected Pattern: **{pattern_name}** (ID: {selected_pattern})"
