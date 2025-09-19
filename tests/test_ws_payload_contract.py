import asyncio
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any

from jsonschema import validate
from event_schemas import get_schema

import pytest
from shared_app import SimpleTransport

# NOTE: This test focuses on validating that emitted websocket events conform
# to the documented payload contract (docs/WEBSOCKET_PAYLOAD_CONTRACT.md).
# It does not run a full workflow orchestration; instead it emits synthetic
# events via the transport to keep it fast and deterministic.

# For tool calls we expect a namespaced outer envelope + a data object produced
# by transport.send_ui_tool_event -> send_event_to_ui mapping (chat.tool_call)
REQUIRED_TOOL_CALL_OUTER_FIELDS = {
    'type',
    'data'
}

REQUIRED_TOOL_CALL_DATA_FIELDS = {
    'tool_name',
    'component_type',
    'payload'
}

REQUIRED_CHAT_TEXT_FIELDS = {
    'type',  # e.g. chat.text
    'data'   # envelope includes data with content
}

class DummyWebSocket:
    """Minimal stand-in for a FastAPI WebSocket exposing send_json."""
    def __init__(self, sink):
        self._sink = sink
    async def send_json(self, data):  # pragma: no cover - trivial forwarding
        self._sink.append(data)

@pytest.mark.asyncio
async def test_websocket_payload_contract():
    transport = await SimpleTransport.get_instance()
    chat_id = f"test-{uuid.uuid4().hex[:8]}"
    events = []

    # Register dummy connection record mimicking real structure
    transport.connections[chat_id] = {
        'websocket': DummyWebSocket(events),
        'connected_at': datetime.now(timezone.utc),
        'client_index': 0,
        'last_heartbeat': time.time(),
        'heartbeat_task': None,
        'autostarted': True
    }

    # Emit synthetic chat.text
    await transport.send_event_to_ui({
        'kind': 'chat.text',
        'content': 'Hello world',
        'agent': 'TestAgent'
    }, chat_id=chat_id)

    # Emit synthetic ui tool call using dedicated helper to ensure proper mapping
    await transport.send_ui_tool_event(
        event_id=str(uuid.uuid4()),
        chat_id=chat_id,
        tool_name='TestComponent',
        component_name='TestComponent',
        display_type='inline',
        payload={
            'workflow_name': 'TestWorkflow',
            'component_type': 'TestComponent',
            'content': 'Rendered component body',
            'display': 'inline'
        }
    )

    # Give event loop a tick to process async sends
    await asyncio.sleep(0)

    assert events, "No events captured from transport"

    # Transport currently namespaces tool_call events as chat.tool_call
    ui_tool_events = [m for m in events if m.get('type') == 'chat.tool_call']
    chat_text_events = [m for m in events if m.get('type') == 'chat.text']

    if chat_text_events:
        evt = chat_text_events[0]
        missing = REQUIRED_CHAT_TEXT_FIELDS - set(evt.keys())
        assert not missing, f"chat.text event missing fields: {missing} in {evt}"
        assert isinstance(evt['data'].get('content'), str), "chat.text data.content must be string"
        schema = get_schema('chat.text')
        if schema:
            validate(instance=evt, schema=schema)

    assert ui_tool_events, "Expected at least one chat.tool_call event"
    tool_evt = ui_tool_events[0]
    missing_outer = REQUIRED_TOOL_CALL_OUTER_FIELDS - set(tool_evt.keys())
    assert not missing_outer, f"chat.tool_call outer missing fields: {missing_outer} in {tool_evt}"
    assert isinstance(tool_evt['data'], dict)
    data_obj: Dict[str, Any] = tool_evt['data']
    missing_inner = REQUIRED_TOOL_CALL_DATA_FIELDS - set(data_obj.keys())
    assert not missing_inner, f"chat.tool_call data missing fields: {missing_inner} in {data_obj}"
    assert data_obj['tool_name'] == 'TestComponent'
    assert data_obj['component_type'] == 'TestComponent'
    assert isinstance(data_obj['payload'], dict)
    assert data_obj['payload'].get('workflow_name') == 'TestWorkflow'
    assert data_obj['payload'].get('component_type') == 'TestComponent'
    assert data_obj['payload'].get('display') in {'inline', 'artifact', None}
    schema = get_schema('chat.tool_call')
    if schema:
        validate(instance=tool_evt, schema=schema)
    for msg in events:
        t = msg.get('type')
        if isinstance(t, str):
            assert t == t.lower(), f"Event type must be lowercase (got {t})"
