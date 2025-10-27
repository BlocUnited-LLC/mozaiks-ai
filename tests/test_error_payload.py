import pytest

from core.events.unified_event_dispatcher import get_event_dispatcher


def test_error_event_payload_message():
    dispatcher = get_event_dispatcher()

    raw = {"kind": "error", "agent": "TestAgent", "message": "Something broke: inner exception"}
    env = dispatcher.build_outbound_event_envelope(raw_event=raw, chat_id="test-chat-xyz", get_sequence_cb=lambda x: 1, workflow_name="Generator")

    assert env is not None
    assert env.get("type") == "chat.error"
    data = env.get("data", {})
    assert "message" in data and data["message"]
    assert data["message"] == "Something broke: inner exception"
