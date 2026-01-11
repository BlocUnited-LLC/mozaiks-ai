"""
Core runtime tests - Open source test suite for MozaiksAI runtime.

These tests verify the workflow-agnostic runtime engine works correctly.
"""

import pytest
from pathlib import Path


class TestWorkflowDiscovery:
    """Test workflow loading and discovery."""

    def test_workflow_manager_import(self):
        """Verify workflow manager can be imported."""
        from core.workflow.workflow_manager import workflow_manager
        assert workflow_manager is not None

    def test_list_workflows(self):
        """Verify workflows can be listed."""
        from core.workflow.workflow_manager import workflow_manager
        workflows = workflow_manager.list_workflows()
        assert isinstance(workflows, list)

    def test_workflow_config_loading(self):
        """Verify workflow configs load without error."""
        from core.workflow.workflow_manager import workflow_manager
        workflows = workflow_manager.list_workflows()
        
        for wf_name in workflows:
            config = workflow_manager.get_config(wf_name)
            # Should have basic structure
            assert config is not None


class TestRuntimeExtensions:
    """Test runtime extension loading."""

    def test_extension_loader_import(self):
        """Verify extension loader can be imported."""
        from core.runtime.extensions import get_workflow_api_router, get_workflow_lifecycle_hooks
        assert get_workflow_api_router is not None
        assert get_workflow_lifecycle_hooks is not None

    def test_lifecycle_hooks_returns_dict(self):
        """Verify lifecycle hooks returns safe dict even for non-existent workflow."""
        from core.runtime.extensions import get_workflow_lifecycle_hooks
        
        hooks = get_workflow_lifecycle_hooks("NonExistentWorkflow")
        assert isinstance(hooks, dict)
        assert "is_build_workflow" in hooks
        assert "on_start" in hooks
        assert "on_complete" in hooks
        assert "on_fail" in hooks


class TestEventSystem:
    """Test event dispatching."""

    def test_event_dispatcher_import(self):
        """Verify event dispatcher can be imported."""
        from core.events.dispatcher import UnifiedEventDispatcher
        assert UnifiedEventDispatcher is not None

    def test_create_dispatcher(self):
        """Verify dispatcher can be instantiated."""
        from core.events.dispatcher import UnifiedEventDispatcher
        dispatcher = UnifiedEventDispatcher()
        assert dispatcher is not None


class TestPersistence:
    """Test persistence layer (requires MongoDB)."""

    @pytest.mark.skipif(
        not pytest.importorskip("pymongo", reason="MongoDB not available"),
        reason="MongoDB not configured"
    )
    def test_persistence_manager_import(self):
        """Verify persistence manager can be imported."""
        from core.data.persistence.persistence_manager import AG2PersistenceManager
        assert AG2PersistenceManager is not None
