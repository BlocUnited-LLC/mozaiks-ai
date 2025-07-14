"""
Events Module
Handles all event-related functionality including protocols and event definitions.
"""

# Core event system
from .simple_events import *
from .simple_protocols import *

__all__ = [
    # Export event classes
    # SimpleEvent, SimpleEventType, SimpleEventEncoder from simple_events
    # SimpleCommunicationChannel from simple_protocols
]
