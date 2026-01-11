import zipfile
from pathlib import Path

import pytest

from workflows.AgentGenerator.tools.export_to_github import ExportToGitHubTool


@pytest.mark.asyncio
async def test_execute_missing_bundle_returns_error(tmp_path: Path) -> None:
    tool = ExportToGitHubTool()
    tool.internal_api_key = "test-key"
    result = await tool.execute(app_id="app-123", bundle_path=str(tmp_path / "missing.zip"), user_id="user-1")
    assert result.success is False
    assert result.error and "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_rejects_non_zip(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.txt"
    bundle_path.write_text("nope", encoding="utf-8")

    tool = ExportToGitHubTool()
    tool.internal_api_key = "test-key"
    result = await tool.execute(app_id="app-123", bundle_path=str(bundle_path), user_id="user-1")
    assert result.success is False
    assert result.error and ".zip" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_success_returns_repo_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr("MyApp/README.md", "hello")

    tool = ExportToGitHubTool()
    tool.internal_api_key = "test-key"

    async def fake_initial_export(**_kwargs):
        return {
            "success": True,
            "repoUrl": "https://github.com/org/repo",
            "repoFullName": "org/repo",
            "baseCommitSha": "abc123",
        }

    async def fake_set_secrets(**_kwargs):
        return {"success": True, "secretsSet": ["DATABASE_URI"], "secretsFailed": []}

    async def fake_poll_status(**_kwargs):
        return {
            "success": True,
            "status": "completed",
            "workflowRun": {"id": 123, "conclusion": "success", "htmlUrl": "https://github.com/org/repo/actions/runs/123"},
            "deploymentUrls": {"preview": "https://app.example"},
        }

    monkeypatch.setattr(tool, "initial_export", fake_initial_export)
    monkeypatch.setattr(tool, "set_repository_secrets", fake_set_secrets)
    monkeypatch.setattr(tool, "_poll_deployment_status", fake_poll_status)

    result = await tool.execute(app_id="app-123", bundle_path=str(bundle_path), user_id="user-1")
    assert result.success is True
    assert result.repo_url == "https://github.com/org/repo"
    assert result.repo_full_name == "org/repo"
    assert result.base_commit_sha == "abc123"
    assert result.job_id == "123"
    assert result.workflow_run_url == "https://github.com/org/repo/actions/runs/123"
    assert result.deployment_url == "https://app.example"


@pytest.mark.asyncio
async def test_execute_initial_export_failure_returns_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr("MyApp/README.md", "hello")

    tool = ExportToGitHubTool()
    tool.internal_api_key = "test-key"

    async def fake_initial_export(**_kwargs):
        return {"success": False, "error": "nope"}

    monkeypatch.setattr(tool, "initial_export", fake_initial_export)

    result = await tool.execute(app_id="app-123", bundle_path=str(bundle_path), user_id="user-1")
    assert result.success is False
    assert result.error and "nope" in result.error.lower()


@pytest.mark.asyncio
async def test_poll_deployment_status_stops_on_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = ExportToGitHubTool()
    tool.max_poll_attempts = 5
    tool.poll_interval_s = 0.0

    responses = [
        {"status": "pending"},
        {"status": "in_progress"},
        {"status": "completed", "workflowRun": {"conclusion": "success"}},
    ]

    calls = {"count": 0}

    async def fake_get_status(**_kwargs):
        calls["count"] += 1
        return responses[min(calls["count"] - 1, len(responses) - 1)]

    monkeypatch.setattr(tool, "get_deploy_status", fake_get_status)

    result = await tool._poll_deployment_status(app_id="app-123", repo_full_name="org/repo", chat_id=None)
    assert result.get("status") == "completed"
