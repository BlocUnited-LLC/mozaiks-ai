# ==============================================================================
# FILE: core/events/__init__.py
# DESCRIPTION: Events package initialization - unified event system exports
# ==============================================================================

"""
MozaiksAI Unified Event System

This package provides a centralized event dispatcher for all event types:
- Business Logic Events (logging/monitoring)
- AG2 Runtime Events (workflow execution)  
- UI Tool Events (user interactions)

Usage Examples:

    # Business events
    from core.events import emit_business_event
    await emit_business_event("WORKFLOW_STARTED", "Workflow initialized")

    # UI tool interactions should use use_ui_tool helper (see core.workflow.ui_tools)
    from core.workflow.ui_tools import use_ui_tool
    response = await use_ui_tool("api_key_input", {"service": "openai"}, workflow_name="generator")
    api_key = response.get("api_key")

    # Direct dispatcher access (advanced / internal)
    from core.events import get_event_dispatcher
    dispatcher = get_event_dispatcher()
    metrics = dispatcher.get_metrics()
"""

from .unified_event_dispatcher import (
    # Core classes
    UnifiedEventDispatcher,
    EventCategory,
    EventType,
    BusinessLogEvent,
    UIToolEvent,
    SessionPausedEvent,
    
    # Event handlers
    EventHandler,
    BusinessLogHandler,
    UIToolHandler,
    
    # Main functions
    get_event_dispatcher,
    emit_business_event
)

__all__ = [
    # Core dispatcher
    "UnifiedEventDispatcher",
    "get_event_dispatcher",
    
    # Event categories and types
    "EventCategory", 
    "EventType",
    "BusinessLogEvent",
    "UIToolEvent",
    "SessionPausedEvent",
    
    # Handlers
    "EventHandler",
    "BusinessLogHandler", 
    "UIToolHandler",
    
    # Convenience functions
    "emit_business_event"
]
