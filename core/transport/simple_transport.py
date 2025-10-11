# ==============================================================================
# FILE: core/transport/simple_transport.py
# DESCRIPTION: Lean transport system for real-time UI communication
# ==============================================================================
import logging
import asyncio
import re
import json
import uuid
import traceback
from typing import Dict, Any, Optional, Union, Tuple, List
from fastapi import WebSocket
from datetime import datetime, timezone
try:  # pymongo optional in some test environments
    from pymongo import ReturnDocument  # type: ignore
except Exception:  # pragma: no cover
    class ReturnDocument:  # minimal fallback so attribute exists
        BEFORE = 0
        AFTER = 1

# AG2 imports for event type checking
from autogen.events import BaseEvent

# Guarded AG2 event class imports (top-level, no lazy inside hot path)
try:  # Core frequently used
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

# Print / streaming output event may live in a different module in some AG2 versions
try:  # pragma: no cover - optional
    from autogen.events.print_event import PrintEvent as AG2PrintEvent  # type: ignore
except Exception:  # pragma: no cover
    AG2PrintEvent = None  # type: ignore

# Import workflow configuration for agent visibility filtering
from core.workflow.workflow_manager import workflow_manager

# Enhanced logging setup
from logs.logging_config import get_core_logger, get_workflow_logger

# Get our enhanced loggers
logger = get_core_logger("simple_transport")
# Context-aware logger for agent messages category (used where applicable)
chat_logger = get_workflow_logger("agent_messages")

# ==================================================================================
# COMMUNICATION CHANNEL WRAPPER & MESSAGE FILTERING
# ==================================================================================


# ==================================================================================
# MAIN TRANSPORT CLASS
# ==================================================================================

class SimpleTransport:
    """
    Lean transport system focused solely on real-time UI communication.
    
    Features:
    - Message filtering (removes AutoGen noise)
    - WebSocket connection management
    - Event forwarding to the UI
    - Thread-safe singleton pattern
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls, *args, **kwargs):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    # Call __new__ and __init__ inside the lock
                    instance = super().__new__(cls)
                    instance.__init__(*args, **kwargs)
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        """Singleton initializer (idempotent)."""
        if getattr(self, '_initialized', False):
            return

        # Core structures
        self.connections: Dict[str, Dict[str, Any]] = {}

        # AG2-aligned input request callback registry
        self._input_request_registries: Dict[str, Dict[str, Any]] = {}

        # T1-T5: WebSocket protocol support structures
        self._input_callbacks: Dict[str, Any] = {}            # T1
        self._ui_tool_futures: Dict[str, Any] = {}            # T4
        self._sequence_counters: Dict[str, int] = {}          # T3

        # H1-H2: Hardening features
        self._message_queues: Dict[str, List[Dict[str, Any]]] = {}  # H1
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}         # H2
        self._max_queue_size = 100
        self._heartbeat_interval = 120

        # H4: Pre-connection buffering (delivery reliability)
        self._pre_connection_buffers: Dict[str, List[Dict[str, Any]]] = {}
        self._max_pre_connection_buffer = 200
        self._scheduled_flush_tasks: Dict[str, asyncio.Task] = {}

        # UI tool response correlation
        self.pending_ui_tool_responses: Dict[str, asyncio.Future] = {}

        self._initialized = True
        logger.info("🚀 SimpleTransport singleton initialized")
        
    # ==================================================================================
    # USER INPUT COLLECTION (Production-Ready)
    # ==================================================================================
    
    async def send_user_input_request(
        self,
        input_request_id: str,
        chat_id: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Send a dedicated user input request to the frontend.
        """
        event_data = {
            "type": "user_input_request",
            "data": {
                "input_request_id": input_request_id,
                "chat_id": chat_id,
                "payload": payload,
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.info(f"📤 Sent user input request {input_request_id} to chat {chat_id}")

    
    async def submit_user_input(self, input_request_id: str, user_input: str) -> bool:
        """
        Submit user input response for a pending input request.
        
        This method is called by the API endpoint when the frontend submits user input.
        """
        # First try orchestration registry respond callback(s)
        handled = False
        ack_chat_id = None
        for chat_id, reg in list(self._input_request_registries.items()):
            respond_cb = reg.get(input_request_id)
            if respond_cb:
                try:
                    # Support both async and sync lambdas assigned by AG2
                    result = respond_cb(user_input)
                    if asyncio.iscoroutine(result):
                        await result
                    handled = True
                    ack_chat_id = chat_id
                    logger.info(f"✅ [INPUT] Respond callback invoked for request {input_request_id} (chat {chat_id})")
                except Exception as e:
                    logger.error(f"❌ [INPUT] Respond callback failed {input_request_id}: {e}")
                finally:
                    # Remove after use
                    try:
                        del reg[input_request_id]
                    except Exception:
                        pass
                break
        if handled:
            # Emit chat.input_ack for B9/B10 protocol compliance
            if ack_chat_id:
                try:
                    await self.send_event_to_ui({
                        'kind': 'input_ack',
                        'request_id': input_request_id,
                        'corr': input_request_id,
                    }, ack_chat_id)
                except Exception as e:
                    logger.warning(f"Failed to emit input_ack: {e}")
            return True
        
        logger.error(f"❌ [INPUT] No active request found for {input_request_id}")
        return False

    # ------------------------------------------------------------------
    # Orchestration registry integration
    # ------------------------------------------------------------------
    def register_orchestration_input_registry(self, chat_id: str, registry: Dict[str, Any]) -> None:
        self._input_request_registries[chat_id] = registry

    def register_input_request(self, chat_id: str, request_id: str, respond_cb: Any) -> str:
        normalized_id = str(request_id) if request_id is not None else ""
        if not normalized_id or normalized_id.lower() == "none":
            normalized_id = uuid.uuid4().hex
            logger.debug(f"Generated fallback input request id {normalized_id} for chat {chat_id}")
        if chat_id not in self._input_request_registries:
            self._input_request_registries[chat_id] = {}
        self._input_request_registries[chat_id][normalized_id] = respond_cb
        logger.debug(f"Registered input request {normalized_id} for chat {chat_id}")
        return normalized_id
    
    
    @classmethod
    async def reset_instance(cls):
        async with cls._lock:
            cls._instance = None
            
    def should_show_to_user(self, agent_name: Optional[str], chat_id: Optional[str] = None) -> bool:
        """Check if a message should be shown to the user interface"""
        if not agent_name:
            return True  # Show system messages
        
        # Get the workflow type for this chat session
        workflow_name = None
        if chat_id and chat_id in self.connections:
            workflow_name = self.connections[chat_id].get("workflow_name")
        
        # If we have workflow type, use visual_agents filtering
        if workflow_name:
            try:
                config = workflow_manager.get_config(workflow_name)
                visual_agents = config.get("visual_agents")
                
                # If visual_agents is defined, only show messages from those agents
                if isinstance(visual_agents, list):
                    if not visual_agents:
                        logger.debug(f"🔍 visual_agents empty for {workflow_name}; allowing message from {agent_name}")
                        return True
                    # Normalize both the agent name and visual_agents list for comparison
                    # This matches the frontend normalization logic in ChatPage.js
                    def normalize_agent(name):
                        if not name:
                            return ''
                        return str(name).lower().replace('agent', '').replace(' ', '').strip()
                    
                    normalized_agent = normalize_agent(agent_name)
                    normalized_visual_agents = [normalize_agent(va) for va in visual_agents]
                    
                    is_allowed = normalized_agent in normalized_visual_agents
                    logger.debug(f"🔍 Backend visual_agents check: '{agent_name}' -> '{normalized_agent}' in {normalized_visual_agents} = {is_allowed}")
                    return is_allowed
            except FileNotFoundError:
                # If no specific config, default to showing the message
                pass
        
        return True

    # ==================================================================================
    # UNIFIED USER MESSAGE INGESTION
    # ==================================================================================
    async def process_incoming_user_message(self, *, chat_id: str, user_id: Optional[str], content: str, source: str = 'ws') -> None:
        """Persist and forward a free-form user message into the active workflow orchestration.

        This is used by both WebSocket (user.input.submit without request_id) and
        HTTP input endpoint. It appends the message to persistence so that future
        resume operations have it, and (if an orchestration is already running)
        attempts to surface it to the user proxy agent if available.
        """
        if not content:
            return
        index: Optional[int] = None
        try:
            from core.data.persistence_manager import AG2PersistenceManager
            pm = getattr(self, '_persistence_manager', None)
            if not pm:
                pm = AG2PersistenceManager()
                self._persistence_manager = pm
            coll = await pm._coll()  # type: ignore[attr-defined]
            now_dt = datetime.now(timezone.utc)
            bump = await coll.find_one_and_update(
                {"_id": chat_id},
                {"$inc": {"last_sequence": 1}, "$set": {"last_updated_at": now_dt}},
                return_document=ReturnDocument.AFTER,
            )
            seq = int(bump.get('last_sequence', 1)) if bump else 1
            index = seq - 1  # zero-based index for UI
            msg_doc = {
                'role': 'user',
                'name': 'user',
                'content': content,
                'timestamp': now_dt,
                'event_type': 'message.created',
                'sequence': seq,
                'source': source,
            }
            await coll.update_one({"_id": chat_id}, {"$push": {"messages": msg_doc}})
        except Exception as e:
            # Persistence failure should not block UI emission; fall back to in-memory sequence
            logger.error(f"Failed to persist user message for {chat_id}: {e}")
            try:
                # Use transport sequence counter (converted to zero-based)
                seq_fallback = self._get_next_sequence(chat_id)
                index = max(0, seq_fallback - 1)
            except Exception:
                index = 0
        # Always emit event (best-effort) even if persistence failed
        try:
            await self.send_event_to_ui({'kind': 'text', 'agent': 'user', 'content': content, 'index': index}, chat_id)
        except Exception as emit_err:
            logger.error(f"Failed to emit user message event for {chat_id}: {emit_err}")

    async def process_component_action(self, *, chat_id: str, enterprise_id: str, component_id: str, action_type: str, action_data: dict) -> Dict[str, Any]:
        """Apply a component action to context variables and emit acknowledgement.

        Returns a structured result indicating applied changes.
        """
        conn = self.connections.get(chat_id) or {}
        context = conn.get('context')
        applied: Dict[str, Any] = {}
        try:
            # Basic pattern: if action_data has 'set': {k: v} apply to context
            sets = action_data.get('set') if isinstance(action_data, dict) else None
            if context and isinstance(sets, dict):
                for k, v in sets.items():
                    try:
                        context.set(k, v)
                        applied[k] = v
                    except Exception as ce:
                        logger.debug(f"Context set failed for {k}: {ce}")
                # Persist a lightweight snapshot of changed keys ONLY
                try:
                    from core.data.persistence_manager import AG2PersistenceManager
                    pm = getattr(self, '_persistence_manager', None) or AG2PersistenceManager()
                    self._persistence_manager = pm
                    coll = await pm._coll()  # type: ignore[attr-defined]
                    now = datetime.now(timezone.utc)
                    snapshot_doc = {
                        'role': 'system',
                        'name': 'context',
                        'content': {'updated': applied, 'component_id': component_id, 'action_type': action_type},
                        'timestamp': now,
                        'event_type': 'context.updated',
                    }
                    await coll.update_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"$push": {"messages": snapshot_doc}, "$set": {"last_updated_at": now}})
                except Exception as pe:
                    logger.debug(f"Context snapshot persistence failed: {pe}")
            # Emit acknowledgement event
            await self.send_event_to_ui({
                'kind': 'component_action_ack',
                'component_id': component_id,
                'action_type': action_type,
                'applied': applied,
                'chat_id': chat_id,
            }, chat_id)
            return {'applied': applied, 'component_id': component_id, 'action_type': action_type}
        except Exception as e:
            logger.error(f"Component action processing failed for {chat_id}: {e}")
            raise
        
    # ==================================================================================
    # AG2 EVENT SENDING (Production)
    # ==================================================================================
    
    async def send_event_to_ui(self, event: Any, chat_id: Optional[str] = None) -> None:
        """
        Serializes and sends a raw AG2 event to the UI.
        This is the primary method for forwarding AG2 native events.
        """
        try:
            from core.events.unified_event_dispatcher import get_event_dispatcher  # local import to avoid cycle
            dispatcher = get_event_dispatcher()
            workflow_name = None
            if chat_id and chat_id in self.connections:
                workflow_name = self.connections[chat_id].get('workflow_name')

            # DEBUG: Log what we're processing
            event_type = type(event).__name__ if hasattr(event, '__class__') else 'dict'
            if isinstance(event, dict):
                event_kind = event.get('kind', 'unknown')
                logger.info(f"🔍 [TRANSPORT] Processing event: type={event_type}, kind={event_kind}, chat_id={chat_id}, dict_keys={list(event.keys()) if isinstance(event, dict) else 'N/A'}")
            else:
                logger.info(f"🔍 [TRANSPORT] Processing event: type={event_type}, chat_id={chat_id}")

            envelope = dispatcher.build_outbound_event_envelope(
                raw_event=event,
                chat_id=chat_id,
                get_sequence_cb=self._get_next_sequence,
                workflow_name=workflow_name,
            )
            if not envelope:
                logger.warning(f"❌ [TRANSPORT] No envelope created for event type={event_type}")
                return

            # Additional filtering (agent visibility) only for BaseEvent path where needed
            agent_name = None
            if isinstance(event, BaseEvent) and hasattr(event, 'sender') and getattr(event.sender, 'name', None):  # type: ignore
                agent_name = event.sender.name  # type: ignore
            if agent_name and not self.should_show_to_user(agent_name, chat_id):
                logger.debug(f"🚫 Filtered out AG2 event from agent '{agent_name}' for chat {chat_id}")
                return

            # Record performance metrics for tool calls (best-effort)
            try:
                et_name = type(event).__name__
                if any(token in et_name for token in ("Tool", "Function", "Call")):
                    tool_name = getattr(event, "tool_name", None)
                    if isinstance(tool_name, str) and tool_name.strip():
                        try:
                            from core.observability.performance_manager import get_performance_manager
                            perf = await get_performance_manager()
                            await perf.record_tool_call(chat_id or "unknown", tool_name.strip(), True)
                        except Exception:
                            pass
            except Exception:
                pass

            # Check for suppression flag from derived context hooks
            if envelope and isinstance(envelope, dict):
                data_payload = envelope.get('data')
                if isinstance(data_payload, dict) and data_payload.get('_mozaiks_hide'):
                    logger.info(f"🚫 [TRANSPORT] Suppressing hidden message (derived context trigger) for chat {chat_id}: {data_payload.get('content', 'no content')[:100]}")
                    return

            logger.info(f"📤 [TRANSPORT] Sending envelope: type={envelope.get('type')}, chat_id={chat_id}")
            await self._broadcast_to_websockets(envelope, chat_id)
        except Exception as e:
            logger.error(f"❌ Failed to serialize or send UI event: {e}\n{traceback.format_exc()}")

    def _extract_clean_content(self, message: Union[str, Dict[str, Any], Any]) -> str:
        """Extract clean content from AG2 UUID-formatted messages or other formats."""
        
        # Handle string messages (most common case)
        if isinstance(message, str):
            # Check for AG2's UUID format and extract only the 'content' part
            match = re.search(r"content='(.*?)'", message, re.DOTALL)
            if match:
                return match.group(1)
            return message  # Return original string if not in UUID format
        elif isinstance(message, dict):
            # Handle dictionary messages
            return message.get('content', str(message))
        else:
            # Handle any other type by converting to string
            return str(message)
        
    def _extract_agent_name_from_uuid_content(self, content: str) -> Optional[str]:
        """Extract actual agent name from AG2 UUID-formatted message content."""
        import re
        
        # AG2 format: "uuid=UUID('...') content='...' sender='AgentName' recipient='...'"
        # Look for sender='AgentName' pattern
        sender_match = re.search(r"sender='([^']+)'", content)
        if sender_match:
            return sender_match.group(1)
        
        # Fallback patterns if above doesn't work
        sender_match_quotes = re.search(r'sender="([^"]+)"', content)
        if sender_match_quotes:
            return sender_match_quotes.group(1)
        
        return None  # no agent found
        
    async def _broadcast_to_websockets(self, event_data: Dict[str, Any], target_chat_id: Optional[str] = None) -> None:
        """Broadcast event data to relevant WebSocket connections."""
        active_connections = list(self.connections.items())
        
        # If a chat_id is specified, only send to that connection
        if target_chat_id:
            connection_info = self.connections.get(target_chat_id)
            if connection_info and connection_info.get("websocket"):
                # H1: Use message queuing with backpressure control
                await self._queue_message_with_backpressure(target_chat_id, event_data)
                await self._flush_message_queue(target_chat_id)
            else:
                # H4: Buffer message until the websocket connects
                buf = self._pre_connection_buffers.setdefault(target_chat_id, [])
                buf.append(event_data)
                if len(buf) > self._max_pre_connection_buffer:
                    # Drop oldest while keeping newest insight
                    overflow = len(buf) - self._max_pre_connection_buffer
                    del buf[0:overflow]
                    logger.warning(f"🧹 Dropped {overflow} pre-connection buffered messages for {target_chat_id}")
                logger.debug(f"🕑 Buffered pre-connection message for {target_chat_id} (size={len(buf)})")
            return

        # Otherwise, broadcast to all connections
        for chat_id, info in active_connections:
            websocket = info.get("websocket")
            if websocket:
                # H1: Use message queuing with backpressure control
                await self._queue_message_with_backpressure(chat_id, event_data)
                await self._flush_message_queue(chat_id)

    def _stringify_unknown(self, obj: Any) -> str:
        """Safely convert any object to a string for logging/transport."""
        try:
            if obj is None:
                return ""
            if isinstance(obj, (str, int, float, bool)):
                return str(obj)
            # Try JSON first with default=str to preserve structure
            return json.dumps(obj, default=str)
        except Exception:
            try:
                return str(obj)
            except Exception:
                return "<unserializable>"

    def _serialize_ag2_events(self, obj: Any) -> Any:
        """Convert AG2 event objects to JSON-serializable format."""
        try:
            # Lazy imports (wrapped) so absence of autogen doesn't break app start.
            try:
                from autogen.events.agent_events import TextEvent, InputRequestEvent  # type: ignore
            except Exception:  # pragma: no cover - autogen optional
                TextEvent = InputRequestEvent = tuple()  # type: ignore

            # Optional tool events (some versions place them elsewhere)
            ToolResponseEvent = None  # default
            for mod_path in [
                "autogen.events.tool_events",
                "autogen.events.agent_events",  # fallback if class relocated
            ]:
                if ToolResponseEvent:
                    break
                try:  # pragma: no cover - defensive import paths
                    mod = __import__(mod_path, fromlist=["ToolResponseEvent"])
                    ToolResponseEvent = getattr(mod, "ToolResponseEvent", None)
                except Exception:
                    continue

            # Primitive fast-path
            if obj is None or isinstance(obj, (str, int, float, bool)):
                return obj

            # Dict / list recursive handling
            if isinstance(obj, dict):
                return {k: self._serialize_ag2_events(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple, set)):
                return [self._serialize_ag2_events(v) for v in list(obj)]

            # Specific AG2 event shapes
            def _extract_sender(o):
                s = getattr(o, "sender", None)
                try:
                    if s is not None and hasattr(s, "name"):
                        return getattr(s, "name")
                except Exception:
                    pass
                return self._stringify_unknown(s)

            def _extract_recipient(o):
                r = getattr(o, "recipient", None)
                try:
                    if r is not None and hasattr(r, "name"):
                        return getattr(r, "name")
                except Exception:
                    pass
                return self._stringify_unknown(r)

            cls_name = obj.__class__.__name__

            # TextEvent
            try:
                if "TextEvent" in cls_name:
                    return {
                        "uuid": str(getattr(obj, "uuid", "")),
                        "content": self._stringify_unknown(getattr(obj, "content", None)),
                        "sender": _extract_sender(obj),
                        "recipient": _extract_recipient(obj),
                        "_ag2_event_type": "TextEvent",
                    }
            except Exception:
                pass

            # InputRequestEvent
            if InputRequestEvent and isinstance(obj, InputRequestEvent):  # type: ignore[arg-type]
                return {
                    "uuid": str(getattr(obj, "uuid", "")),
                    "prompt": self._stringify_unknown(getattr(obj, "prompt", None)),
                    "password": None,  # never forward secrets
                    "type": self._stringify_unknown(getattr(obj, "type", None)),
                    "_ag2_event_type": "InputRequestEvent",
                }

            # ToolResponseEvent (covers tool outputs)
            if ToolResponseEvent and isinstance(obj, ToolResponseEvent):  # type: ignore[arg-type]
                return {
                    "uuid": str(getattr(obj, "uuid", "")),
                    "tool_name": self._stringify_unknown(getattr(obj, "tool_name", None)),
                    "content": self._stringify_unknown(getattr(obj, "content", getattr(obj, "result", None))),
                    "sender": _extract_sender(obj),
                    "recipient": _extract_recipient(obj),
                    "_ag2_event_type": "ToolResponseEvent",
                }

            # Generic event-like objects with a small public attribute surface.
            public_attrs = {}
            # Avoid exploding on very large objects; cap attributes
            attr_count = 0
            for name in dir(obj):
                if name.startswith("_"):
                    continue
                if attr_count > 25:
                    break
                try:
                    value = getattr(obj, name)
                except Exception:
                    continue
                # Skip callables
                if callable(value):
                    continue
                attr_count += 1
                public_attrs[name] = self._serialize_ag2_events(value)

            if public_attrs:
                public_attrs["_ag2_event_type"] = cls_name
                return public_attrs

            # Fallback textual representation
            return self._stringify_unknown(obj)
        except Exception:
            # Final safety fallback
            return self._stringify_unknown(obj)

    async def _handle_resume_request(self, chat_id: str, last_client_index: int, websocket) -> None:
        """Resume protocol aligned with AG2 GroupChat resume semantics.

        We DO NOT compute sequence diffs via a bespoke diff endpoint anymore.
        Instead we:
          1. Load the authoritative persisted message list for the chat.
          2. Determine the slice of messages the client is missing based on the
             last message *index* the client reports it has (last_client_index).
             The client sends -1 if it has none.
          3. Re-emit each missing message to the client as chat.text with a
             replay flag and a stable index. We keep an internal sequence counter
             but its primary purpose is ordering of new live events; indexes are
             sufficient for replay correctness.
          4. Emit chat.resume_boundary summarizing counts and boundaries.

        This mirrors AG2's requirement that the *messages array* is the source
        of truth for preparing agents via GroupChatManager.resume, while giving
        the WebSocket consumer a minimal, deterministic replay mechanism.
        """
        try:
            from core.data.persistence_manager import AG2PersistenceManager
            if not hasattr(self, '_persistence_manager'):
                self._persistence_manager = AG2PersistenceManager()
            conn_meta = self.connections.get(chat_id) or {}
            enterprise_id = conn_meta.get('enterprise_id')
            if not enterprise_id:
                raise RuntimeError("Missing enterprise_id for resume")

            # Fetch full message history (in-progress or completed allowed).
            # We intentionally do not restrict to IN_PROGRESS so a user can
            # re-open a completed chat in a read-only fashion.
            coll = await self._persistence_manager._coll()  # type: ignore[attr-defined]
            doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"messages": 1})
            full_messages: List[Dict[str, Any]] = doc.get("messages", []) if doc else []

            if last_client_index < -1:
                last_client_index = -1  # sanitize

            # Determine missing slice (exclusive of last_client_index)
            start_idx = last_client_index + 1
            if start_idx < 0:
                start_idx = 0
            missing = full_messages[start_idx:]

            replayed_count = 0
            last_idx_sent = last_client_index
            for idx_offset, env in enumerate(missing):
                absolute_index = start_idx + idx_offset
                last_idx_sent = absolute_index
                try:
                    role = env.get('role')
                    if role == 'assistant':
                        agent_name = env.get('agent_name') or env.get('name') or 'assistant'
                    else:
                        agent_name = 'user'
                    await websocket.send_json({
                        'type': 'chat.text',
                        'data': {
                            'agent': agent_name,
                            'content': env.get('content'),
                            'index': absolute_index,
                            'replay': True,
                            'chat_id': chat_id,
                        },
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
                    replayed_count += 1
                except Exception as re:
                    logger.warning(f"Failed to replay message index={absolute_index}: {re}")

            await websocket.send_json({
                'type': 'chat.resume_boundary',
                'data': {
                    'chat_id': chat_id,
                    'replayed_messages': replayed_count,
                    'last_message_index': last_idx_sent,
                    'total_messages': len(full_messages)
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

            # Real-time sequence continuity: if we already had a higher
            # counter (e.g. resumed mid-flight) we do not reduce it.
            if replayed_count:
                existing_seq = self._sequence_counters.get(chat_id, 0)
                if existing_seq < last_idx_sent + 1:
                    self._sequence_counters[chat_id] = last_idx_sent + 1

            logger.info(
                f"✅ Resume complete chat={chat_id} sent={replayed_count} missing_from>{last_client_index} now_at_index={last_idx_sent}"
            )
        except Exception as e:
            logger.error(f"❌ Resume failed chat={chat_id}: {e}")
            raise

    def _validate_inbound_message(self, message_data: dict) -> bool:
        """H3: Validate inbound WebSocket message schema"""
        if not isinstance(message_data, dict):
            return False
        
        msg_type = message_data.get('type') or message_data.get('kind')
        if not msg_type or not isinstance(msg_type, str):
            return False
        
        # T1: Validate required fields based on message type
        if msg_type == "user.input.submit":
            # Allow either (a) input_request response with request_id OR (b) free-form user chat message
            base_ok = "chat_id" in message_data and "text" in message_data
            if not base_ok:
                return False
            # request_id optional (only when responding to InputRequestEvent)
            return True
        
        elif msg_type == "ui_tool_response":
            # UI tool response from frontend (Approve/Cancel/Submit buttons)
            # Must have ui_tool_id or eventId to correlate with pending wait_for_ui_tool_response
            return ("ui_tool_id" in message_data or "eventId" in message_data)
        
        elif msg_type == "client.resume":
            # Canonical resume field: lastClientIndex (0-based index of last message the client has)
            return all(field in message_data for field in ["chat_id", "lastClientIndex"]) and isinstance(message_data.get("lastClientIndex"), int)
        
        # Unknown message types are invalid
        return False
        
    async def send_error(
        self,
        error_message: str,
        error_code: str = "GENERAL_ERROR",
        chat_id: Optional[str] = None
    ) -> None:
        """Send error message to UI via WebSocket"""
        event_data = {
            "type": "error",
            "data": {
                "message": error_message,
                "error_code": error_code,
                "chat_id": chat_id
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.error(f"❌ Error: {error_message}")
        
    async def send_status(
        self,
        status_message: str,
        status_type: str = "info",
        chat_id: Optional[str] = None
    ) -> None:
        """Send status update to UI via WebSocket"""
        event_data = {
            "type": "status",
            "data": {
                "message": status_message,
                "status_type": status_type,
                "chat_id": chat_id
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self._broadcast_to_websockets(event_data, chat_id)
        logger.info(f"ℹ️ Status: {status_message}")
    
    # ==================================================================================
    # CONNECTION MANAGEMENT METHODS
    # ==================================================================================
    
    async def handle_websocket(
        self,
        websocket: WebSocket,
        chat_id: str,
        user_id: str,
        workflow_name: str,
        enterprise_id: Optional[str] = None
    ) -> None:
        """Handle WebSocket connection for real-time communication"""
        await websocket.accept()
        self.connections[chat_id] = {
            "websocket": websocket,
            "user_id": user_id,
            "workflow_name": workflow_name,
            "enterprise_id": enterprise_id,
            "active": True,
        }
        logger.info(f"🔌 WebSocket connected for chat_id: {chat_id}")
        
        # H2: Start heartbeat for connection
        await self._start_heartbeat(chat_id, websocket)
        
        # H1: Initialize message queue for backpressure control
        self._message_queues[chat_id] = []

        # H4: Flush any pre-connection buffered messages (if orchestration
        # started emitting before the UI finished the handshake)
        if chat_id in self._pre_connection_buffers:
            buffered = self._pre_connection_buffers.pop(chat_id)
            if buffered:
                logger.info(f"📤 Flushing {len(buffered)} pre-connection buffered messages for {chat_id}")
                for msg in buffered:
                    await self._queue_message_with_backpressure(chat_id, msg)
                await self._flush_message_queue(chat_id)

        # H5: Auto-resume for IN_PROGRESS chats (check status and restore chat history)
        await self._auto_resume_if_needed(chat_id, websocket, enterprise_id)
        
        try:
            # Inbound loop: receive JSON control messages from client
            while True:
                try:
                    msg = await websocket.receive_text()
                except Exception as recv_err:
                    # Client disconnected
                    raise recv_err
                if not msg:
                    await asyncio.sleep(0.05)
                    continue
                try:
                    data = json.loads(msg)
                except Exception:
                    logger.debug(f"⚠️ Received non-JSON message on WS chat {chat_id}: {msg[:80]}")
                    continue
                # H3: Validate message schema
                if not self._validate_inbound_message(data):
                    await websocket.send_json({
                        "type": "chat.error",
                        "data": {
                            "message": "Invalid message schema",
                            "error_code": "SCHEMA_VALIDATION_FAILED"
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    continue

                mtype = data.get('type') or data.get('kind')
                # Handle user input submission (alternative to REST endpoint)
                if mtype in ("user.input.submit", "user_input_submit"):
                    req_id = data.get('input_request_id') or data.get('request_id')
                    text = (data.get('text') or data.get('user_input') or "").strip()
                    if req_id:
                        # Treat as response to AG2 InputRequestEvent
                        try:
                            ok = await self.submit_user_input(req_id, text)
                            await websocket.send_json({
                                "type": "ack.input",
                                "data": {"input_request_id": req_id, "status": "accepted" if ok else "rejected"},
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                        except Exception as ie:
                            logger.error(f"❌ Failed to process inbound user input {req_id}: {ie}")
                    else:
                        # Free-form user message (no pending request). Persist & feed to orchestrator.
                        try:
                            await self.process_incoming_user_message(
                                chat_id=chat_id,
                                user_id=self.connections.get(chat_id, {}).get('user_id'),
                                content=text,
                                source='ws'
                            )
                            await websocket.send_json({
                                "type": "chat.input_ack",
                                "data": {"chat_id": chat_id, "status": "accepted"},
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                        except Exception as e:
                            logger.error(f"Failed to process free-form user message for {chat_id}: {e}")
                            await websocket.send_json({
                                "type": "chat.error",
                                "data": {"message": "User message failed", "error_code": "USER_MESSAGE_FAILED"},
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                    continue
                
                # Handle UI tool response submission (Approve/Cancel/Submit buttons from frontend)
                if mtype == "ui_tool_response":
                    event_id = data.get('eventId') or data.get('ui_tool_id')
                    response_data = data.get('response', {})
                    if event_id:
                        try:
                            ok = await self.submit_ui_tool_response(event_id, response_data)
                            logger.info(f"✅ UI tool response received for event {event_id}: {ok}")
                            await websocket.send_json({
                                "type": "ack.ui_tool_response",
                                "data": {"eventId": event_id, "status": "accepted" if ok else "rejected"},
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                        except Exception as uie:
                            logger.error(f"❌ Failed to process UI tool response {event_id}: {uie}")
                            await websocket.send_json({
                                "type": "chat.error",
                                "data": {"message": "UI tool response failed", "error_code": "UI_TOOL_RESPONSE_FAILED"},
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                    continue
                
                # Client resume handshake (B11)
                if mtype == "client.resume":
                    try:
                        last_client_index = data.get("lastClientIndex")
                        if not isinstance(last_client_index, int):
                            raise ValueError("lastClientIndex must be int")
                        await self._handle_resume_request(chat_id, last_client_index, websocket)
                    except Exception as re:
                        logger.error(f"❌ Failed to process client.resume for chat {chat_id}: {re}")
                        await websocket.send_json({
                            "type": "chat.error",
                            "data": {"message": f"Resume failed: {str(re)}", "error_code": "RESUME_FAILED"},
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    continue
                # Unknown control message -> ignore silently
        except Exception as e:
            logger.warning(f"WebSocket error for chat {chat_id}: {e}")
        finally:
            # H1-H2: Clean up connection resources (heartbeat, message queues, etc.)
            await self._cleanup_connection(chat_id)
            logger.info(f"🔌 WebSocket disconnected for chat_id: {chat_id}")

    # ==================================================================================
    # WORKFLOW INTEGRATION METHODS
    # ==================================================================================
    
    async def handle_user_input_from_api(
        self,
        chat_id: str,
        user_id: Optional[str],
        workflow_name: str,
        message: Optional[str],
        enterprise_id: str
    ) -> Dict[str, Any]:
        """
        Handle user input from the POST API endpoint with smart routing

        Checks if there's an active AG2 GroupChat session waiting for input.
        If yes, passes message to existing session. If no, starts new workflow.
        """
        try:
            # Check if there's an active AG2 session waiting for user input
            has_active_session = bool(self._input_request_registries.get(chat_id))

            # Also check if there are pending input callbacks for this chat
            active_callbacks = False
            if chat_id in self._input_request_registries:
                active_callbacks = bool(self._input_request_registries[chat_id])

            logger.info(f"🔀 [SMART_ROUTING] chat={chat_id} has_registry={has_active_session} has_callbacks={active_callbacks}")

            if has_active_session and active_callbacks:
                # Route to existing AG2 session via WebSocket callback mechanism
                logger.info(f"🔄 [SMART_ROUTING] Continuing existing AG2 session for chat {chat_id}")

                # Get any available request_id from the registry
                registry = self._input_request_registries.get(chat_id, {})
                if registry:
                    # Get the first available request_id
                    request_id = next(iter(registry.keys()))

                    # Submit the input directly to the existing AG2 session - no UI echo needed
                    success = await self.submit_user_input(request_id, message or "")

                    if success:
                        return {"status": "success", "chat_id": chat_id, "message": "Input passed to existing AG2 session.", "route": "existing_session"}
                    else:
                        logger.warning(f"⚠️ [SMART_ROUTING] Failed to submit input to existing session, falling back to new workflow")

            # No active session or callback failed - start new workflow
            logger.info(f"🚀 [SMART_ROUTING] Starting new workflow for chat {chat_id}")

            from core.workflow.orchestration_patterns import run_workflow_orchestration

            # Only persist and echo user message when starting NEW workflows
            # For existing sessions, the message goes directly to AG2 via callback
            if message:
                try:
                    await self.process_incoming_user_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        content=message,
                        source='http'
                    )
                except Exception as persist_err:
                    logger.debug(f"Early persistence of user message failed (non-fatal): {persist_err}")

            # Launch orchestration (will also seed initial_messages including the persisted one)
            await run_workflow_orchestration(
                workflow_name=workflow_name,
                enterprise_id=enterprise_id,
                chat_id=chat_id,
                user_id=user_id,
                initial_message=None  # already persisted & sent upstream
            )

            return {"status": "success", "chat_id": chat_id, "message": "Workflow started successfully.", "route": "new_workflow"}

        except Exception as e:
            logger.error(f"❌ User input handling failed for chat {chat_id}: {e}\n{traceback.format_exc()}")
            await self.send_error(
                error_message=f"An internal error occurred: {e}",
                error_code="WORKFLOW_EXECUTION_FAILED",
                chat_id=chat_id
            )
            return {"status": "error", "chat_id": chat_id, "message": str(e)}

    # ==================================================================================
    # SIMPLIFIED EVENT API - WEBSOCKET ONLY
    # ==================================================================================
    
    async def send_chat_message(
        self,
        message: str,
        agent_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Send chat message to user interface"""
        # Create properly formatted event data with 'kind' field for envelope builder
        event_data = {
            "kind": "text",
            "agent": agent_name or "Agent", 
            "content": str(message),
            "chat_id": chat_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if metadata:
            event_data["metadata"] = metadata

        # Enhanced logging for debugging UI rendering
        logger.info(f"💬 Sending chat message: kind={event_data['kind']} agent='{agent_name}' content_len={len(message)} content_preview='{message[:50]}...'")

        await self.send_event_to_ui(event_data, chat_id)
    
    async def send_simple_text_message(self, content: str, chat_id: Optional[str] = None, agent_name: Optional[str] = None) -> None:
        """
        Send simple text message using AG2's official approach with agent context.
        Based on: https://docs.ag2.ai/latest/docs/_blogs/2025-01-10-WebSockets/
        """
        if chat_id and chat_id in self.connections:
            # This method is now simplified as the main send_to_ui handles formatting
            await self.send_chat_message(content, agent_name or "Assistant", chat_id)
    
    # ==================================================================================
    # UI TOOL EVENT HANDLING (Companion to user input)
    # ==================================================================================

    def _get_or_create_persistence_manager(self):
        """Return cached AG2PersistenceManager instance (lazy import)."""
        pm = getattr(self, "_persistence_manager", None)
        if pm is None:
            from core.data.persistence_manager import AG2PersistenceManager
            pm = AG2PersistenceManager()
            self._persistence_manager = pm
        return pm

    async def _resolve_chat_context(
        self,
        chat_id: Optional[str],
        *,
        pm,
        payload_workflow: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Resolve enterprise/workflow for a chat regardless of live connection."""
        if not chat_id:
            return None, payload_workflow

        enterprise_id: Optional[str] = None
        workflow_name: Optional[str] = payload_workflow

        conn = self.connections.get(chat_id)
        if conn:
            raw_ent = conn.get("enterprise_id")
            if raw_ent:
                enterprise_id = str(raw_ent)
            if not workflow_name:
                workflow_name = conn.get("workflow_name")

        if enterprise_id and workflow_name:
            return enterprise_id, workflow_name

        try:
            coll = await pm._coll()
            doc = await coll.find_one({"_id": chat_id}, {"enterprise_id": 1, "workflow_name": 1})
            if doc:
                if not enterprise_id and doc.get("enterprise_id") is not None:
                    enterprise_id = str(doc.get("enterprise_id"))
                if not workflow_name and doc.get("workflow_name"):
                    workflow_name = doc.get("workflow_name")
        except Exception as ctx_err:
            logger.debug(f"dY'\" [UI_TOOL] Context lookup failed for chat {chat_id}: {ctx_err}")

        if chat_id in self.connections:
            conn = self.connections[chat_id]
            if enterprise_id and not conn.get("enterprise_id"):
                conn["enterprise_id"] = enterprise_id
            if workflow_name and not conn.get("workflow_name"):
                conn["workflow_name"] = workflow_name

        return enterprise_id, workflow_name

    async def _persist_ui_tool_state(
        self,
        *,
        chat_id: Optional[str],
        tool_name: str,
        event_id: str,
        display_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Persist latest artifact/inline UI payload for chat restoration."""
        if not chat_id or not isinstance(payload, dict):
            return

        mode_candidates = [
            display_type,
            payload.get("display"),
            payload.get("mode"),
        ]
        display_mode = next(
            (m.strip() for m in mode_candidates if isinstance(m, str) and m.strip()),
            None,
        )
        normalized_mode = display_mode.lower() if display_mode else None
        persist_flag = bool(payload.get("persist_ui_state")) if isinstance(payload, dict) else False

        if not normalized_mode and not persist_flag:
            return
        if normalized_mode not in ("artifact", "inline") and not persist_flag:
            return

        if not normalized_mode:
            normalized_mode = "artifact"

        try:
            pm = self._get_or_create_persistence_manager()
        except Exception as pm_err:  # pragma: no cover
            logger.debug(f"dY'\" [UI_TOOL] Persistence manager unavailable: {pm_err}")
            return

        try:
            enterprise_id, workflow_name = await self._resolve_chat_context(
                chat_id,
                pm=pm,
                payload_workflow=payload.get("workflow_name"),
            )
            if not enterprise_id:
                logger.debug(f"dY'\" [UI_TOOL] Missing enterprise_id for chat {chat_id}; skipping last_artifact persist")
                return

            try:
                sanitized_payload = json.loads(json.dumps(payload))
            except Exception:
                sanitized_payload = payload

            artifact_doc = {
                "ui_tool_id": tool_name,
                "event_id": event_id,
                "display": normalized_mode,
                "workflow_name": payload.get("workflow_name") or workflow_name,
                "payload": sanitized_payload,
            }
            await pm.update_last_artifact(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                artifact=artifact_doc,
            )
        except Exception as persist_err:
            logger.debug(f"dY'\" [UI_TOOL] Failed to persist last_artifact for chat {chat_id}: {persist_err}")
    
    async def send_ui_tool_event(
        self,
        event_id: str,
        chat_id: Optional[str],
        tool_name: str,
        component_name: str,
        display_type: str,
        payload: Dict[str, Any],
        agent_name: Optional[str] = None
    ) -> None:
        """
        Emit a tool_call event to the frontend using the strict chat.tool_call protocol.
        """
        # Extract agent_name from payload if not explicitly provided
        if not agent_name and isinstance(payload, dict):
            agent_name = payload.get("agent_name")
        
        # Build a standardized AG2 tool_call payload
        event = {
            "kind": "tool_call",
            "tool_name": tool_name,
            "component_type": component_name,
            "awaiting_response": True,
            "payload": payload,
            "corr": event_id,
            "display": display_type,
            "display_type": display_type,
        }
        
        # Set agent field if available
        if agent_name:
            event["agent"] = agent_name

        payload_keys = list(payload.keys()) if isinstance(payload, dict) else []
        logger.info(
            f"🛠️ [UI_TOOL] Emitting tool_call event: tool={tool_name}, component={component_name}, display={display_type}, event_id={event_id}, chat_id={chat_id}, payload_keys={payload_keys[:12]}"
        )

        try:
            await self._persist_ui_tool_state(
                chat_id=chat_id,
                tool_name=tool_name,
                event_id=event_id,
                display_type=display_type,
                payload=payload,
            )
        except Exception as persist_exc:  # pragma: no cover
            logger.debug(f"🧩 [UI_TOOL] Persist hook raised for chat {chat_id}: {persist_exc}")

        # Delegate to core event sender for namespacing and sequence handling
        await self.send_event_to_ui(event, chat_id)

    @classmethod
    async def wait_for_ui_tool_response(cls, event_id: str, timeout: Optional[float] = 300.0) -> Dict[str, Any]:
        """Await a UI tool response with an optional timeout.

        Args:
            event_id: Correlation id originally sent in the ui_tool_event.
            timeout: Seconds to wait before raising TimeoutError (None = wait forever).
        """
        instance = await cls.get_instance()
        if not instance:
            raise RuntimeError("SimpleTransport instance not available")

        if event_id not in instance.pending_ui_tool_responses:
            instance.pending_ui_tool_responses[event_id] = asyncio.Future()

        fut = instance.pending_ui_tool_responses[event_id]
        try:
            response_data = await asyncio.wait_for(fut, timeout=timeout) if timeout else await fut
            return response_data
        except asyncio.TimeoutError:
            if not fut.done():
                fut.set_exception(asyncio.TimeoutError("UI tool response timed out"))
            logger.error(f"⏰ UI tool response timed out for event {event_id}")
            raise
        finally:
            instance.pending_ui_tool_responses.pop(event_id, None)

    async def submit_ui_tool_response(self, event_id: str, response_data: Dict[str, Any]) -> bool:
        """
        Submit response data for a pending UI tool event.
        
        This method is called by an API endpoint when the frontend submits data
        from an interactive UI component.
        """
        if event_id in self.pending_ui_tool_responses:
            future = self.pending_ui_tool_responses[event_id]
            if not future.done():
                future.set_result(response_data)
                logger.info(f"✅ [UI_TOOL] Submitted response for event {event_id}")
                return True
            else:
                logger.warning(f"⚠️ [UI_TOOL] Event {event_id} already completed")
                return False
        else:
            logger.warning(f"⚠️ [UI_TOOL] No pending event found for {event_id}")
            return False

    # T1: WebSocket message handling for input requests
    async def _handle_websocket_message(self, websocket, message_data: dict, session) -> None:
        """Handle inbound WebSocket messages from client."""
        if not self._validate_inbound_message(message_data):
            await self._send_error(websocket, "SCHEMA_VALIDATION_FAILED", "Invalid message format")
            return
        
        message_type = message_data.get("type")
        chat_id = message_data.get("chat_id")
        
        if message_type == "user.input.submit":
            # Handle user input submission
            request_id_raw = message_data.get("request_id")
            request_id: Optional[str] = request_id_raw if isinstance(request_id_raw, str) and request_id_raw else None
            text = message_data.get("text", "")

            # Find and invoke callback
            callback = self._input_callbacks.get(request_id) if request_id else None
            if callback and request_id:
                try:
                    await callback(text)
                except Exception as e:
                    logger.error(f"Error invoking input callback for {request_id}: {e}")
                finally:
                    # Clean up after use
                    if request_id in self._input_callbacks:
                        self._input_callbacks.pop(request_id, None)
            else:
                logger.warning(f"No callback found for input request {request_id}")
        
        
        elif message_type == "client.resume":
            # Handle resume request using canonical lastClientIndex
            last_client_index = message_data.get("lastClientIndex")
            if not isinstance(last_client_index, int):
                logger.warning(f"Invalid resume payload (lastClientIndex missing or non-int): {message_data}")
                await self._send_error(websocket, "RESUME_FAILED", "Invalid lastClientIndex for resume request")
                return
            if not chat_id:
                logger.warning(f"Resume request missing chat_id: {message_data}")
                await self._send_error(websocket, "RESUME_FAILED", "Missing chat_id for resume request")
                return
            await self._handle_resume_request(chat_id, last_client_index, websocket)
        
        else:
            logger.warning(f"Unknown message type: {message_type}")

    async def _send_error(self, websocket, error_code: str, message: str) -> None:
        """Send error message to client."""
        error_data = {
            "type": "chat.error",
            "data": {
                "message": message,
                "error_code": error_code,
                "recoverable": True
            }
        }
        try:
            await websocket.send_json(error_data)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

    # T3: Sequence tracking methods for resume capability
    def _get_next_sequence(self, chat_id: str) -> int:
        """Get the next sequence number for a chat session."""
        if chat_id not in self._sequence_counters:
            self._sequence_counters[chat_id] = 0
        self._sequence_counters[chat_id] += 1
        return self._sequence_counters[chat_id]
    
    def _reset_sequence_after_resume(self, chat_id: str, last_seq: int) -> None:
        """Reset sequence counter after resume to continue from last sequence."""
        self._sequence_counters[chat_id] = last_seq
        logger.info(f"Reset sequence counter for {chat_id} to {last_seq}")
    
    async def _get_chat_coll(self):
        """Get MongoDB chat collection for persistence operations."""
        # Production: connect to actual persistence layer
        try:
            from core.data.persistence_manager import AG2PersistenceManager
            if not hasattr(self, '_persistence_manager'):
                self._persistence_manager = AG2PersistenceManager()
            
            await self._persistence_manager.persistence._ensure_client()
            client = self._persistence_manager.persistence.client
            if client is None:
                logger.warning("MongoDB client unavailable for chat collection")
                return None
            return client["MozaiksAI"]["ChatSessions"]
        except Exception as e:
            logger.error(f"Failed to get chat collection: {e}")
            return None
 
    # H1: Server backpressure implementation
    async def _check_backpressure(self, chat_id: str) -> bool:
        """Check if connection should be throttled due to backpressure."""
        if chat_id not in self._message_queues:
            self._message_queues[chat_id] = []
        
        queue_size = len(self._message_queues[chat_id])
        if queue_size >= self._max_queue_size:
            logger.warning(f"🚨 Backpressure triggered for {chat_id}: queue size {queue_size}")
            # Drop oldest messages to make room
            dropped = queue_size - self._max_queue_size + 10  # Keep some buffer
            self._message_queues[chat_id] = self._message_queues[chat_id][dropped:]
            logger.info(f"📉 Dropped {dropped} queued messages for {chat_id}")
            return True
        return False

    async def _queue_message_with_backpressure(self, chat_id: str, message_data: Dict[str, Any]) -> bool:
        """Queue message with backpressure control."""
        if await self._check_backpressure(chat_id):
            # Connection is under backpressure - message may have been dropped
            pass
        # Early serialization guard: ensure no raw AG2 objects linger in queue.
        if not isinstance(message_data, (dict, list, tuple, str, int, float, bool, type(None))):
            try:
                message_data = self._serialize_ag2_events(message_data)
            except Exception:
                message_data = {"type": "log", "data": {"message": self._stringify_unknown(message_data)}}

        self._message_queues[chat_id].append(message_data)
        return True

    async def _flush_message_queue(self, chat_id: str) -> None:
        """Flush queued messages for a connection."""
        if chat_id not in self._message_queues or not self._message_queues[chat_id]:
            return
        
        if chat_id in self.connections:
            websocket = self.connections[chat_id]["websocket"]
            messages_to_send = self._message_queues[chat_id].copy()
            self._message_queues[chat_id].clear()
            
            for message in messages_to_send:
                try:
                    # Check if message is already in proper format for WebSocket
                    if isinstance(message, dict) and 'type' in message and 'data' in message:
                        # Ensure the 'data' payload is JSON-serializable (may contain AG2 objects)
                        try:
                            safe_message = message.copy()
                            safe_message['data'] = self._serialize_ag2_events(message['data'])
                            
                            # Extract agent name from data payload and add to top-level envelope for frontend attribution
                            if isinstance(safe_message.get('data'), dict):
                                agent_from_data = safe_message['data'].get('agent') or safe_message['data'].get('sender')
                                if agent_from_data and isinstance(agent_from_data, str):
                                    safe_message['agent'] = agent_from_data
                                elif 'agent' not in safe_message:
                                    # Fallback to generic if no agent in data
                                    safe_message['agent'] = 'Agent'
                            
                            if safe_message.get('type') == 'chat.tool_call':
                                payload_obj = safe_message.get('data', {}).get('payload', {})
                                payload_keys = list(payload_obj.keys()) if isinstance(payload_obj, dict) else []
                                logger.info('TRANSPORT payload keys before send: %s', payload_keys[:12])
                            await websocket.send_json(safe_message)
                        except Exception:
                            # Fallback: attempt to serialize whole message as a last resort
                            try:
                                await websocket.send_json(self._serialize_ag2_events(message))
                            except Exception:
                                raise
                    else:
                        serialized_message = self._serialize_ag2_events(message)
                        await websocket.send_json(serialized_message)
                except Exception as e:
                    logger.error(f"Failed to send queued message to {chat_id}: {e}. Will retry shortly.")
                    # Re-queue remaining (including current) for retry
                    remaining = [message] + messages_to_send[messages_to_send.index(message)+1:]
                    self._message_queues[chat_id] = remaining + self._message_queues[chat_id]
                    # Schedule a retry flush with small backoff
                    self._schedule_flush_retry(chat_id)
                    break

    def _schedule_flush_retry(self, chat_id: str, delay: float = 0.5) -> None:
        """Schedule a single retry flush if not already pending."""
        if chat_id in self._scheduled_flush_tasks and not self._scheduled_flush_tasks[chat_id].done():
            return  # already scheduled
        async def _delayed():
            try:
                await asyncio.sleep(delay)
                await self._flush_message_queue(chat_id)
            finally:
                # Clear handle so future retries can be scheduled
                self._scheduled_flush_tasks.pop(chat_id, None)
        self._scheduled_flush_tasks[chat_id] = asyncio.create_task(_delayed())

    # H2: Heartbeat implementation
    async def _start_heartbeat(self, chat_id: str, websocket) -> None:
        """Start heartbeat task for a connection."""
        if chat_id in self._heartbeat_tasks:
            self._heartbeat_tasks[chat_id].cancel()
        
        self._heartbeat_tasks[chat_id] = asyncio.create_task(
            self._heartbeat_loop(chat_id, websocket)
        )
        logger.info(f"💓 Started heartbeat for {chat_id}")

    async def _heartbeat_loop(self, chat_id: str, websocket) -> None:
        """Heartbeat loop for detecting silent disconnects."""
        try:
            while chat_id in self.connections:
                await asyncio.sleep(self._heartbeat_interval)
                
                # Send ping
                ping_data = {
                    "type": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                try:
                    await websocket.send_json(ping_data)
                    logger.debug(f"📡 Sent ping to {chat_id}")
                except Exception as e:
                    logger.warning(f"💔 Heartbeat failed for {chat_id}: {e}")
                    # Connection is dead - clean up
                    await self._cleanup_connection(chat_id)
                    break
        except asyncio.CancelledError:
            logger.debug(f"💔 Heartbeat cancelled for {chat_id}")
        except Exception as e:
            logger.error(f"💔 Heartbeat error for {chat_id}: {e}")

    async def _stop_heartbeat(self, chat_id: str) -> None:
        """Stop heartbeat task for a connection."""
        if chat_id in self._heartbeat_tasks:
            self._heartbeat_tasks[chat_id].cancel()
            del self._heartbeat_tasks[chat_id]
            logger.debug(f"💔 Stopped heartbeat for {chat_id}")

    async def _auto_resume_if_needed(self, chat_id: str, websocket, enterprise_id: Optional[str]) -> None:
        """Automatically restore chat history for IN_PROGRESS chats on WebSocket connection."""
        try:
            if not enterprise_id:
                logger.debug(f"[AUTO_RESUME] No enterprise_id for {chat_id}, skipping auto-resume")
                return

            from core.data.persistence_manager import AG2PersistenceManager
            if not hasattr(self, '_persistence_manager'):
                self._persistence_manager = AG2PersistenceManager()

            # Check if chat exists and is IN_PROGRESS
            coll = await self._persistence_manager._coll()
            doc = await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"status": 1, "messages": 1})

            if not doc:
                logger.debug(f"[AUTO_RESUME] No existing chat found for {chat_id}, skipping auto-resume")
                return

            from core.data.models import WorkflowStatus
            status = doc.get("status", -1)
            if int(status) != int(WorkflowStatus.IN_PROGRESS):
                logger.debug(f"[AUTO_RESUME] Chat {chat_id} not IN_PROGRESS (status={status}), skipping auto-resume")
                return

            messages = doc.get("messages", [])
            if not messages:
                logger.debug(f"[AUTO_RESUME] No messages to resume for {chat_id}")
                return

            logger.info(f"🔄 [AUTO_RESUME] Restoring {len(messages)} messages for IN_PROGRESS chat {chat_id}")

            # Send all messages to restore the chat UI
            for idx, msg in enumerate(messages):
                # Convert message to chat.text event format
                event_data = {
                    "type": "chat.text",
                    "data": {
                        "index": idx,
                        "content": msg.get("content", ""),
                        "role": msg.get("role", "user"),
                        "sender": msg.get("name", msg.get("role", "user")),
                        "replay": True  # Mark as replay/restoration
                    }
                }
                await self._queue_message_with_backpressure(chat_id, event_data)

            # Send resume boundary event
            boundary_event = {
                "type": "chat.resume_boundary",
                "data": {
                    "message_count": len(messages),
                    "chat_status": "in_progress"
                }
            }
            await self._queue_message_with_backpressure(chat_id, boundary_event)
            await self._flush_message_queue(chat_id)

        except Exception as e:
            logger.warning(f"[AUTO_RESUME] Failed to auto-resume chat {chat_id}: {e}")

    async def _cleanup_connection(self, chat_id: str) -> None:
        """Clean up connection resources."""
        if chat_id in self.connections:
            del self.connections[chat_id]

        if chat_id in self._message_queues:
            del self._message_queues[chat_id]

        await self._stop_heartbeat(chat_id)
        logger.info(f"🧹 Cleaned up connection resources for {chat_id}")
    
    async def emit_session_paused(self, event) -> None:
        """Emit session paused event to client WebSocket."""
        from core.events.unified_event_dispatcher import SessionPausedEvent
        if not isinstance(event, SessionPausedEvent):
            return
            
        chat_id = event.chat_id
        if chat_id not in self.connections:
            logger.warning(f"No active connection for chat_id {chat_id} to emit session paused")
            return
            
        try:
            websocket = self.connections[chat_id]["websocket"]
            message = {
                "type": "session.paused",
                "data": {
                    "chat_id": chat_id,
                    "reason": event.reason,
                    "required_tokens": event.required_tokens,
                    "message": "Session paused due to insufficient tokens. Please top up your balance to continue.",
                    "timestamp": event.timestamp.isoformat()
                },
                "timestamp": event.timestamp.isoformat()
            }
            await websocket.send_json(message)
            logger.info(f"⏸️ Emitted session paused event to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to emit session paused event to {chat_id}: {e}")


