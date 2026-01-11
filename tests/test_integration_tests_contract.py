import pytest

from workflows.AppGenerator.tools.integration_tests import run_integration_tests


@pytest.mark.asyncio
async def test_integration_tests_returns_checks_contract_success() -> None:
    files = {
        "src/services/agentClient.js": "const ws = import.meta.env.VITE_AGENT_WEBSOCKET_URL;",
        ".env.example": "VITE_APP_ID=\nVITE_AGENT_WEBSOCKET_URL=\nVITE_AGENT_API_URL=\n",
    }

    result = await run_integration_tests(files=files, agent_context=None, context_variables=None)

    assert isinstance(result, dict)
    assert result.get("passed") is True
    assert result.get("offline") is True
    checks = result.get("checks")
    assert isinstance(checks, list)
    assert len(checks) >= 1

    for c in checks:
        assert isinstance(c, dict)
        assert isinstance(c.get("id"), str) and c["id"]
        assert isinstance(c.get("passed"), bool)
        assert isinstance(c.get("message"), str)


@pytest.mark.asyncio
async def test_integration_tests_fails_when_env_vars_unused() -> None:
    files = {
        "src/App.jsx": "export default function App(){ return null }",
    }

    result = await run_integration_tests(files=files, agent_context=None, context_variables=None)
    assert result.get("passed") is False
    checks = result.get("checks") or []
    assert any(c.get("id") == "agent_env_var_usage" and c.get("passed") is False for c in checks if isinstance(c, dict))

