# ==============================================================================
# FILE: core/events/unified_event_dispatcher.py
# DESCRIPTION: Centralized event dispatcher for all event types in MozaiksAI
# ==============================================================================

import logging
import uuid
from typing import Dict, Any, Optional, Union, List, cast
from datetime import datetime, timezone, UTC
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# Enhanced logging setup
from logs.logging_config import get_core_logger, get_workflow_logger

# Get our enhanced loggers
logger = get_core_logger("unified_event_dispatcher")
wf_logger = get_workflow_logger("event_dispatcher")

# Attempt guarded AG2 imports here so SimpleTransport can delegate mapping logic
try:  # pragma: no cover
    from autogen.events import BaseEvent as AG2BaseEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2BaseEvent = None  # type: ignore
try:  # agent events (guarded individually for forward compat)
    from autogen.events.agent_events import TextEvent as AG2TextEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2TextEvent = None  # type: ignore
try:
    from autogen.events.agent_events import ToolCallEvent as AG2ToolCallEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2ToolCallEvent = None  # type: ignore
try:
    from autogen.events.agent_events import ToolResponseEvent as AG2ToolResponseEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2ToolResponseEvent = None  # type: ignore
try:
    from autogen.events.agent_events import InputRequestEvent as AG2InputRequestEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2InputRequestEvent = None  # type: ignore
try:
    from autogen.events.agent_events import UsageSummaryEvent as AG2UsageSummaryEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2UsageSummaryEvent = None  # type: ignore
try:
    from autogen.events.agent_events import ErrorEvent as AG2ErrorEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2ErrorEvent = None  # type: ignore
try:
    from autogen.events.agent_events import SelectSpeakerEvent as AG2SelectSpeakerEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2SelectSpeakerEvent = None  # type: ignore
try:
    from autogen.events.agent_events import RunCompletionEvent as AG2RunCompletionEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2RunCompletionEvent = None  # type: ignore
try:  # optional print event location
    from autogen.events.print_event import PrintEvent as AG2PrintEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2PrintEvent = None  # type: ignore

try:  # access workflow structured outputs config
    from core.workflow.workflow_manager import workflow_manager  # type: ignore
except Exception:  # pragma: no cover
    workflow_manager = None  # type: ignore

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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: str = field(default="ui_tool")

@dataclass
class SessionPausedEvent:
    """Session paused due to insufficient tokens or other conditions"""
    chat_id: str
    reason: str
    user_id: str
    enterprise_id: str
    required_tokens: Optional[int] = None
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: str = field(default="business")

# ==============================================================================
# EVENT HANDLERS (Abstract Base Classes)
# ==============================================================================

# Type alias for all event types
EventType = Union[BusinessLogEvent, UIToolEvent, SessionPausedEvent]

class EventHandler(ABC):
    """Abstract base class for event handlers"""
    
    @abstractmethod
    async def handle(self, _event: EventType) -> bool:
        """Handle an event. Returns True if handled successfully."""
        pass
    
    @abstractmethod
    def can_handle(self, _event: EventType) -> bool:
        """Check if this handler can process the given event."""
        pass

class BusinessLogHandler(EventHandler):
    """Handler for business logic events (logging and monitoring)"""
    
    def can_handle(self, event: EventType) -> bool:
        return event.category == "business"
    
    async def handle(self, event: EventType) -> bool:
        """Handle business logging events"""
        if isinstance(event, BusinessLogEvent):
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
                logger.error(f"Failed to handle business event: {e}")
                return False
        
        elif isinstance(event, SessionPausedEvent):
            try:
                # Log the session pause
                wf_logger.warning(f"⏸️ Session paused: {event.reason} (chat_id: {event.chat_id})")
                
                # Emit to transport layer for UI notification  
                try:
                    from core.transport.simple_transport import SimpleTransport
                    # Get singleton instance without parameters
                    transport = await SimpleTransport.get_instance()
                    if transport:
                        await transport.emit_session_paused(event)
                except ImportError:
                    logger.warning("SimpleTransport not available for session paused notification")
                    
                return True
            except Exception as e:
                logger.error(f"Failed to handle session paused event: {e}")
                return False
        
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
        # Runtime cache for AG2 class -> chat.* mapping (filled lazily)
        self._ag2_class_map: Dict[type, str] = {}
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
        start_time = datetime.now(UTC)

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
            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000
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
            "timestamp": datetime.now(UTC).isoformat(),
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

    # ==================================================================
    # OUTBOUND EVENT ENVELOPE BUILDER (delegated from SimpleTransport)
    # ==================================================================
    def build_outbound_event_envelope(
        self,
        *,
        raw_event: Any,
        chat_id: Optional[str],
        get_sequence_cb: Optional[Any] = None,
        workflow_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Centralized transformation of raw orchestration/AG2 events into
        transport envelope { type, data, timestamp }.

        Parameters:
            raw_event: Either a pre-normalized dict (with 'kind') or an AG2 BaseEvent instance.
            chat_id: Target chat (used for sequence assignment and filtering).
            get_sequence_cb: Callback returning next per-chat sequence int.
            workflow_name: For structured outputs detection.

        Returns:
            envelope dict or None (if filtered / cannot map).

        Notes:
            - This removes heavy mapping logic from SimpleTransport for SoC.
            - Future: raw passthrough variant (emit_raw_ag2) could be added here; see comment below.
        """
        timestamp = datetime.now(UTC).replace(tzinfo=timezone.utc).isoformat()  # type: ignore[name-defined]
        # Fast-path normalized dicts
        if isinstance(raw_event, dict) and 'kind' in raw_event:
            # Explicitly widen value type for downstream bool enrichment
            event_dict: Dict[str, Any] = raw_event  # type: ignore[assignment]
            kind_val = event_dict.get('kind')
            kind = str(kind_val) if kind_val is not None else 'unknown'
            # Support callers already passing namespaced kinds like chat.text
            if kind.startswith('chat.'):
                # derive base kind (chat.text -> text) for uniform enrichment, but keep full mapping later
                base_kind = kind.split('.', 1)[1]
            else:
                base_kind = kind
            if kind == 'input_request' and 'request_id' in event_dict and 'corr' not in event_dict:
                event_dict['corr'] = event_dict['request_id']
            if base_kind in ('text', 'print') and workflow_manager and workflow_name:
                agent_name = event_dict.get('agent') or event_dict.get('sender')
                structured_flag = False
                visual_flag = False
                tool_agent_flag = False
                if agent_name:
                    try:
                        cfg = workflow_manager.get_agent_structured_outputs_config(workflow_name)  # type: ignore
                        structured_flag = cfg.get(agent_name, False)
                    except Exception:
                        structured_flag = False
                    try:
                        visual_agents = workflow_manager.get_visual_agents(workflow_name)  # type: ignore
                        visual_flag = agent_name in visual_agents
                    except Exception:
                        visual_flag = False
                    try:
                        # Check if this agent has any UI tools associated
                        ui_tools = workflow_manager.get_ui_tools(workflow_name)  # type: ignore
                        tool_agent_flag = any(
                            tool.get('agent') == agent_name or tool.get('caller') == agent_name 
                            for tool in ui_tools.values()
                        )
                    except Exception:
                        tool_agent_flag = False
                # New explicit flags for frontend rendering logic
                event_dict['is_structured_capable'] = structured_flag
                event_dict['is_visual'] = visual_flag
                event_dict['is_tool_agent'] = tool_agent_flag
                if get_sequence_cb and chat_id:
                    try:
                        event_dict['sequence'] = get_sequence_cb(chat_id)
                    except Exception:
                        pass
            ns_map = {
                'print': 'chat.print',
                'text': 'chat.text',
                'input_request': 'chat.input_request',
                'input_ack': 'chat.input_ack',
                'input_timeout': 'chat.input_timeout',
                'select_speaker': 'chat.select_speaker',
                'resume_boundary': 'chat.resume_boundary',
                'usage_summary': 'chat.usage_summary',
                'run_complete': 'chat.run_complete',
                'error': 'chat.error',
                'tool_call': 'chat.tool_call',
                'tool_response': 'chat.tool_response',
            }
            mapped_type = kind if kind.startswith('chat.') else ns_map.get(kind, kind)
            return {'type': mapped_type, 'data': event_dict, 'timestamp': timestamp}

        # AG2 BaseEvent path
        if AG2BaseEvent and isinstance(raw_event, AG2BaseEvent):  # type: ignore
            cls = type(raw_event)
            if not self._ag2_class_map:  # lazily populate
                if AG2TextEvent: self._ag2_class_map[AG2TextEvent] = 'chat.text'  # type: ignore
                if AG2PrintEvent: self._ag2_class_map[AG2PrintEvent] = 'chat.print'  # type: ignore
                if AG2ToolCallEvent: self._ag2_class_map[AG2ToolCallEvent] = 'chat.tool_call'  # type: ignore
                if AG2ToolResponseEvent: self._ag2_class_map[AG2ToolResponseEvent] = 'chat.tool_response'  # type: ignore
                if AG2InputRequestEvent: self._ag2_class_map[AG2InputRequestEvent] = 'chat.input_request'  # type: ignore
                if AG2UsageSummaryEvent: self._ag2_class_map[AG2UsageSummaryEvent] = 'chat.usage_summary'  # type: ignore
                if AG2ErrorEvent: self._ag2_class_map[AG2ErrorEvent] = 'chat.error'  # type: ignore
                if AG2SelectSpeakerEvent: self._ag2_class_map[AG2SelectSpeakerEvent] = 'chat.select_speaker'  # type: ignore
                if AG2RunCompletionEvent: self._ag2_class_map[AG2RunCompletionEvent] = 'chat.run_complete'  # type: ignore
            mapped_type = self._ag2_class_map.get(cls)
            if mapped_type:
                # Serialize with best-effort Pydantic compatibility
                try:
                    payload = cast(Dict[str, Any], raw_event.dict())  # type: ignore
                except Exception:
                    try:
                        payload = cast(Dict[str, Any], raw_event.model_dump())  # type: ignore[attr-defined]
                    except Exception:
                        payload = {'event_type': cls.__name__}
                if mapped_type == 'chat.input_request' and 'corr' not in payload:
                    for candidate in ('request_id', 'id', 'uuid'):
                        if candidate in payload:
                            payload['corr'] = payload[candidate]
                            break
                if mapped_type in ('chat.text', 'chat.print') and workflow_manager and workflow_name:
                    if not isinstance(payload, dict):
                        payload = {'event_type': cls.__name__}
                    agent_name = payload.get('sender') or payload.get('agent')
                    structured_flag = False
                    visual_flag = False
                    tool_agent_flag = False
                    if agent_name:
                        try:
                            cfg = workflow_manager.get_agent_structured_outputs_config(workflow_name)  # type: ignore
                            structured_flag = cfg.get(agent_name, False)
                        except Exception:
                            structured_flag = False
                        try:
                            visual_agents = workflow_manager.get_visual_agents(workflow_name)  # type: ignore
                            visual_flag = agent_name in visual_agents
                        except Exception:
                            visual_flag = False
                        try:
                            # Check if this agent has any UI tools associated
                            ui_tools = workflow_manager.get_ui_tools(workflow_name)  # type: ignore
                            tool_agent_flag = any(
                                tool.get('agent') == agent_name or tool.get('caller') == agent_name 
                                for tool in ui_tools.values()
                            )
                        except Exception:
                            tool_agent_flag = False
                    payload['is_structured_capable'] = structured_flag  # type: ignore[assignment]
                    payload['is_visual'] = visual_flag  # type: ignore[assignment]
                    payload['is_tool_agent'] = tool_agent_flag  # type: ignore[assignment]
                    if get_sequence_cb:
                        try:
                            payload['sequence'] = get_sequence_cb(chat_id)
                        except Exception:
                            pass
                return {'type': mapped_type, 'data': payload, 'timestamp': timestamp}

        # Fallback generic envelope (kept for forward compatibility)
        try:
            if AG2BaseEvent and isinstance(raw_event, AG2BaseEvent):  # type: ignore
                try:
                    payload = cast(Dict[str, Any], raw_event.dict())  # type: ignore
                except Exception:
                    try:
                        payload = cast(Dict[str, Any], raw_event.model_dump())  # type: ignore[attr-defined]
                    except Exception:
                        payload = {'event_type': type(raw_event).__name__}
            elif isinstance(raw_event, dict):
                payload = raw_event
            else:
                payload = {'event_type': type(raw_event).__name__, 'content': str(raw_event)}
            return {'type': 'ag2_event', 'data': payload, 'timestamp': timestamp}
        except Exception as e:  # pragma: no cover
            wf_logger.error(f"Failed to build outbound envelope: {e}")
            return None

        # Future: raw AG2 passthrough (emit_raw_ag2) could be implemented here if needed
        # by returning an envelope like {'type': 'ag2.raw', 'data': serialized_original,...}

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
