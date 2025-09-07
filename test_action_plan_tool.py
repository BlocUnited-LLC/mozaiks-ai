import asyncio
import types
import pytest

# Target module
from workflows.Generator.tools import action_plan as ap_mod


@pytest.mark.asyncio
async def test_action_plan_success(monkeypatch):
    # Stub UI emission to avoid transport dependency
    async def fake_use_ui_tool(*, tool_id=None, payload=None, chat_id=None, workflow_name=None, display=None, **kwargs):
        assert tool_id == "ActionPlan"
        assert isinstance(payload, dict)
        # Simulate UI returning a response object
        return {"ui_event_id": "evt_123", "status": "ok", "echo": payload.get("workflow_title")}

    # Patch the use_ui_tool function in the imported module's namespace
    monkeypatch.setattr(ap_mod, "use_ui_tool", fake_use_ui_tool)

    # Minimal valid plan
    plan = {
        "workflow_title": "My Workflow",
        "workflow_description": "Short description",
        "suggested_features": [
            {"feature_title": "Login", "description": "User logs in"},
            {"feature_title": "Process", "description": "System processes request"},
        ],
        "mermaid_flow": "sequenceDiagram\n  User->>System: start\n  System-->>User: done",
        "third_party_integrations": [{"technology_title": "Stripe", "description": "Payments"}],
        "constraints": ["No PII"],
    }

    result = await ap_mod.action_plan(action_plan=plan, agent_message="Review this", chat_id="chat123", enterprise_id="ent456", workflow_name="Generator")

    assert result["status"] == "success"
    assert result["ui_event_id"] == "evt_123"
    assert isinstance(result.get("action_plan"), dict)
    assert result["action_plan"]["workflow_title"] == "My Workflow"
    assert result["workflow_name"] == "Generator"


@pytest.mark.asyncio
async def test_action_plan_invalid_payload(monkeypatch):
    # Patch UI tool anyway (should not be called)
    async def fake_use_ui_tool(*args, **kwargs):
        raise AssertionError("use_ui_tool should not be called for invalid payload")

    monkeypatch.setattr(ap_mod, "use_ui_tool", fake_use_ui_tool)

    result = await ap_mod.action_plan(action_plan="not a dict", chat_id="chat123", enterprise_id="ent456", workflow_name="Generator")

    assert result["status"] == "error"
    assert "Invalid action_plan" in result["message"]
