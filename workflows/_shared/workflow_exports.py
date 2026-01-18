"""Workflow-time export persistence (app-scoped).

This module stores lightweight, app-scoped "export artifacts" that allow downstream
workflows (e.g., AppGenerator) to discover upstream deployment/export results
from prior workflows (e.g., AgentGenerator) without leaking across tenants.

Storage:
- Database: MozaiksAI (override via MOZAIKS_EXPORTS_DB)
- Collection: WorkflowExports (override via MOZAIKS_WORKFLOW_EXPORTS_COLLECTION)

Notes:
- Records are append-only for auditability; readers fetch the most recent record.
- No secrets should be stored here (repo URLs and public endpoints only).
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Any, Dict, Optional

from logs.logging_config import get_core_logger

from mozaiksai.core.core_config import get_mongo_client
from mozaiksai.core.multitenant import build_app_scope_filter, coalesce_app_id

logger = get_core_logger("workflow_exports")


def _exports_db_name() -> str:
    return (os.getenv("MOZAIKS_EXPORTS_DB") or "MozaiksAI").strip() or "MozaiksAI"


def _exports_collection_name() -> str:
    return (os.getenv("MOZAIKS_WORKFLOW_EXPORTS_COLLECTION") or "WorkflowExports").strip() or "WorkflowExports"


async def record_workflow_export(
    *,
    app_id: str,
    user_id: Optional[str],
    workflow_type: str,
    repo_url: Optional[str],
    job_id: Optional[str],
    meta: Optional[Dict[str, Any]] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an export record for later discovery."""

    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        raise ValueError("app_id is required")
    wf_type = str(workflow_type or "").strip()
    if not wf_type:
        raise ValueError("workflow_type is required")

    doc: Dict[str, Any] = {
        **build_app_scope_filter(resolved_app_id),
        "workflow_type": wf_type,
        "repo_url": str(repo_url) if repo_url else None,
        "job_id": str(job_id) if job_id else None,
        "user_id": str(user_id) if user_id else None,
        "created_at": datetime.now(UTC),
    }
    if isinstance(meta, dict) and meta:
        doc["meta"] = meta
    if isinstance(extra_fields, dict) and extra_fields:
        protected = {"app_id", "workflow_type", "repo_url", "job_id", "user_id", "created_at", "meta"}
        for key, value in extra_fields.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if key in protected:
                continue
            doc[key] = value

    client = get_mongo_client()
    coll = client[_exports_db_name()][_exports_collection_name()]
    await coll.insert_one(doc)


async def get_latest_workflow_export(
    *,
    app_id: str,
    workflow_type: str,
) -> Optional[Dict[str, Any]]:
    """Fetch the most recent export record for a workflow_type within an app scope."""

    resolved_app_id = coalesce_app_id(app_id=app_id)
    if not resolved_app_id:
        return None
    wf_type = str(workflow_type or "").strip()
    if not wf_type:
        return None

    client = get_mongo_client()
    coll = client[_exports_db_name()][_exports_collection_name()]

    query = {"workflow_type": wf_type, **build_app_scope_filter(resolved_app_id)}
    cursor = coll.find(query).sort("_id", -1).limit(1)
    docs = await cursor.to_list(length=1)
    doc = docs[0] if docs else None
    if not isinstance(doc, dict):
        return None
    doc.pop("_id", None)
    return doc


__all__ = ["record_workflow_export", "get_latest_workflow_export"]
