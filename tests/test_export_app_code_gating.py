import pytest

from workflows.AppGenerator.tools.export_app_code import export_app_code_to_github
from workflows.AgentGenerator.tools.export_to_github import export_to_github_tool


class DummyContext:
    def __init__(self, data):
        self._data = dict(data or {})

    def get(self, key, default=None):
        return self._data.get(key, default)


@pytest.mark.asyncio
async def test_export_app_code_blocked_without_context(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    async def fake_execute(**_kwargs):
        called["count"] += 1
        raise AssertionError("execute should not be called when export is blocked")

    monkeypatch.setattr(export_to_github_tool, "execute", fake_execute)

    res = await export_app_code_to_github(app_id="app-1", bundle_path="bundle.zip", context_variables=None)
    assert res.get("success") is False
    assert res.get("blocked") is True
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_export_app_code_blocked_when_validation_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    async def fake_execute(**_kwargs):
        called["count"] += 1
        raise AssertionError("execute should not be called when export is blocked")

    monkeypatch.setattr(export_to_github_tool, "execute", fake_execute)

    ctx = DummyContext({"app_validation_passed": False, "integration_tests_passed": True})
    res = await export_app_code_to_github(app_id="app-1", bundle_path="bundle.zip", context_variables=ctx)
    assert res.get("success") is False
    assert res.get("blocked") is True
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_export_app_code_calls_execute_when_gates_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    class DummyResult:
        success = False
        repo_url = None
        job_id = None
        error = "noop"

        def model_dump(self):
            return {"success": False, "repo_url": None, "job_id": None, "error": "noop"}

    async def fake_execute(**_kwargs):
        called["count"] += 1
        return DummyResult()

    monkeypatch.setattr(export_to_github_tool, "execute", fake_execute)

    ctx = DummyContext({"app_validation_passed": True, "integration_tests_passed": True})
    res = await export_app_code_to_github(app_id="app-1", bundle_path="bundle.zip", context_variables=ctx)
    assert called["count"] == 1
    assert res.get("workflow_type") == "app-generator"

