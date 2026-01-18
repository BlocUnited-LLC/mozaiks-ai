"""Workflow-time endpoint templating helpers for generated apps.

These helpers keep platform-specific endpoint shapes behind env vars so the
runtime remains open-source friendly.

Env vars (recommended):
- MOZAIKS_AGENT_WEBSOCKET_URL_TEMPLATE="wss://agents.example.com/ws/{app_id}"
- MOZAIKS_AGENT_API_URL_TEMPLATE="https://agents.example.com/api/{app_id}"

Template tokens supported:
- {app_id}
- {{app_id}}
"""

from __future__ import annotations

import os
from typing import Optional

from mozaiksai.core.multitenant import coalesce_app_id


def _get_env_any(*keys: str) -> Optional[str]:
    for key in keys:
        raw = os.getenv(key)
        if raw is None:
            continue
        val = str(raw).strip()
        if val:
            return val
    return None


def _format_template(template: Optional[str], app_id: str) -> Optional[str]:
    if not template:
        return None
    t = str(template).strip()
    if not t:
        return None
    return (
        t.replace("{app_id}", app_id)
        .replace("{{app_id}}", app_id)
        .replace("{APP_ID}", app_id)
        .replace("{{APP_ID}}", app_id)
    )


def resolve_agent_websocket_url(app_id: str) -> Optional[str]:
    resolved = coalesce_app_id(app_id=app_id)
    if not resolved:
        return None
    template = _get_env_any("MOZAIKS_AGENT_WEBSOCKET_URL_TEMPLATE", "MOZAIKS_AGENT_WS_URL_TEMPLATE")
    return _format_template(template, resolved)


def resolve_agent_api_url(app_id: str) -> Optional[str]:
    resolved = coalesce_app_id(app_id=app_id)
    if not resolved:
        return None
    template = _get_env_any("MOZAIKS_AGENT_API_URL_TEMPLATE", "MOZAIKS_AGENT_HTTP_URL_TEMPLATE")
    return _format_template(template, resolved)


__all__ = ["resolve_agent_websocket_url", "resolve_agent_api_url"]
