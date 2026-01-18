"""Workflow-time app code snapshots + patch sets (Lovable-style updates).

MozaiksAI owns deterministic generation-time artifacts:
- AppCodeSnapshots: content-addressed snapshots of generated app bundles
- AppCodePatchSets: deterministic change sets + conflict detection for PR-based updates

Backend owns GitHub credentials and PR creation. MozaiksAI never pushes directly.

Non-negotiables:
- Multi-tenant safe: all queries are scoped by app_id.
- Deterministic IDs: same inputs -> same snapshotId/patchId.
- No secrets stored (repo URLs + commit SHAs only).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from logs.logging_config import get_core_logger

from mozaiksai.core.core_config import get_mongo_client
from mozaiksai.core.multitenant import build_app_scope_filter, coalesce_app_id

logger = get_core_logger("app_code_versions")

_INDEX_LOCK = asyncio.Lock()
_INDEX_READY = False


_SENSITIVE_KEY_SUBSTRINGS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "private_key",
    "internal_api_key",
    "authorization",
    "access_key",
)

_SENSITIVE_VALUE_PREFIXES = (
    "sk-",  # OpenAI
    "rk-",  # OpenAI (rare)
    "ghp_",  # GitHub classic PAT
    "github_pat_",  # GitHub fine-grained PAT
    "e2b_",  # E2B
    "moz_live_",  # Mozaiks (example)
    "moz_test_",  # Mozaiks (example)
)

_SENSITIVE_VALUE_CONTAINS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)


def _db_name() -> str:
    return (os.getenv("MOZAIKS_APP_CODE_DB") or "MozaiksAI").strip() or "MozaiksAI"


def _snapshots_collection() -> str:
    return (os.getenv("MOZAIKS_APP_CODE_SNAPSHOTS_COLLECTION") or "AppCodeSnapshots").strip() or "AppCodeSnapshots"


def _patchsets_collection() -> str:
    return (os.getenv("MOZAIKS_APP_CODE_PATCHSETS_COLLECTION") or "AppCodePatchSets").strip() or "AppCodePatchSets"


def _get_generator_version() -> str:
    # Prefer explicit CI/version env vars; fall back to a stable sentinel.
    for key in ("MOZAIKS_GENERATOR_VERSION", "MOZAIKS_RUNTIME_VERSION", "GIT_SHA", "GITHUB_SHA"):
        raw = os.getenv(key)
        if raw and str(raw).strip():
            return str(raw).strip()
    return "dev"


async def _ensure_indexes() -> None:
    global _INDEX_READY
    if _INDEX_READY:
        return
    async with _INDEX_LOCK:
        if _INDEX_READY:
            return
        try:
            client = get_mongo_client()
            db = client[_db_name()]
            snaps = db[_snapshots_collection()]
            patches = db[_patchsets_collection()]

            await snaps.create_index([("app_id", 1), ("snapshotId", 1)], unique=True, name="app_snapshot_unique")
            await snaps.create_index([("app_id", 1), ("workflowType", 1), ("createdAt", -1)], name="app_snapshot_latest")
            await snaps.create_index([("app_id", 1), ("repoUrl", 1), ("createdAt", -1)], name="app_snapshot_repo_latest")

            await patches.create_index([("app_id", 1), ("patchId", 1)], unique=True, name="app_patch_unique")
            await patches.create_index([("app_id", 1), ("createdAt", -1)], name="app_patch_latest")
            await patches.create_index([("app_id", 1), ("repoUrl", 1), ("createdAt", -1)], name="app_patch_repo_latest")

            _INDEX_READY = True
        except Exception as exc:  # pragma: no cover
            # Index creation should never hard-fail the workflow.
            logger.warning("Failed to ensure snapshot/patchset indexes: %s", exc)


def _safe_relpath(raw: str) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    path = raw.replace("\\", "/").strip()
    if not path or path.startswith("/"):
        return None
    p = PurePosixPath(path)
    if p.is_absolute():
        return None
    if any(part == ".." for part in p.parts):
        return None
    # Avoid odd Windows drive prefixes sneaking in via zip entries.
    if ":" in p.parts[0]:
        return None
    return str(p)


def _is_sensitive_path(path: str) -> bool:
    p = str(path or "").replace("\\", "/").strip().lower()
    if not p:
        return False
    name = p.split("/")[-1]
    if name == ".env":
        return True
    if name.startswith(".env.") and name not in {".env.example", ".env.template"}:
        return True
    if name in {"id_rsa", "id_ed25519", "id_dsa"}:
        return True
    for suffix in (".pem", ".key", ".p12", ".pfx", ".crt"):
        if name.endswith(suffix):
            return True
    return False


def _redact_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return value
    upper = raw.upper()
    if any(marker in raw for marker in _SENSITIVE_VALUE_CONTAINS):
        return "[REDACTED]"
    if any(raw.startswith(prefix) for prefix in _SENSITIVE_VALUE_PREFIXES):
        return "[REDACTED]"
    if "TOKEN" in upper or "API KEY" in upper:
        # Avoid persisting obvious secret-bearing blobs.
        if len(raw) > 20:
            return "[REDACTED]"
    return value


def _sanitize_structured_outputs(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 25:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                continue
            key_norm = k.strip().lower()
            if any(s in key_norm for s in _SENSITIVE_KEY_SUBSTRINGS):
                out[k] = "[REDACTED]"
            else:
                out[k] = _sanitize_structured_outputs(v, _depth=_depth + 1)
        return out
    if isinstance(value, list):
        return [_sanitize_structured_outputs(v, _depth=_depth + 1) for v in value[:500]]
    if isinstance(value, str):
        return _redact_value(value)
    return value


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _snapshot_id_from_file_meta(meta: List[Dict[str, Any]]) -> str:
    # Deterministic across ordering: use sorted "path:sha:size" lines.
    sig = "\n".join(
        f"{m.get('path')}:{m.get('sha256')}:{m.get('sizeBytes')}"
        for m in sorted(meta, key=lambda x: str(x.get("path") or ""))
    )
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:32]


def _patch_id(*, repo_url: Optional[str], base_snapshot_id: str, target_snapshot_id: str, base_commit_sha: Optional[str]) -> str:
    sig = "|".join(
        [
            str(repo_url or "").strip(),
            str(base_snapshot_id or "").strip(),
            str(target_snapshot_id or "").strip(),
            str(base_commit_sha or "").strip(),
        ]
    )
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:32]


def extract_files_from_zip_bundle(bundle_path: str) -> Dict[str, bytes]:
    """Extract a normalized relpath->bytes map from a bundle zip.

    The bundler writes zip entries as: <bundle_name>/<relpath>. We strip the root
    folder segment when present.
    """
    out: Dict[str, bytes] = {}
    with zipfile.ZipFile(bundle_path, "r") as zf:
        for member in zf.namelist():
            if not isinstance(member, str):
                continue
            norm = member.replace("\\", "/")
            if not norm or norm.endswith("/"):
                continue
            parts = [p for p in norm.split("/") if p]
            if not parts:
                continue
            rel = "/".join(parts[1:]) if len(parts) > 1 else parts[0]
            safe = _safe_relpath(rel)
            if not safe:
                continue
            try:
                out[safe] = zf.read(member)
            except Exception:
                continue
    return out


def build_snapshot_document(
    *,
    app_id: str,
    session_id: Optional[str],
    workflow_type: str,
    source: str,
    files: Dict[str, bytes],
    structured_outputs: Optional[Dict[str, Any]] = None,
    repo_url: Optional[str] = None,
    base_commit_sha: Optional[str] = None,
    generator_version: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        raise ValueError("app_id is required")

    normalized_files: Dict[str, bytes] = {}
    for raw_path, content in (files or {}).items():
        safe = _safe_relpath(str(raw_path))
        if not safe:
            continue
        if _is_sensitive_path(safe):
            continue
        if isinstance(content, bytes):
            normalized_files[safe] = content
        else:
            normalized_files[safe] = str(content).encode("utf-8", errors="replace")

    file_entries: List[Dict[str, Any]] = []
    for path in sorted(normalized_files.keys()):
        content = normalized_files[path]
        sha = _sha256_hex(content)
        entry: Dict[str, Any] = {
            "path": path,
            "sha256": sha,
            "sizeBytes": int(len(content)),
            "contentBase64": base64.b64encode(content).decode("ascii"),
        }
        file_entries.append(entry)

    snapshot_id = _snapshot_id_from_file_meta(file_entries)
    now = datetime.now(UTC)
    doc: Dict[str, Any] = {
        **build_app_scope_filter(resolved_app_id),
        "snapshotId": snapshot_id,
        "appId": resolved_app_id,
        "sessionId": str(session_id) if session_id else None,
        "createdAt": now,
        "source": str(source or "").strip() or "generated",
        "workflowType": str(workflow_type or "").strip() or "app-generator",
        "generatorVersion": str(generator_version or "").strip() or _get_generator_version(),
        "files": file_entries,
        "structuredOutputs": _sanitize_structured_outputs(structured_outputs) if isinstance(structured_outputs, dict) else {},
        "repoUrl": str(repo_url).strip() if repo_url else None,
        "baseCommitSha": str(base_commit_sha).strip() if base_commit_sha else None,
    }
    return doc


def build_snapshot_document_from_hashes(
    *,
    app_id: str,
    session_id: Optional[str],
    workflow_type: str,
    source: str,
    files: List[Dict[str, Any]],
    structured_outputs: Optional[Dict[str, Any]] = None,
    repo_url: Optional[str] = None,
    base_commit_sha: Optional[str] = None,
    generator_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a snapshot document when only file hashes are available.

    This is used when a baseline is derived from a Git repo tree manifest (no
    file contents pulled into MozaiksAI).
    """
    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        raise ValueError("app_id is required")

    file_entries: List[Dict[str, Any]] = []
    for entry in files or []:
        if not isinstance(entry, dict):
            continue
        safe = _safe_relpath(str(entry.get("path") or ""))
        sha = entry.get("sha256")
        if not safe or not isinstance(sha, str) or not sha.strip():
            continue
        if _is_sensitive_path(safe):
            continue
        try:
            size = int(entry.get("sizeBytes") or 0)
        except Exception:
            size = 0
        file_entries.append({"path": safe, "sha256": sha.strip(), "sizeBytes": size})

    snapshot_id = _snapshot_id_from_file_meta(file_entries)
    now = datetime.now(UTC)
    doc: Dict[str, Any] = {
        **build_app_scope_filter(resolved_app_id),
        "snapshotId": snapshot_id,
        "appId": resolved_app_id,
        "sessionId": str(session_id) if session_id else None,
        "createdAt": now,
        "source": str(source or "").strip() or "imported_repo",
        "workflowType": str(workflow_type or "").strip() or "app-generator",
        "generatorVersion": str(generator_version or "").strip() or _get_generator_version(),
        "files": sorted(file_entries, key=lambda x: str(x.get("path") or "")),
        "structuredOutputs": _sanitize_structured_outputs(structured_outputs) if isinstance(structured_outputs, dict) else {},
        "repoUrl": str(repo_url).strip() if repo_url else None,
        "baseCommitSha": str(base_commit_sha).strip() if base_commit_sha else None,
    }
    return doc


async def persist_snapshot(*, snapshot_doc: Dict[str, Any]) -> str:
    await _ensure_indexes()
    snapshot_id = (snapshot_doc or {}).get("snapshotId")
    app_id = (snapshot_doc or {}).get("app_id")
    if not snapshot_id or not app_id:
        raise ValueError("snapshot_doc must include snapshotId and app_id")
    client = get_mongo_client()
    coll = client[_db_name()][_snapshots_collection()]
    await coll.replace_one({"snapshotId": snapshot_id, **build_app_scope_filter(app_id)}, snapshot_doc, upsert=True)
    return str(snapshot_id)


async def get_snapshot(*, app_id: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        return None
    sid = str(snapshot_id or "").strip()
    if not sid:
        return None
    client = get_mongo_client()
    coll = client[_db_name()][_snapshots_collection()]
    doc = await coll.find_one({**build_app_scope_filter(resolved_app_id), "snapshotId": sid})
    if not isinstance(doc, dict):
        return None
    doc.pop("_id", None)
    return doc


async def get_latest_snapshot(
    *,
    app_id: str,
    workflow_type: str,
    repo_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        return None
    wf_type = str(workflow_type or "").strip()
    if not wf_type:
        return None
    query: Dict[str, Any] = {**build_app_scope_filter(resolved_app_id), "workflowType": wf_type}
    if repo_url and str(repo_url).strip():
        query["repoUrl"] = str(repo_url).strip()
    client = get_mongo_client()
    coll = client[_db_name()][_snapshots_collection()]
    cursor = coll.find(query).sort("_id", -1).limit(1)
    docs = await cursor.to_list(length=1)
    doc = docs[0] if docs else None
    if not isinstance(doc, dict):
        return None
    doc.pop("_id", None)
    return doc


def _files_map_from_snapshot(snapshot_doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    files = (snapshot_doc or {}).get("files")
    if not isinstance(files, list):
        return out
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        sha = entry.get("sha256")
        if not isinstance(path, str) or not path.strip():
            continue
        if not isinstance(sha, str) or not sha.strip():
            continue
        out[path] = entry
    return out


def compute_patchset_document(
    *,
    app_id: str,
    base_snapshot: Dict[str, Any],
    target_snapshot: Dict[str, Any],
    repo_file_shas: Dict[str, str],
    base_commit_sha: Optional[str],
    repo_url: Optional[str],
    workflow_type: str,
) -> Dict[str, Any]:
    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        raise ValueError("app_id is required")

    base_snapshot_id = str((base_snapshot or {}).get("snapshotId") or "").strip()
    target_snapshot_id = str((target_snapshot or {}).get("snapshotId") or "").strip()
    if not base_snapshot_id or not target_snapshot_id:
        raise ValueError("base_snapshot and target_snapshot must include snapshotId")

    base_files = _files_map_from_snapshot(base_snapshot)
    target_files = _files_map_from_snapshot(target_snapshot)

    base_paths = set(base_files.keys())
    target_paths = set(target_files.keys())

    changes: List[Dict[str, Any]] = []

    # Adds
    for path in sorted(target_paths - base_paths):
        entry = target_files[path]
        changes.append(
            {
                "path": path,
                "operation": "add",
                "afterSha256": entry.get("sha256"),
                "contentBase64": entry.get("contentBase64"),
            }
        )

    # Deletes
    for path in sorted(base_paths - target_paths):
        entry = base_files[path]
        changes.append({"path": path, "operation": "delete", "beforeSha256": entry.get("sha256")})

    # Modifies
    for path in sorted(base_paths & target_paths):
        b = base_files[path]
        t = target_files[path]
        if b.get("sha256") != t.get("sha256"):
            changes.append(
                {
                    "path": path,
                    "operation": "modify",
                    "beforeSha256": b.get("sha256"),
                    "afterSha256": t.get("sha256"),
                    "contentBase64": t.get("contentBase64"),
                }
            )

    # Conflicts: compare current repo sha (at baseCommitSha) with baseline sha (base snapshot)
    conflicts: List[Dict[str, Any]] = []
    for change in changes:
        path = str(change.get("path") or "")
        if not path:
            continue
        base_sha = base_files.get(path, {}).get("sha256")
        target_sha = target_files.get(path, {}).get("sha256")
        repo_sha = repo_file_shas.get(path)
        operation = change.get("operation")

        if operation == "add":
            # Baseline did not have it; if repo now has it, we would overwrite user-added file in the PR diff.
            if repo_sha:
                conflicts.append(
                    {
                        "path": path,
                        "reason": "repo_has_file",
                        "baseSha256": None,
                        "repoSha256": repo_sha,
                        "targetSha256": target_sha,
                    }
                )
        elif operation == "modify":
            if repo_sha != base_sha:
                conflicts.append(
                    {
                        "path": path,
                        "reason": "repo_modified_since_baseline",
                        "baseSha256": base_sha,
                        "repoSha256": repo_sha,
                        "targetSha256": target_sha,
                    }
                )
        elif operation == "delete":
            # If repo still has the file but it changed, flag conflict. If repo already removed it, treat as idempotent.
            if repo_sha and repo_sha != base_sha:
                conflicts.append(
                    {
                        "path": path,
                        "reason": "repo_modified_since_baseline",
                        "baseSha256": base_sha,
                        "repoSha256": repo_sha,
                        "targetSha256": None,
                    }
                )

    patch_id = _patch_id(
        repo_url=repo_url,
        base_snapshot_id=base_snapshot_id,
        target_snapshot_id=target_snapshot_id,
        base_commit_sha=base_commit_sha,
    )

    now = datetime.now(UTC)
    doc: Dict[str, Any] = {
        **build_app_scope_filter(resolved_app_id),
        "patchId": patch_id,
        "appId": resolved_app_id,
        "createdAt": now,
        "workflowType": str(workflow_type or "").strip() or "app-generator",
        "repoUrl": str(repo_url).strip() if repo_url else None,
        "baseCommitSha": str(base_commit_sha).strip() if base_commit_sha else None,
        "baseSnapshotId": base_snapshot_id,
        "targetSnapshotId": target_snapshot_id,
        "changes": changes,
        "conflicts": conflicts,
    }
    return doc


async def persist_patchset(*, patchset_doc: Dict[str, Any]) -> str:
    await _ensure_indexes()
    patch_id = (patchset_doc or {}).get("patchId")
    app_id = (patchset_doc or {}).get("app_id")
    if not patch_id or not app_id:
        raise ValueError("patchset_doc must include patchId and app_id")
    client = get_mongo_client()
    coll = client[_db_name()][_patchsets_collection()]
    await coll.replace_one({"patchId": patch_id, **build_app_scope_filter(app_id)}, patchset_doc, upsert=True)
    return str(patch_id)


__all__ = [
    "extract_files_from_zip_bundle",
    "build_snapshot_document",
    "build_snapshot_document_from_hashes",
    "persist_snapshot",
    "get_snapshot",
    "get_latest_snapshot",
    "compute_patchset_document",
    "persist_patchset",
]
