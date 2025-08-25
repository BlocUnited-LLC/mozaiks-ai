# ==============================================================================
# FILE: core/events/unified_event_dispatcher.py
# DESCRIPTION: Centralized event dispatcher for all event types in MozaiksAI
# ==============================================================================

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Union, Callable, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# Import our logging configuration
from logs.logging_config import get_workflow_logger

# Core logger for the event dispatcher
logger = logging.getLogger(__name__)
wf_logger = get_workflow_logger("event_dispatcher")

# ==============================================================================
# EVENT CATEGORY DEFINITIONS
# ==============================================================================

class EventCategory(Enum):
    """Clear event category definitions"""
    BUSINESS = "business"      # Application lifecycle and monitoring  
    UI_TOOL = "ui_tool"       # User interface interactions

# ==============================================================================
# EVENT DATA CLASSES
# ==============================================================================

@dataclass
class BusinessLogEvent:
    """Business logic events for monitoring and lifecycle tracking"""
    log_event_type: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    level: str = "INFO"
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: str = field(default="business")

@dataclass
class UIToolEvent:
    """UI interaction events for dynamic components"""
    ui_tool_id: str
    payload: Dict[str, Any]
    workflow_name: str
    display: str = "inline"
    chat_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: str = field(default="ui_tool")

# ==============================================================================
# EVENT HANDLERS (Abstract Base Classes)
# ==============================================================================

# Type alias for all event types
EventType = Union[BusinessLogEvent, UIToolEvent]

class EventHandler(ABC):
    """Abstract base class for event handlers"""
    
    @abstractmethod
    async def handle(self, event: EventType) -> bool:
        """Handle an event. Returns True if handled successfully."""
        pass
    
    @abstractmethod
    def can_handle(self, event: EventType) -> bool:
        """Check if this handler can process the given event."""
        pass

class BusinessLogHandler(EventHandler):
    """Handler for business logic events (logging and monitoring)"""
    
    def can_handle(self, event: EventType) -> bool:
        return event.category == "business"
    
    async def handle(self, event: EventType) -> bool:
        """Handle business logging events"""
        if not isinstance(event, BusinessLogEvent):
            return False
            
        try:
            # Log business event details using workflow logger
            level = getattr(wf_logger, event.level.lower(), wf_logger.info)
            level(
                f"BUSINESS_EVENT {event.log_event_type}: {event.description}",
                **(event.context or {})
            )
            wf_logger.debug(f"📊 Business event processed: {event.log_event_type}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to handle business event {event.log_event_type}: {e}")
            return False

class UIToolHandler(EventHandler):
    """Handler for UI tool events (user interactions)"""
    
    def can_handle(self, event: EventType) -> bool:
        return event.category == "ui_tool"
    
    async def handle(self, event: EventType) -> bool:
        """Handle UI tool events - LOG ONLY to prevent circular dependencies"""
        if not isinstance(event, UIToolEvent):
            return False
            
        try:
            # LOG the UI tool event but DO NOT send it back through transport
            # This prevents the circular dependency that was causing infinite loops
            wf_logger.debug(f"🔧 UI Tool event logged: {event.ui_tool_id} for workflow {event.workflow_name}")
            
            # Log the event payload for debugging
            wf_logger.debug(f"🔧 UI Tool payload: {event.payload}")
            
            # Mark as successfully processed - the transport layer should handle actual UI updates directly
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to handle UI tool event {event.ui_tool_id}: {e}")
            return False

# ==============================================================================
# UNIFIED EVENT DISPATCHER
# ==============================================================================

class UnifiedEventDispatcher:
    """
    Centralized event dispatcher that routes events to appropriate handlers.

    Scope (by design):
    - Business Logic Events (logging/monitoring)
    - UI Tool Events (user interactions)

        Not in scope:
        - AG2 runtime (agent) events fanout. Those are forwarded to the UI
            directly by the orchestrator via SimpleTransport to avoid latency and
            circular dependencies.
    """

    def __init__(self):
        self.handlers: List[EventHandler] = []
        self.metrics = {
            "events_processed": 0,
            "events_failed": 0,
            "events_by_category": {
                "business": 0,
                "ui_tool": 0,
            },
        }
        # Initialize default handlers and log readiness
        self._setup_default_handlers()
        wf_logger.info("🎯 Unified Event Dispatcher initialized")

    def _setup_default_handlers(self):
        """Setup default handlers for each event category"""
        self.handlers = [BusinessLogHandler(), UIToolHandler()]
        wf_logger.debug(f"📋 Registered {len(self.handlers)} default event handlers")

    def register_handler(self, handler: EventHandler):
        """Register a custom event handler"""
        self.handlers.append(handler)
        wf_logger.debug(f"➕ Registered custom event handler: {handler.__class__.__name__}")

    async def dispatch(self, event: EventType) -> bool:
        """
        Dispatch an event to the appropriate handler.

        Args:
            event: The event to dispatch

        Returns:
            bool: True if event was handled successfully
        """
        start_time = datetime.utcnow()

        try:
            # Find appropriate handler
            handler = None
            for h in self.handlers:
                if h.can_handle(event):
                    handler = h
                    break

            if not handler:
                logger.warning(f"⚠️ No handler found for event category: {event.category}")
                self.metrics["events_failed"] += 1
                return False

            # Handle the event
            success = await handler.handle(event)

            # Update metrics
            if success:
                self.metrics["events_processed"] += 1
                if event.category in self.metrics["events_by_category"]:
                    self.metrics["events_by_category"][event.category] += 1
            else:
                self.metrics["events_failed"] += 1

            # Log performance
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            if duration > 100:  # Log slow events
                logger.warning(f"⏱️ Slow event processing: {event.category} took {duration:.2f}ms")

            return success

        except Exception as e:
            logger.error(f"❌ Event dispatch failed for {event.category}: {e}")
            self.metrics["events_failed"] += 1
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """Get dispatcher metrics"""
        return {
            **self.metrics,
            "handler_count": len(self.handlers),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ======================================================================
    # CONVENIENCE METHODS FOR EACH EVENT TYPE
    # ======================================================================

    async def emit_business_event(
        self,
        log_event_type: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
        level: str = "INFO",
    ) -> bool:
        """Emit a business logic event"""
        event = BusinessLogEvent(
            log_event_type=log_event_type,
            description=description,
            context=context or {},
            level=level,
        )
        return await self.dispatch(event)

    async def emit_ui_tool_event(
        self,
        ui_tool_id: str,
        payload: Dict[str, Any],
        workflow_name: str,
        display: str = "inline",
        chat_id: Optional[str] = None,
    ) -> bool:
        """Emit a UI tool event"""
        event = UIToolEvent(
            ui_tool_id=ui_tool_id,
            payload=payload,
            workflow_name=workflow_name,
            display=display,
            chat_id=chat_id,
        )
        return await self.dispatch(event)

# ==============================================================================
# GLOBAL DISPATCHER INSTANCE
# ==============================================================================

# Global dispatcher instance (singleton pattern)
_global_dispatcher: Optional[UnifiedEventDispatcher] = None

def get_event_dispatcher() -> UnifiedEventDispatcher:
    """Get the global event dispatcher instance"""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = UnifiedEventDispatcher()
    return _global_dispatcher

# ==============================================================================
# CONVENIENCE FUNCTIONS (mirror main API)
# ==============================================================================

async def emit_business_event(
    log_event_type: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
) -> bool:
    """Convenience function to emit business events through dispatcher"""
    dispatcher = get_event_dispatcher()
    return await dispatcher.emit_business_event(log_event_type, description, context, level)

async def emit_ui_tool_event(
    ui_tool_id: str,
    payload: Dict[str, Any],
    workflow_name: str,
    display: str = "inline",
    chat_id: Optional[str] = None
) -> bool:
    """Convenience function to emit UI tool events through dispatcher"""
    dispatcher = get_event_dispatcher()
    return await dispatcher.emit_ui_tool_event(ui_tool_id, payload, workflow_name, display, chat_id)
