"""
Data & Persistence Module - Clean Architecture
Provides database access and real-time AG2 persistence utilities.
Updated: Removed deprecated performance_manager exports.
"""

from .persistence_manager import PersistenceManager, AG2PersistenceManager

__all__ = [
    "PersistenceManager",
    "AG2PersistenceManager",
]
