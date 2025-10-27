import pytest

from core.transport.simple_transport import SimpleTransport


@pytest.mark.asyncio
async def test_resume_without_echo(monkeypatch):
    st = await SimpleTransport.get_instance()
    chat_id = "test-chat-resume"
    request_id = "req-123"

    recorded = {"called": False, "value": None}

    def respond_cb(val):
        recorded["called"] = True
        recorded["value"] = val
        return None

    # Register the fake input request directly
    st._input_request_registries[chat_id] = {request_id: respond_cb}

    # Capture emitted events instead of sending over websocket
    captured = []

    async def fake_send_event_to_ui(event, target_chat_id=None):
        captured.append((event, target_chat_id))

    monkeypatch.setattr(st, "send_event_to_ui", fake_send_event_to_ui)

    # Invoke the resume path (message=None)
    result = await st.handle_user_input_from_api(chat_id=chat_id, user_id=None, workflow_name="Generator", message=None, enterprise_id="ent1")

    assert result["status"] == "success"
    assert result.get("route") == "existing_session_resume"
    assert recorded["called"] is True and recorded["value"] is None
    assert captured, "expected an input_ack to be emitted"
    assert captured[0][0].get("kind") == "input_ack"
