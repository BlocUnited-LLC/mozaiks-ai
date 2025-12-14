"""
pattern_selection tool - stores AG2 pattern selection from PatternAgent.

Caches the selected pattern so update_agent_state hooks can inject pattern-specific
guidance into downstream agent prompts.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, Optional

_logger = logging.getLogger("tools.pattern_selection")


def pattern_selection(
    *,
    PatternSelection: Annotated[Optional[Dict[str, Any]], "Pattern selection payload"],
    context_variables: Annotated[Optional[Any], "Context variables provided by AG2"] = None,
) -> str:
    """Persist pattern selection for downstream prompt injections."""

    if not PatternSelection or not isinstance(PatternSelection, dict):
        _logger.warning("pattern_selection called with no PatternSelection data")
        return "No pattern selection provided"

    selected_pattern = PatternSelection.get("selected_pattern")
    pattern_name = PatternSelection.get("pattern_name", "Unknown")

    if context_variables and hasattr(context_variables, "set"):
        try:
            context_variables.set("PatternSelection", PatternSelection)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive logging
            _logger.error("Failed to cache PatternSelection via context_variables.set: %s", exc)
    if context_variables and hasattr(context_variables, "data"):
        try:
            context_variables.data["PatternSelection"] = PatternSelection  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            _logger.debug("Unable to assign PatternSelection into context_variables.data: %s", exc)

    _logger.info("Cached pattern selection: %s (ID: %s)", pattern_name, selected_pattern)

    return f"Selected Pattern: {pattern_name} (ID: {selected_pattern})"
