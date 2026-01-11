import hashlib

import pytest

from workflows._shared.app_code_versions import build_snapshot_document, compute_patchset_document


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_snapshot_id_is_deterministic_across_file_order() -> None:
    files_a = {"src/a.txt": b"hello", "src/b.txt": b"world"}
    files_b = {"src/b.txt": b"world", "src/a.txt": b"hello"}  # reversed

    snap_a = build_snapshot_document(
        app_id="app-1",
        session_id="chat-1",
        workflow_type="app-generator",
        source="generated",
        files=files_a,
    )
    snap_b = build_snapshot_document(
        app_id="app-1",
        session_id="chat-1",
        workflow_type="app-generator",
        source="generated",
        files=files_b,
    )

    assert snap_a["snapshotId"] == snap_b["snapshotId"]


def test_patchset_computes_changes_and_conflicts_deterministically() -> None:
    base = build_snapshot_document(
        app_id="app-1",
        session_id="chat-1",
        workflow_type="app-generator",
        source="generated",
        files={"src/a.txt": b"v1", "src/b.txt": b"keep"},
        repo_url="https://github.com/example/repo",
    )
    target = build_snapshot_document(
        app_id="app-1",
        session_id="chat-2",
        workflow_type="app-generator",
        source="generated",
        files={"src/a.txt": b"v2", "src/c.txt": b"new"},  # modify a, delete b, add c
        repo_url="https://github.com/example/repo",
    )

    # Repo HEAD has user edits in a.txt and already has c.txt.
    repo_file_shas = {
        "src/a.txt": _sha(b"user-edited"),
        "src/b.txt": next(e["sha256"] for e in base["files"] if e["path"] == "src/b.txt"),
        "src/c.txt": _sha(b"existing"),
    }

    patchset = compute_patchset_document(
        app_id="app-1",
        base_snapshot=base,
        target_snapshot=target,
        repo_file_shas=repo_file_shas,
        base_commit_sha="deadbeef",
        repo_url="https://github.com/example/repo",
        workflow_type="app-generator",
    )

    assert isinstance(patchset.get("patchId"), str) and len(patchset["patchId"]) == 32
    assert patchset["baseSnapshotId"] == base["snapshotId"]
    assert patchset["targetSnapshotId"] == target["snapshotId"]

    changes = patchset["changes"]
    assert [c["operation"] for c in changes] == ["add", "delete", "modify"]
    assert [c["path"] for c in changes] == ["src/c.txt", "src/b.txt", "src/a.txt"]

    conflicts = patchset["conflicts"]
    assert len(conflicts) == 2
    assert conflicts[0]["path"] == "src/c.txt"
    assert conflicts[0]["reason"] == "repo_has_file"
    assert conflicts[1]["path"] == "src/a.txt"
    assert conflicts[1]["reason"] == "repo_modified_since_baseline"


def test_snapshot_redacts_sensitive_structured_outputs_and_skips_env_files() -> None:
    snap = build_snapshot_document(
        app_id="app-1",
        session_id="chat-1",
        workflow_type="app-generator",
        source="generated",
        files={
            ".env": b"OPENAI_API_KEY=sk-real\n",
            ".env.example": b"OPENAI_API_KEY=\n",
            "src/config.js": b"export const x = 1;\n",
        },
        structured_outputs={
            "INTERNAL_API_KEY": "dont_store_me",
            "nested": {"token": "ghp_abcdef", "ok": "hello"},
        },
    )

    # .env should be excluded entirely from stored files.
    paths = [f["path"] for f in snap["files"]]
    assert ".env" not in paths
    assert ".env.example" in paths

    so = snap.get("structuredOutputs") or {}
    assert so.get("INTERNAL_API_KEY") == "[REDACTED]"
    assert so.get("nested", {}).get("token") == "[REDACTED]"
    assert so.get("nested", {}).get("ok") == "hello"
