import hashlib
import zipfile
from pathlib import Path

import pytest

from workflows._shared.app_code_versions import (
    build_snapshot_document,
    compute_patchset_document,
    extract_files_from_zip_bundle,
)
from workflows.AppGenerator.tools.export_app_code import export_app_code_to_github
from workflows.AgentGenerator.tools.export_to_github import export_to_github_tool


class DummyContext:
    def __init__(self, data):
        self._data = dict(data or {})

    def get(self, key, default=None):
        return self._data.get(key, default)


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_update_export_creates_pr_with_conflicts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import workflows.AppGenerator.tools.export_app_code as export_module

    app_id = "app-1"
    user_id = "user-1"
    repo_url = "https://github.com/example/repo"
    base_commit_sha = "deadbeef"

    base_snapshot = build_snapshot_document(
        app_id=app_id,
        session_id="chat-baseline",
        workflow_type="app-generator",
        source="generated",
        files={"src/a.txt": b"baseline", "src/b.txt": b"keep"},
        repo_url=repo_url,
    )

    # Target bundle modifies a.txt, deletes b.txt, adds c.txt.
    bundle_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as zf:
        zf.writestr("MyApp/src/a.txt", "generated")
        zf.writestr("MyApp/src/c.txt", "new")

    target_files = extract_files_from_zip_bundle(str(bundle_path))
    expected_target_snapshot = build_snapshot_document(
        app_id=app_id,
        session_id="chat-1",
        workflow_type="app-generator",
        source="generated",
        files=target_files,
        repo_url=repo_url,
    )

    # Repo manifest represents current repo state (user edited a.txt and c.txt already exists).
    repo_file_shas = {
        "src/a.txt": _sha(b"user-edited"),
        "src/b.txt": next(e["sha256"] for e in base_snapshot["files"] if e["path"] == "src/b.txt"),
        "src/c.txt": _sha(b"existing"),
    }

    expected_patchset = compute_patchset_document(
        app_id=app_id,
        base_snapshot=base_snapshot,
        target_snapshot=expected_target_snapshot,
        repo_file_shas=repo_file_shas,
        base_commit_sha=base_commit_sha,
        repo_url=repo_url,
        workflow_type="app-generator",
    )

    # --- Stubs: avoid DB calls ---
    async def fake_get_latest_workflow_export(*, app_id: str, workflow_type: str):
        assert app_id == "app-1"
        assert workflow_type == "app-generator"
        return {"repo_url": repo_url, "snapshotId": base_snapshot["snapshotId"]}

    async def fake_get_snapshot(*, app_id: str, snapshot_id: str):
        assert app_id == "app-1"
        assert snapshot_id == base_snapshot["snapshotId"]
        return base_snapshot

    async def fake_persist_snapshot(*, snapshot_doc):
        return snapshot_doc["snapshotId"]

    async def fake_persist_patchset(*, patchset_doc):
        return patchset_doc["patchId"]

    async def fake_record_workflow_export(**_kwargs):
        return None

    monkeypatch.setattr(export_module, "get_latest_workflow_export", fake_get_latest_workflow_export)
    monkeypatch.setattr(export_module, "get_snapshot", fake_get_snapshot)
    monkeypatch.setattr(export_module, "persist_snapshot", fake_persist_snapshot)
    monkeypatch.setattr(export_module, "persist_patchset", fake_persist_patchset)
    monkeypatch.setattr(export_module, "record_workflow_export", fake_record_workflow_export)

    # --- Stubs: backend calls ---
    async def fake_execute(**_kwargs):
        raise AssertionError("execute should not be called for update exports")

    async def fake_manifest(**_kwargs):
        return {
            "repoUrl": repo_url,
            "baseCommitSha": base_commit_sha,
            "files": [{"path": p, "sha256": sha} for p, sha in sorted(repo_file_shas.items())],
        }

    captured = {"create_pr_kwargs": None}

    async def fake_create_pr(**kwargs):
        captured["create_pr_kwargs"] = kwargs
        return {"prUrl": "https://github.com/example/repo/pull/1", "jobId": "job-1"}

    monkeypatch.setattr(export_to_github_tool, "execute", fake_execute)
    monkeypatch.setattr(export_to_github_tool, "get_repo_manifest", fake_manifest)
    monkeypatch.setattr(export_to_github_tool, "create_pull_request", fake_create_pr)

    ctx = DummyContext({"app_validation_passed": True, "integration_tests_passed": True, "chat_id": "chat-1"})

    res = await export_app_code_to_github(
        app_id=app_id,
        bundle_path=str(bundle_path),
        user_id=user_id,
        commit_message="Update from MozaiksAI",
        context_variables=ctx,
    )

    assert res["success"] is True
    assert res["export_mode"] == "update_pr"
    assert res["repo_url"] == repo_url
    assert res["pr_url"] == "https://github.com/example/repo/pull/1"
    assert res["patch_id"] == expected_patchset["patchId"]
    assert res["conflicts_count"] == len(expected_patchset["conflicts"])
    assert res["conflicts"] == expected_patchset["conflicts"]

    pr_kwargs = captured["create_pr_kwargs"]
    assert pr_kwargs is not None
    assert pr_kwargs["repo_url"] == repo_url
    assert pr_kwargs["base_commit_sha"] == base_commit_sha
    assert pr_kwargs["patch_id"] == expected_patchset["patchId"]
    assert pr_kwargs["branch_name"].endswith(expected_patchset["patchId"])
    assert pr_kwargs["changes"] == expected_patchset["changes"]
    assert "conflicts" not in pr_kwargs
