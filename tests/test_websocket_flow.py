import pytest

from autogen.io import IOWebsockets

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from shared_app import app  # noqa: E402

def test_websocket_smoke_connect():
    """Smoke test to verify WebSocket handshake succeeds."""
    # Ensure SimpleTransport is initialized for shared_app
    import asyncio
    from core.transport.simple_transport import SimpleTransport
    import shared_app
    shared_app.simple_transport = asyncio.get_event_loop().run_until_complete(
        SimpleTransport.get_instance()
    )
    client = TestClient(app)
    # Use arbitrary identifiers for workflow/chat/user
    ws_url = "/ws/test_workflow/test_ent/test_chat/test_user"
    with client.websocket_connect(ws_url) as ws:
        # Connection established without error
        assert ws is not None
