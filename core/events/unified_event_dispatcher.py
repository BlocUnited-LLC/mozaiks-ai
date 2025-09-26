# ==============================================================================
# FILE: core/events/unified_event_dispatcher.py
# DESCRIPTION: Centralized event dispatcher for all event types in MozaiksAI
# ==============================================================================

"""Unified Event Dispatcher (clean version)

This simplified implementation removes legacy forward-compat fallback logic.
All AG2 runtime events should already be normalized into dicts with a 'kind'
property (handled earlier by event_serialization / orchestration). Dispatcher
focuses on:
  - BusinessLogEvent / UIToolEvent internal domain events
  - Lightweight outbound envelope construction for already-normalized events
"""

import logging
import uuid
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, UTC
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from logs.logging_config import get_core_logger, get_workflow_logger

logger = get_core_logger("unified_event_dispatcher")
wf_logger = get_workflow_logger("event_dispatcher")

try:  # workflow config (optional in some minimal test contexts)
    from core.workflow.workflow_manager import workflow_manager  # type: ignore
except Exception:  # pragma: no cover
    workflow_manager = None  # type: ignore

class EventCategory(Enum):
    BUSINESS = "business"
    UI_TOOL = "ui_tool"

@dataclass
class BusinessLogEvent:
    log_event_type: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    level: str = "INFO"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: str = field(default="business")

@dataclass
class UIToolEvent:
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
    chat_id: str
    reason: str
    required_tokens: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    category: str = field(default="runtime")


EventType = Union[BusinessLogEvent, UIToolEvent, SessionPausedEvent]

class EventHandler(ABC):
    @abstractmethod
    async def handle(self, _event: EventType) -> bool:
        ...

    @abstractmethod
    def can_handle(self, _event: EventType) -> bool:
        ...

class BusinessLogHandler(EventHandler):
    def can_handle(self, event: EventType) -> bool:
        return isinstance(event, BusinessLogEvent)

    async def handle(self, event: EventType) -> bool:
        if not isinstance(event, BusinessLogEvent):
            return False
        lvl = getattr(logger, event.level.lower(), logger.info)
        lvl(f"[BUSINESS] {event.log_event_type}: {event.description} context={event.context}")
        return True

class UIToolHandler(EventHandler):
    def can_handle(self, event: EventType) -> bool:
        return isinstance(event, UIToolEvent)

    async def handle(self, event: EventType) -> bool:
        if not isinstance(event, UIToolEvent):
            return False
        logger.debug(f"[UI_TOOL] id={event.ui_tool_id} workflow={event.workflow_name} display={event.display}")
        return True

class UnifiedEventDispatcher:
    def __init__(self):
        self.handlers: List[EventHandler] = []
        self.metrics: Dict[str, Any] = {
            "events_processed": 0,
            "events_failed": 0,
            "events_by_category": {"business": 0, "ui_tool": 0},
            "created": datetime.now(UTC).isoformat(),
        }
        self._setup_default_handlers()

    def _setup_default_handlers(self):
        self.register_handler(BusinessLogHandler())
        self.register_handler(UIToolHandler())

    def register_handler(self, handler: EventHandler):
        self.handlers.append(handler)

    async def dispatch(self, event: EventType) -> bool:
        start_time = datetime.now(UTC)
        try:
            handler = next((h for h in self.handlers if h.can_handle(event)), None)
            if not handler:
                logger.warning(f"No handler for event category={getattr(event,'category',None)}")
                self.metrics["events_failed"] += 1
                return False
            success = await handler.handle(event)
            if success:
                self.metrics["events_processed"] += 1
                cat = getattr(event, "category", None)
                if cat in self.metrics["events_by_category"]:
                    self.metrics["events_by_category"][cat] += 1
            else:
                self.metrics["events_failed"] += 1
            dur_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            if dur_ms > 100:
                logger.info(f"Slow event dispatch category={getattr(event,'category',None)} dur={dur_ms:.1f}ms")
            return success
        except Exception as e:  # pragma: no cover
            logger.error(f"Dispatch failure: {e}")
            self.metrics["events_failed"] += 1
            return False

    def get_metrics(self) -> Dict[str, Any]:
        return {**self.metrics, "handler_count": len(self.handlers), "timestamp": datetime.now(UTC).isoformat()}

    async def emit_business_event(
        self,
        log_event_type: str,
        description: str,
        context: Optional[Dict[str, Any]] = None,
        level: str = "INFO",
    ) -> bool:
        event = BusinessLogEvent(log_event_type=log_event_type, description=description, context=context or {}, level=level)
        return await self.dispatch(event)

    async def emit_ui_tool_event(
        self,
        ui_tool_id: str,
        payload: Dict[str, Any],
        workflow_name: str,
        display: str = "inline",
        chat_id: Optional[str] = None,
    ) -> bool:
        event = UIToolEvent(ui_tool_id=ui_tool_id, payload=payload, workflow_name=workflow_name, display=display, chat_id=chat_id)
        return await self.dispatch(event)

    def build_outbound_event_envelope(
        self,
        *,
        raw_event: Any,
        chat_id: Optional[str],
        get_sequence_cb: Optional[Any] = None,
        workflow_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Expect normalized dict with 'kind'; enrich minimal metadata and namespace kind."""
        if not (isinstance(raw_event, dict) and 'kind' in raw_event):
            return None
        timestamp = datetime.now(UTC).isoformat()
        event_dict: Dict[str, Any] = raw_event  # type: ignore[assignment]
        kind = str(event_dict.get('kind', 'unknown'))
        base_kind = kind.split('.', 1)[1] if kind.startswith('chat.') else kind
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
                    pass
                try:
                    visual_agents = workflow_manager.get_visual_agents(workflow_name)  # type: ignore
                    visual_flag = agent_name in visual_agents
                except Exception:
                    pass
                try:
                    ui_tools = workflow_manager.get_ui_tools(workflow_name)  # type: ignore
                    tool_agent_flag = any(
                        tool.get('agent') == agent_name or tool.get('caller') == agent_name
                        for tool in ui_tools.values()
                    )
                except Exception:
                    pass
            event_dict['is_structured_capable'] = structured_flag
            event_dict['is_visual'] = visual_flag
            event_dict['is_tool_agent'] = tool_agent_flag
            if get_sequence_cb and chat_id:
                try:
                    event_dict['sequence'] = get_sequence_cb(chat_id)
                except Exception:
                    pass
        ns_map = {
            'print': 'chat.print', 'text': 'chat.text', 'input_request': 'chat.input_request', 'input_ack': 'chat.input_ack',
            'input_timeout': 'chat.input_timeout', 'select_speaker': 'chat.select_speaker', 'resume_boundary': 'chat.resume_boundary',
            'usage_summary': 'chat.usage_summary', 'run_complete': 'chat.run_complete', 'error': 'chat.error', 'tool_call': 'chat.tool_call', 'tool_response': 'chat.tool_response'
        }
        mapped_type = kind if kind.startswith('chat.') else ns_map.get(kind, kind)
        return {'type': mapped_type, 'data': event_dict, 'timestamp': timestamp}

_global_dispatcher: Optional[UnifiedEventDispatcher] = None

def get_event_dispatcher() -> UnifiedEventDispatcher:
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = UnifiedEventDispatcher()
    return _global_dispatcher

async def emit_business_event(
    log_event_type: str,
    description: str,
    context: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
) -> bool:
    dispatcher = get_event_dispatcher()
    return await dispatcher.emit_business_event(log_event_type, description, context, level)

async def emit_ui_tool_event(
    ui_tool_id: str,
    payload: Dict[str, Any],
    workflow_name: str,
    display: str = "inline",
    chat_id: Optional[str] = None
) -> bool:
    dispatcher = get_event_dispatcher()
    return await dispatcher.emit_ui_tool_event(ui_tool_id, payload, workflow_name, display, chat_id)

