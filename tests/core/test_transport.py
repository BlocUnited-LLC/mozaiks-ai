"""
Transport layer tests - WebSocket and session management.
"""

import pytest


class TestSessionRegistry:
    """Test session management."""

    def test_session_registry_import(self):
        """Verify session registry can be imported."""
        from mozaiksai.core.transport.session_registry import SessionRegistry
        assert SessionRegistry is not None

    def test_create_registry(self):
        """Verify registry can be instantiated."""
        from mozaiksai.core.transport.session_registry import SessionRegistry
        registry = SessionRegistry()
        assert registry is not None


class TestSimpleTransport:
    """Test transport handlers."""

    def test_transport_import(self):
        """Verify transport module can be imported."""
        from mozaiksai.core.transport import simple_transport
        assert simple_transport is not None

    def test_has_handler(self):
        """Verify handler function exists."""
        from mozaiksai.core.transport.simple_transport import handle_user_input_api
        assert callable(handle_user_input_api)
