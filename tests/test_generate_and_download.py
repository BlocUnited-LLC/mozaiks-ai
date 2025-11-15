# ==============================================================================
# FILE: tests/test_generate_and_download.py
# DESCRIPTION: Unit tests for generate_and_download dependency graph extraction
# ==============================================================================

import asyncio
import logging
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the module (not the function)
import workflows.Generator.tools.generate_and_download
gnd_module = sys.modules['workflows.Generator.tools.generate_and_download']

from core.workflow import dependencies

# Use pytest-asyncio
pytestmark = pytest.mark.asyncio


async def test_update_workflow_dependency_graph_calls_manager(monkeypatch):
    """Ensure _update_workflow_dependency_graph extracts fields and calls dependency_manager.update_workflow_graph."""
    called = {}

    async def fake_update_workflow_graph(self, enterprise_id, workflow_name, dependencies, provides):
        called['enterprise_id'] = enterprise_id
        called['workflow_name'] = workflow_name
        called['dependencies'] = dependencies
        called['provides'] = provides
        return True

    # Monkeypatch dependency_manager in the generate_and_download module
    fake_manager = type("DM", (), {"update_workflow_graph": fake_update_workflow_graph})()
    monkeypatch.setattr(gnd_module, "dependency_manager", fake_manager)

    # Prepare fake collected dict with WorkflowArchitectAgent -> TechnicalBlueprint
    collected = {
        "WorkflowArchitectAgent": {
            "TechnicalBlueprint": {
                "workflow_dependencies": {
                    "required_workflows": [{"workflow": "Generator", "status": "completed"}],
                    "required_context_vars": ["generated_files"],
                    "required_artifacts": [{"artifact_type": "ActionPlan", "source_workflow": "Generator"}],
                },
                "workflow_provides": {
                    "context_vars": ["built_package"],
                    "artifacts": ["BuildBundle"]
                }
            }
        }
    }

    logger = logging.getLogger("test_gnd")
    await gnd_module._update_workflow_dependency_graph(collected, "MyWorkflow", "ent-123", logger)

    assert called.get("enterprise_id") == "ent-123"
    assert called.get("workflow_name") == "MyWorkflow"
    assert isinstance(called.get("dependencies"), dict)
    assert isinstance(called.get("provides"), dict)
    assert called["dependencies"]["required_workflows"][0]["workflow"] == "Generator"
    assert "generated_files" in called["dependencies"]["required_context_vars"]
    assert "built_package" in called["provides"]["context_vars"]


async def test_update_workflow_dependency_graph_handles_null_dependencies(monkeypatch):
    """Ensure _update_workflow_dependency_graph handles null workflow_dependencies gracefully."""
    called = {}

    async def fake_update_workflow_graph(self, enterprise_id, workflow_name, dependencies, provides):
        called['enterprise_id'] = enterprise_id
        called['workflow_name'] = workflow_name
        called['dependencies'] = dependencies
        called['provides'] = provides
        return True

    fake_manager = type("DM", (), {"update_workflow_graph": fake_update_workflow_graph})()
    monkeypatch.setattr(gnd_module, "dependency_manager", fake_manager)

    # First workflow with no dependencies
    collected = {
        "WorkflowArchitectAgent": {
            "TechnicalBlueprint": {
                "workflow_dependencies": None,
                "workflow_provides": {
                    "context_vars": ["action_plan"],
                    "artifacts": ["ActionPlan"]
                }
            }
        }
    }

    logger = logging.getLogger("test_gnd")
    await gnd_module._update_workflow_dependency_graph(collected, "Generator", "ent-456", logger)

    assert called.get("enterprise_id") == "ent-456"
    assert called.get("workflow_name") == "Generator"
    # Should handle null gracefully
    assert called.get("dependencies") is None or called["dependencies"] == {}
    assert called["provides"]["context_vars"] == ["action_plan"]


async def test_update_workflow_dependency_graph_missing_architect_output(monkeypatch):
    """Ensure _update_workflow_dependency_graph handles missing architect output without crashing."""
    called = {}

    async def fake_update_workflow_graph(self, enterprise_id, workflow_name, dependencies, provides):
        called['called'] = True
        return True

    fake_manager = type("DM", (), {"update_workflow_graph": fake_update_workflow_graph})()
    monkeypatch.setattr(gnd_module, "dependency_manager", fake_manager)

    # No WorkflowArchitectAgent output
    collected = {}

    logger = logging.getLogger("test_gnd")
    await gnd_module._update_workflow_dependency_graph(collected, "MyWorkflow", "ent-789", logger)

    # Should not call update_workflow_graph when architect output missing
    assert called.get('called') is None
