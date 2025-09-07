import asyncio
import json


async def check_llm_config():
    from core.workflow.llm_config import get_llm_config
    _, cfg = await get_llm_config()
    tools_present = isinstance(cfg, dict) and "tools" in cfg and isinstance(cfg.get("tools"), list)
    return {
        "tools_present": tools_present,
        "tools_len": len(cfg.get("tools", [])) if isinstance(cfg.get("tools", []), list) else None,
        "config_list_len": len(cfg.get("config_list", []) if isinstance(cfg.get("config_list", []), list) else []),
    }


async def check_action_plan_tool():
    # Import the tool module and stub the UI function it uses
    from workflows.Generator.tools import action_plan as ap_mod

    async def fake_use_ui_tool(*, tool_id=None, payload=None, chat_id=None, workflow_name=None, display=None, **kwargs):
        # Minimal validation mirroring the real expectations
        assert tool_id == "ActionPlan"
        assert isinstance(payload, dict)
        return {"ui_event_id": "evt_123", "status": "ok"}

    # Patch the module-level function
    ap_mod.use_ui_tool = fake_use_ui_tool

    plan = {
        "workflow_title": "Smoke Workflow",
        "workflow_description": "Short description",
        "suggested_features": [
            {"feature_title": "Login", "description": "User logs in"},
            {"feature_title": "Process", "description": "System processes request"},
        ],
        "mermaid_flow": "sequenceDiagram\n  User->>System: start\n  System-->>User: done",
        "third_party_integrations": [{"technology_title": "Stripe", "description": "Payments"}],
        "constraints": ["No PII"],
    }

    result = await ap_mod.action_plan(
        action_plan=plan,
        agent_message="Review this",
        chat_id="chat_smoke",
        enterprise_id="ent_smoke",
        workflow_name="Generator",
    )
    return {
        "status": result.get("status"),
        "ui_event_id": result.get("ui_event_id"),
        "has_action_plan": isinstance(result.get("action_plan"), dict),
    }


async def main():
    out = {"llm_config": await check_llm_config(), "action_plan": await check_action_plan_tool()}
    print(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(main())
