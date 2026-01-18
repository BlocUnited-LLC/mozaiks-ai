"""
generate_and_download - Bundle generated app code and present FileDownloadCenter UI.

This tool:
1) Collects latest agent JSON outputs for the chat/app
2) Extracts `code_files` from any agent output
3) Writes files to disk under generated_apps/<app_id>/<chat_id>/<bundle_name>/
4) Creates a ZIP bundle
5) Presents FileDownloadCenter UI and (optionally) triggers export_to_github
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Annotated, Dict, List, Optional

from mozaiksai.core.data.persistence.persistence_manager import AG2PersistenceManager
from workflows._shared.workflow_exports import get_latest_workflow_export
from workflows._shared.agent_endpoints import resolve_agent_api_url, resolve_agent_websocket_url
from mozaiksai.core.workflow.outputs.ui_tools import UIToolError, use_ui_tool
from logs.logging_config import get_workflow_logger

from workflows.AppGenerator.tools.export_app_code import export_app_code_to_github

try:
    from logs.tools_logs import get_tool_logger as _get_tool_logger, log_tool_event as _log_tool_event  # type: ignore
except Exception:  # pragma: no cover
    _get_tool_logger = None  # type: ignore
    _log_tool_event = None  # type: ignore


def _safe_relpath(raw: str) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    path = raw.replace("\\", "/").strip()
    if not path or path.startswith("/"):
        return None
    p = PurePosixPath(path)
    if p.is_absolute():
        return None
    if any(part in {".."} for part in p.parts):
        return None
    return str(p)


def _discover_code_files(col: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _agent_name, data in (col or {}).items():
        try:
            if isinstance(data, dict):
                cf = data.get("code_files")
                if isinstance(cf, list):
                    for item in cf:
                        if not isinstance(item, dict):
                            continue
                        filename = item.get("filename") or item.get("path")
                        content = item.get("content") or item.get("filecontent")
                        if not filename or content is None:
                            continue
                        safe = _safe_relpath(str(filename))
                        if not safe:
                            continue
                        out[safe] = str(content)
            elif isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict) and isinstance(parsed.get("code_files"), list):
                        for item in parsed.get("code_files", []):
                            if not isinstance(item, dict):
                                continue
                            filename = item.get("filename") or item.get("path")
                            content = item.get("content") or item.get("filecontent")
                            if not filename or content is None:
                                continue
                            safe = _safe_relpath(str(filename))
                            if not safe:
                                continue
                            out[safe] = str(content)
                except Exception:
                    pass
        except Exception:
            continue
    return out


def _format_bytes(num: int) -> str:
    try:
        value: float = float(num)
        for unit in ["bytes", "KB", "MB", "GB", "TB"]:
            if value < 1024 or unit == "TB":
                if unit == "bytes":
                    return f"{int(value)} bytes"
                return f"{value:.1f} {unit}"
            value /= 1024.0
    except Exception:
        return f"{num} bytes"
    return f"{num} bytes"


def _ensure_env_line(lines: List[str], key: str, value: str) -> List[str]:
    normalized_key = key.strip()
    if not normalized_key:
        return lines
    rendered = f"{normalized_key}={value or ''}"

    out: List[str] = []
    replaced = False
    for line in lines:
        if not isinstance(line, str):
            continue
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        k = stripped.split("=", 1)[0].strip()
        if k == normalized_key:
            out.append(rendered)
            replaced = True
        else:
            out.append(line)

    if not replaced:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(rendered)
    return out


def _admin_surfaces_default_manifest() -> Dict[str, Any]:
    return {
        "version": 1,
        "modules": [
            {
                "moduleId": "agents.monitoring",
                "displayName": "Agent Monitoring",
                "category": "agents",
                "admin": {"enabled": True, "scope": "app"},
                "settingsSchema": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "default": True},
                        "pollIntervalSeconds": {"type": "integer", "minimum": 10, "default": 60},
                    },
                    "required": ["enabled"],
                },
                "actions": [
                    {"actionId": "runNow", "label": "Run now", "danger": False},
                    {"actionId": "disable", "label": "Disable", "danger": True},
                ],
            }
        ],
    }


def _admin_surfaces_md() -> str:
    return """# Admin Surfaces (Mozaiks) - Contract (v1)

Generated apps include a small, **platform-only** admin API surface plus a versioned
manifest describing which admin modules exist and how they can be configured.

## Platform proxy

In production, Mozaiks calls these endpoints through the app's public base URL:

`https://<baseUrl>/__mozaiks/admin/*`

Your hosting should route/proxy `/__mozaiks/admin/*` to the admin server process.
The admin key is **never shown in MOZ-UI** and should only be injected server-side.

## Production env vars

Required:
- `MOZAIKS_APP_ADMIN_KEY`
- `MONGODB_URI` (preferred) or `DATABASE_URI` (fallback)

Optional:
- `MOZAIKS_ADMIN_PORT` (default `3001`)
- `MONGODB_DB_NAME` (defaults to `app`)

## Files

- `admin_surfaces.json` - manifest (versioned)
- `server/mozaiks_admin_server.cjs` - Node admin API server (stub + reference implementation)
- `server/mozaiks_admin/**` - module registry + settings persistence helpers

## Auth (v1)

All admin endpoints require the request header:

`X-Mozaiks-App-Admin-Key: <secret>`

The secret must be provided via environment variable (never shown in MOZ-UI):

- `MOZAIKS_APP_ADMIN_KEY`

## Persistence (MongoDB)

Module settings are stored in the app database in collection:

- `module_settings` (keyed by `moduleId`)

Env vars used:

- `MONGODB_URI` (preferred) or `DATABASE_URI` (fallback)
- `MONGODB_DB_NAME` (optional; defaults to `app`)

## Server port

- `MOZAIKS_ADMIN_PORT` (default `3001`)

## Endpoints

Base path: `/__mozaiks/admin`

### List modules

`GET /__mozaiks/admin/modules`

Response:
```json
{
  "version": 1,
  "modules": [
    {
      "moduleId": "agents.monitoring",
      "displayName": "Agent Monitoring",
      "category": "agents",
      "admin": { "enabled": true, "scope": "app" },
      "settingsSchema": { "...": "..." },
      "actions": [{ "actionId": "runNow", "label": "Run now", "danger": false }]
    }
  ]
}
```

### Read/update settings

`GET /__mozaiks/admin/modules/{moduleId}/settings`

Response:
```json
{
  "moduleId": "agents.monitoring",
  "settings": { "enabled": true, "pollIntervalSeconds": 60 },
  "source": "default|db",
  "updatedAt": null
}
```

`PUT /__mozaiks/admin/modules/{moduleId}/settings`

Request body (either shape is accepted):
```json
{ "enabled": true, "pollIntervalSeconds": 30 }
```
or
```json
{ "settings": { "enabled": true, "pollIntervalSeconds": 30 } }
```

Response:
```json
{ "ok": true, "moduleId": "agents.monitoring", "settings": { "enabled": true, "pollIntervalSeconds": 30 } }
```

### Status

`GET /__mozaiks/admin/modules/{moduleId}/status`

Response:
```json
{
  "moduleId": "agents.monitoring",
  "enabled": true,
  "configured": false,
  "status": "unknown"
}
```

### Actions

`POST /__mozaiks/admin/modules/{moduleId}/actions/{actionId}`

Response:
```json
{ "accepted": true, "moduleId": "agents.monitoring", "actionId": "runNow" }
```

## Local dev

Run the admin server (separate from the frontend dev server):

- `npm run mozaiks:admin`

Default port: `3001` (override with `MOZAIKS_ADMIN_PORT`).
"""


def _inject_admin_surfaces(files_map: Dict[str, str]) -> None:
    # Manifest + docs (do not overwrite if generator provided them)
    if "admin_surfaces.json" not in files_map:
        files_map["admin_surfaces.json"] = json.dumps(_admin_surfaces_default_manifest(), indent=2) + "\n"
    if "ADMIN_SURFACES.md" not in files_map:
        files_map["ADMIN_SURFACES.md"] = _admin_surfaces_md()

    # Admin API server (CommonJS so it works whether or not package.json sets type=module)
    server_files: Dict[str, str] = {
        "server/mozaiks_admin_server.cjs": """/* Mozaiks Admin API Server (v1)

This is a lightweight reference implementation for admin surfaces.
It is intended to run behind the Mozaiks platform proxy (not exposed to end users).
*/

const express = require('express');
const { createAdminRouter } = require('./mozaiks_admin/router.cjs');

const rawPort = process.env.MOZAIKS_ADMIN_PORT || process.env.PORT || '3001';
const parsedPort = Number.parseInt(String(rawPort), 10);
const port = Number.isFinite(parsedPort) ? parsedPort : 3001;

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '1mb' }));

app.use('/__mozaiks/admin', createAdminRouter());

app.listen(port, () => {
  // Do not log secrets; only basic status.
  // eslint-disable-next-line no-console
  console.log(`[mozaiks] admin server listening on :${port}`);
});
""",
        "server/mozaiks_admin/router.cjs": """const express = require('express');
const path = require('path');
const fs = require('fs');
const { requireAdminKey } = require('./security.cjs');
const { getSettingsRecord, upsertSettingsRecord } = require('./store.cjs');

function manifestPath() {
  return path.resolve(__dirname, '..', '..', 'admin_surfaces.json');
}

function loadManifest() {
  try {
    const raw = fs.readFileSync(manifestPath(), 'utf-8');
    const parsed = JSON.parse(raw);
    const version = typeof parsed?.version === 'number' ? parsed.version : 1;
    const modules = Array.isArray(parsed?.modules) ? parsed.modules : [];
    return { version, modules };
  } catch {
    return { version: 1, modules: [] };
  }
}

function findModule(manifest, moduleId) {
  return (manifest.modules || []).find((m) => m && m.moduleId === moduleId) || null;
}

function defaultsFromSchema(schema) {
  const out = {};
  if (!schema || typeof schema !== 'object') return out;
  if (schema.type !== 'object') return out;
  const props = schema.properties && typeof schema.properties === 'object' ? schema.properties : null;
  if (!props) return out;
  for (const [key, def] of Object.entries(props)) {
    if (!def || typeof def !== 'object') continue;
    if (Object.prototype.hasOwnProperty.call(def, 'default')) out[key] = def.default;
  }
  return out;
}

function mergeDefaults(defaults, settings) {
  return { ...(defaults || {}), ...(settings || {}) };
}

function moduleImplPath(moduleId) {
  const parts = String(moduleId || '').split('.').filter(Boolean);
  return path.resolve(__dirname, 'modules', ...parts) + '.cjs';
}

function loadModuleImpl(moduleId) {
  try {
    const p = moduleImplPath(moduleId);
    if (!fs.existsSync(p)) return {};
    // eslint-disable-next-line global-require, import/no-dynamic-require
    return require(p);
  } catch {
    return {};
  }
}

function actionExists(mod, actionId) {
  const actions = Array.isArray(mod?.actions) ? mod.actions : [];
  return actions.some((a) => a && a.actionId === actionId);
}

function createAdminRouter() {
  const router = express.Router();

  router.get('/modules', requireAdminKey, (_req, res) => {
    const manifest = loadManifest();
    res.json({ version: manifest.version, modules: manifest.modules });
  });

  router.get('/modules/:moduleId/settings', requireAdminKey, async (req, res) => {
    const moduleId = req.params.moduleId;
    const manifest = loadManifest();
    const mod = findModule(manifest, moduleId);
    if (!mod) return res.status(404).json({ error: 'Unknown moduleId', error_code: 'UNKNOWN_MODULE', moduleId });

    const defaults = defaultsFromSchema(mod.settingsSchema);
    try {
      const rec = await getSettingsRecord(moduleId);
      if (!rec) {
        return res.json({ moduleId, settings: mergeDefaults(defaults, null), source: 'default', updatedAt: null });
      }
      return res.json({ moduleId, settings: mergeDefaults(defaults, rec.settings), source: 'db', updatedAt: rec.updatedAt || null });
    } catch (e) {
      return res.status(503).json({ error: 'Settings store unavailable', error_code: 'DB_UNAVAILABLE', message: String(e?.message || e) });
    }
  });

  router.put('/modules/:moduleId/settings', requireAdminKey, async (req, res) => {
    const moduleId = req.params.moduleId;
    const manifest = loadManifest();
    const mod = findModule(manifest, moduleId);
    if (!mod) return res.status(404).json({ error: 'Unknown moduleId', error_code: 'UNKNOWN_MODULE', moduleId });

    const body = req.body;
    const nextSettings = body && typeof body === 'object' ? (body.settings && typeof body.settings === 'object' ? body.settings : body) : null;
    if (!nextSettings || typeof nextSettings !== 'object' || Array.isArray(nextSettings)) {
      return res.status(400).json({ error: 'Invalid settings payload', error_code: 'INVALID_BODY' });
    }

    try {
      const rec = await upsertSettingsRecord(moduleId, nextSettings);
      return res.json({ ok: true, moduleId, settings: rec.settings });
    } catch (e) {
      return res.status(503).json({ error: 'Settings store unavailable', error_code: 'DB_UNAVAILABLE', message: String(e?.message || e) });
    }
  });

  router.get('/modules/:moduleId/status', requireAdminKey, async (req, res) => {
    const moduleId = req.params.moduleId;
    const manifest = loadManifest();
    const mod = findModule(manifest, moduleId);
    if (!mod) return res.status(404).json({ error: 'Unknown moduleId', error_code: 'UNKNOWN_MODULE', moduleId });

    const defaults = defaultsFromSchema(mod.settingsSchema);
    let rec = null;
    try {
      rec = await getSettingsRecord(moduleId);
    } catch {
      rec = null;
    }
    const effective = mergeDefaults(defaults, rec ? rec.settings : null);
    const enabled = typeof effective.enabled === 'boolean' ? effective.enabled : true;

    const impl = loadModuleImpl(moduleId);
    let status = { status: 'unknown' };
    if (impl && typeof impl.getStatus === 'function') {
      try {
        status = await impl.getStatus({ moduleId, settings: effective, configured: !!rec, manifest: mod });
      } catch {
        status = { status: 'unknown' };
      }
    }
    return res.json({ moduleId, enabled, configured: !!rec, ...status });
  });

  router.post('/modules/:moduleId/actions/:actionId', requireAdminKey, async (req, res) => {
    const moduleId = req.params.moduleId;
    const actionId = req.params.actionId;
    const manifest = loadManifest();
    const mod = findModule(manifest, moduleId);
    if (!mod) return res.status(404).json({ error: 'Unknown moduleId', error_code: 'UNKNOWN_MODULE', moduleId });
    if (!actionExists(mod, actionId)) {
      return res.status(404).json({ error: 'Unknown actionId', error_code: 'UNKNOWN_ACTION', moduleId, actionId });
    }

    const defaults = defaultsFromSchema(mod.settingsSchema);
    let rec = null;
    try {
      rec = await getSettingsRecord(moduleId);
    } catch {
      rec = null;
    }
    const effective = mergeDefaults(defaults, rec ? rec.settings : null);

    const impl = loadModuleImpl(moduleId);
    if (impl && typeof impl.runAction === 'function') {
      try {
        const result = await impl.runAction({ moduleId, actionId, settings: effective, payload: req.body || {}, manifest: mod });
        return res.json({ accepted: true, moduleId, actionId, ...(result && typeof result === 'object' ? result : {}) });
      } catch {
        return res.json({ accepted: true, moduleId, actionId });
      }
    }
    return res.json({ accepted: true, moduleId, actionId });
  });

  return router;
}

module.exports = { createAdminRouter };
""",
        "server/mozaiks_admin/security.cjs": """const crypto = require('crypto');

function timingSafeEqual(a, b) {
  const aBuf = Buffer.from(String(a || ''), 'utf-8');
  const bBuf = Buffer.from(String(b || ''), 'utf-8');
  if (aBuf.length !== bBuf.length) return false;
  return crypto.timingSafeEqual(aBuf, bBuf);
}

function requireAdminKey(req, res, next) {
  const expected = process.env.MOZAIKS_APP_ADMIN_KEY;
  if (!expected) {
    return res.status(503).json({
      error: 'Admin key not configured',
      error_code: 'ADMIN_KEY_NOT_CONFIGURED',
      message: 'Set MOZAIKS_APP_ADMIN_KEY in the app environment.',
    });
  }
  const provided = req.get('X-Mozaiks-App-Admin-Key');
  if (!provided || !timingSafeEqual(provided, expected)) {
    return res.status(401).json({ error: 'Unauthorized', error_code: 'UNAUTHORIZED' });
  }
  return next();
}

module.exports = { requireAdminKey };
""",
        "server/mozaiks_admin/store.cjs": """const { MongoClient } = require('mongodb');

let clientPromise = null;
let ensured = false;

function getMongoUri() {
  const uri = process.env.MONGODB_URI || process.env.DATABASE_URI || null;
  if (!uri) return null;
  const trimmed = String(uri).trim();
  return trimmed || null;
}

function getDbName() {
  const explicit = process.env.MONGODB_DB_NAME;
  if (explicit && String(explicit).trim()) return String(explicit).trim();
  return 'app';
}

async function getClient() {
  const uri = getMongoUri();
  if (!uri) throw new Error('MONGODB_URI (or DATABASE_URI) is not configured');
  if (!clientPromise) {
    const client = new MongoClient(uri);
    clientPromise = client.connect();
  }
  const client = await clientPromise;
  const db = client.db(getDbName());
  const coll = db.collection('module_settings');
  if (!ensured) {
    ensured = true;
    try {
      await coll.createIndex({ moduleId: 1 }, { unique: true });
    } catch {}
  }
  return { client, coll };
}

async function getSettingsRecord(moduleId) {
  const { coll } = await getClient();
  const doc = await coll.findOne({ moduleId: String(moduleId) });
  if (!doc) return null;
  return {
    moduleId: doc.moduleId,
    settings: doc.settings || {},
    createdAt: doc.createdAt || null,
    updatedAt: doc.updatedAt || null,
  };
}

async function upsertSettingsRecord(moduleId, settings) {
  const { coll } = await getClient();
  const now = new Date();
  const update = {
    $set: { moduleId: String(moduleId), settings: settings || {}, updatedAt: now },
    $setOnInsert: { createdAt: now },
  };
  await coll.updateOne({ moduleId: String(moduleId) }, update, { upsert: true });
  const doc = await coll.findOne({ moduleId: String(moduleId) });
  return {
    moduleId: doc.moduleId,
    settings: doc.settings || {},
    createdAt: doc.createdAt || null,
    updatedAt: doc.updatedAt || null,
  };
}

module.exports = { getSettingsRecord, upsertSettingsRecord };
""",
        "server/mozaiks_admin/modules/agents/monitoring.cjs": """/* Module stub: agents.monitoring */

async function getStatus({ settings }) {
  const enabled = typeof settings?.enabled === 'boolean' ? settings.enabled : true;
  if (!enabled) return { status: 'disabled' };
  return { status: 'unknown' };
}

async function runAction({ actionId }) {
  return { message: `Action '${actionId}' accepted (stub)` };
}

module.exports = { getStatus, runAction };
""",
    }

    for path, content in server_files.items():
        if path not in files_map:
            files_map[path] = content if content.endswith("\n") else content + "\n"

    # Best-effort: ensure server deps + script exist (do not fail bundling if invalid JSON).
    pkg_raw = files_map.get("package.json")
    if isinstance(pkg_raw, str) and pkg_raw.strip():
        try:
            pkg = json.loads(pkg_raw)
            if isinstance(pkg, dict):
                deps = pkg.get("dependencies")
                if not isinstance(deps, dict):
                    deps = {}
                    pkg["dependencies"] = deps
                deps.setdefault("express", "^4.18.2")
                deps.setdefault("mongodb", "^6.3.0")

                scripts = pkg.get("scripts")
                if not isinstance(scripts, dict):
                    scripts = {}
                    pkg["scripts"] = scripts
                scripts.setdefault("mozaiks:admin", "node server/mozaiks_admin_server.cjs")

                files_map["package.json"] = json.dumps(pkg, indent=2) + "\n"
        except Exception:
            pass


async def _inject_agent_context_env(*, files_map: Dict[str, str], app_id: str, context_variables: Optional[Any]) -> None:
    """Best-effort: ensure bundle contains agent endpoint env placeholders."""

    agent_ws = None
    agent_api = None

    if context_variables is not None and hasattr(context_variables, "get"):
        try:
            agent_ws = context_variables.get("agent_websocket_url")
            agent_api = context_variables.get("agent_api_url")
        except Exception:
            agent_ws = None
            agent_api = None

    if not agent_ws or not agent_api:
        try:
            rec = await get_latest_workflow_export(app_id=app_id, workflow_type="agent-generator")
        except Exception:
            rec = None
        if isinstance(rec, dict):
            agent_ws = agent_ws or rec.get("agent_websocket_url")
            agent_api = agent_api or rec.get("agent_api_url")

    agent_ws = agent_ws or resolve_agent_websocket_url(app_id)
    agent_api = agent_api or resolve_agent_api_url(app_id)

    raw_env = files_map.get(".env.example") or ""
    lines = raw_env.splitlines()
    needs_guidance = not agent_ws or not agent_api
    guidance_marker = "# MozaiksAI: Agent endpoint configuration"
    if needs_guidance and guidance_marker not in raw_env:
        lines = [
            guidance_marker,
            "# VITE_AGENT_WEBSOCKET_URL / VITE_AGENT_API_URL are blank because this runtime could not resolve agent endpoints.",
            "# Fix: set MOZAIKS_AGENT_WEBSOCKET_URL_TEMPLATE and MOZAIKS_AGENT_API_URL_TEMPLATE in MozaiksAI `.env`,",
            "# or run AgentGenerator export to record endpoints into WorkflowExports, then regenerate this bundle.",
            "",
            *lines,
        ]
    lines = _ensure_env_line(lines, "VITE_APP_ID", str(app_id))
    lines = _ensure_env_line(lines, "VITE_AGENT_WEBSOCKET_URL", str(agent_ws or ""))
    lines = _ensure_env_line(lines, "VITE_AGENT_API_URL", str(agent_api or ""))
    files_map[".env.example"] = "\n".join(lines).rstrip() + "\n"


async def _emit_deployment_event(*, chat_id: Optional[str], status: str, data: dict) -> None:
    if not chat_id:
        return
    try:
        from mozaiksai.core.transport.simple_transport import SimpleTransport

        transport = await SimpleTransport.get_instance()
        await transport.send_event_to_ui(
            {"type": f"chat.deployment_{status}", "data": {"timestamp": datetime.now(timezone.utc).isoformat(), **data}},
            chat_id,
        )
    except Exception:
        return


async def generate_and_download(
    DownloadRequest: Annotated[Dict[str, Any], "Download configuration (confirmation_only/storage_backend)."],
    agent_message: Annotated[str, "Concise message (<=140 chars) shown to user in download UI."],
    context_variables: Annotated[Optional[Any], "Injected runtime context."] = None,
) -> Dict[str, Any]:
    confirmation_only = bool((DownloadRequest or {}).get("confirmation_only", False))
    storage_backend = (DownloadRequest or {}).get("storage_backend", "none")
    description = (DownloadRequest or {}).get("description")

    chat_id: Optional[str] = None
    app_id: Optional[str] = None
    user_id: Optional[str] = None
    workflow_name = "AppGenerator"
    if context_variables is not None and hasattr(context_variables, "get"):
        try:
            chat_id = context_variables.get("chat_id")
            app_id = context_variables.get("app_id")
            user_id = context_variables.get("user_id")
            workflow_name = context_variables.get("workflow_name") or workflow_name
        except Exception:
            pass

    wf_logger = get_workflow_logger(workflow_name=workflow_name, chat_id=chat_id, app_id=app_id)
    tlog = None
    if _get_tool_logger:
        try:
            tlog = _get_tool_logger(tool_name="GenerateAndDownloadApp", chat_id=chat_id, app_id=app_id, workflow_name=workflow_name)
        except Exception:
            tlog = None

    agent_message_text = agent_message or description or "Your app bundle is ready to download."
    agent_message_id = f"msg_{uuid.uuid4().hex[:10]}"

    if not chat_id or not app_id:
        return {"status": "error", "message": "chat_id and app_id are required"}

    pm = AG2PersistenceManager()
    collected = await pm.gather_latest_agent_jsons(chat_id=chat_id, app_id=app_id)
    files_map = _discover_code_files(collected)
    if not files_map:
        return {"status": "error", "message": "No code_files found to bundle."}
    await _inject_agent_context_env(files_map=files_map, app_id=str(app_id), context_variables=context_variables)
    _inject_admin_surfaces(files_map)

    bundle_name = "GeneratedApp"
    try:
        # Best-effort: allow agent to provide a bundle name
        for _agent, data in collected.items():
            if isinstance(data, dict):
                candidate = data.get("app_name") or data.get("bundle_name") or data.get("project_name")
                if isinstance(candidate, str) and candidate.strip():
                    bundle_name = candidate.strip()
                    break
    except Exception:
        pass

    # Normalize bundle name to a safe folder name
    bundle_name = "".join(ch for ch in bundle_name if ch.isalnum() or ch in {"-", "_"}).strip() or "GeneratedApp"

    base_dir = Path("generated_apps") / str(app_id) / str(chat_id)
    app_dir = base_dir / bundle_name
    app_dir.mkdir(parents=True, exist_ok=True)

    if tlog and _log_tool_event:
        _log_tool_event(tlog, action="write_files", status="start", file_count=len(files_map))

    written_paths: List[str] = []
    for rel_path, content in files_map.items():
        safe = _safe_relpath(rel_path)
        if not safe:
            continue
        out_path = app_dir / safe
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(str(content), encoding="utf-8")
        written_paths.append(safe)

    zip_path = base_dir / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for rel_path in written_paths:
            file_path = app_dir / rel_path
            if file_path.exists() and file_path.is_file():
                zipf.write(file_path, arcname=f"{bundle_name}/{rel_path}")

    zip_size = zip_path.stat().st_size
    ui_files = [
        {
            "name": f"{bundle_name}.zip",
            "size": _format_bytes(zip_size),
            "size_bytes": zip_size,
            "path": str(zip_path.resolve()),
            "id": "file-zip-bundle",
            "type": "zip",
        }
    ]

    ui_payload = {
        "downloadType": "single",
        "files": [] if confirmation_only else ui_files,
        "agent_message": agent_message_text,
        "description": agent_message_text,
        "title": "App Workbench",
        "workflow_name": workflow_name,
        "agent_message_id": agent_message_id,
        "stage": "confirm" if confirmation_only else "files_ready",
        # Workbench context (best-effort): allow ChatUI to render file tree + editor + preview.
        "generated_files": files_map,
    }
    # Best-effort: include validation context if present (set by validate_app_in_sandbox).
    if context_variables is not None and hasattr(context_variables, "get"):
        try:
            ui_payload["app_validation_passed"] = context_variables.get("app_validation_passed")
            ui_payload["app_validation_preview_url"] = context_variables.get("app_validation_preview_url")
            ui_payload["app_validation_result"] = context_variables.get("app_validation_result")
            ui_payload["integration_tests_passed"] = context_variables.get("integration_tests_passed")
            ui_payload["integration_test_result"] = context_variables.get("integration_test_result")
        except Exception:
            pass

    try:
        response = await use_ui_tool(
            tool_id="AppWorkbench",
            payload=ui_payload,
            chat_id=chat_id,
            workflow_name=workflow_name,
        )
    except UIToolError:
        raise
    except Exception as e:
        wf_logger.error(f"UI interaction failed: {e}", exc_info=True)
        raise UIToolError("Failed during file download UI interaction")

    if response.get("status") == "cancelled":
        return {
            "status": "cancelled",
            "ui_response": response,
            "agent_message_id": agent_message_id,
            "ui_files": [],
            "message": "User declined download",
        }

    # Optional GitHub export (triggered by FileDownloadCenter action)
    deployment_result: Optional[Dict[str, Any]] = None
    try:
        action = None
        if isinstance(response, dict):
            action = response.get("action")
            if not action and isinstance(response.get("data"), dict):
                action = response["data"].get("action")

        if action == "export_to_github":
            # Safety gate: ensure validation + integration checks passed before allowing export.
            allow_export = True
            reasons: List[str] = []
            try:
                if context_variables is not None and hasattr(context_variables, "get"):
                    if context_variables.get("app_validation_passed") is not True:
                        allow_export = False
                        reasons.append("E2B validation has not passed.")
                    if context_variables.get("integration_tests_passed") is not True:
                        allow_export = False
                        reasons.append("Integration checks have not passed.")
            except Exception:
                # If we cannot reliably read context, fail closed.
                allow_export = False
                reasons.append("Unable to confirm validation/integration status.")

            if not allow_export:
                error_msg = "Export blocked: " + " ".join(reasons) if reasons else "Export blocked."
                wf_logger.warning(error_msg)
                await _emit_deployment_event(
                    chat_id=chat_id,
                    status="failed",
                    data={
                        "app_id": app_id,
                        "error": error_msg,
                        "message": error_msg,
                        "blocked": True,
                        "reasons": reasons,
                    },
                )
                deployment_result = {
                    "success": False,
                    "error": error_msg,
                    "workflow_type": "app-generator",
                    "blocked": True,
                    "reasons": reasons,
                    "app_validation_passed": (
                        context_variables.get("app_validation_passed") if context_variables is not None and hasattr(context_variables, "get") else None
                    ),
                    "integration_tests_passed": (
                        context_variables.get("integration_tests_passed") if context_variables is not None and hasattr(context_variables, "get") else None
                    ),
                }
                action = None
                return {
                    "status": "success",
                    "ui_response": response,
                    "agent_message_id": agent_message_id,
                    "ui_files": ui_files,
                    "bundle_dir": str(app_dir.resolve()),
                    "bundle_zip": str(zip_path.resolve()),
                    "deployment": deployment_result,
                    "file_count": len(written_paths),
                    "files_written": written_paths,
                    "storage_backend": storage_backend,
                }

            repo_name = None
            commit_message = "Initial code generation from Mozaiks AI"
            if isinstance(response, dict) and isinstance(response.get("data"), dict):
                repo_name = response["data"].get("repo_name") or response["data"].get("repoName")
                commit_message = (
                    response["data"].get("commit_message")
                    or response["data"].get("commitMessage")
                    or commit_message
                )
            deployment_result = await export_app_code_to_github(
                bundle_path=str(zip_path.resolve()),
                app_id=app_id,
                repo_name=repo_name,
                commit_message=commit_message,
                user_id=user_id,
                context_variables=context_variables,
            )
    except Exception as deploy_err:
        wf_logger.warning(f"GitHub export flow failed: {deploy_err}")

    return {
        "status": "success",
        "ui_response": response,
        "agent_message_id": agent_message_id,
        "ui_files": ui_files,
        "bundle_dir": str(app_dir.resolve()),
        "bundle_zip": str(zip_path.resolve()),
        **({"deployment": deployment_result} if deployment_result is not None else {}),
        "file_count": len(written_paths),
        "files_written": written_paths,
        "storage_backend": storage_backend,
    }
