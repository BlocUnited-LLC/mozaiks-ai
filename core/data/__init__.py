"""
Data & Persistence Module - Clean Architecture
Provides database access and real-time AG2 persistence utilities.
"""

from .persistence_manager import PersistenceManager, AG2PersistenceManager
from .theme_validation import (
    ThemeValidationResult,
    ThemeValidationError,
    validate_theme_update,
    validate_full_theme,
    auto_validate_theme,
    summarize_validation,
)

__all__ = [
    "PersistenceManager",
    "AG2PersistenceManager",
    "ThemeValidationResult",
    "ThemeValidationError",
    "validate_theme_update",
    "validate_full_theme",
    "auto_validate_theme",
    "summarize_validation",
]
