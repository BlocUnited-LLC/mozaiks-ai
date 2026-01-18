"""Ask Mozaiks companion service.

AppGenerator-specific implementation.

Provides a lightweight, non-AG2 LLM bridge that can answer user
questions while all workflows are paused in "general" mode. The service
wraps OpenAI-compatible chat completions so we can reuse the same model
configuration that powers AG2 workflows without spawning a new group
chat.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from logs.logging_config import get_workflow_logger
from mozaiksai.core.workflow.validation.llm_config import get_llm_config

logger = get_workflow_logger("ask_mozaiks")


class AskMozaiksService:
    """Thin HTTP client that proxies prompts to the configured LLM."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def aclose(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    async def generate_response(
        self,
        *,
        prompt: str,
        workflows: List[Dict[str, Any]],
        app_id: Optional[str],
        user_id: Optional[str],
        ui_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call the backing LLM with runtime-aware context."""
        provider = await self._select_provider()
        api_key = provider["api_key"]
        model = provider["model"]
        api_base = provider.get("api_base") or provider.get("base_url")
        api_base = (
            api_base
            or os.getenv("ASK_MOZAIKS_API_BASE")
            or "https://api.openai.com/v1"
        ).rstrip("/")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "temperature": 0.3,
            "messages": self._build_messages(
                prompt=prompt,
                workflows=workflows,
                app_id=app_id,
                user_id=user_id,
                ui_context=ui_context,
            ),
        }

        logger.info(
            "[ASK_MOZAIKS] Sending prompt",
            extra={
                "model": model,
                "app_id": app_id,
                "user_id": user_id,
                "workflow_count": len(workflows),
            },
        )

        response = await self._client.post(f"{api_base}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        content = (
            (data.get("choices", [{}])[0]
             .get("message", {})
             .get("content", ""))
            .strip()
        )

        usage = data.get("usage", {})
        logger.info(
            "[ASK_MOZAIKS] Response received",
            extra={
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "app_id": app_id,
            },
        )

        return {
            "content": content or "I'm here! Let me know what you need.",
            "usage": usage,
        }

    async def _select_provider(self) -> Dict[str, Any]:
        """Grab the first provider entry with a usable API key."""
        _, llm_config = await get_llm_config(stream=False, cache=True)
        config_list = llm_config.get("config_list", [])
        for entry in config_list:
            if entry.get("api_key") and entry.get("model"):
                return entry
        raise RuntimeError("No LLM provider available for Ask Mozaiks")

    def _build_messages(
        self,
        *,
        prompt: str,
        workflows: List[Dict[str, Any]],
        app_id: Optional[str],
        user_id: Optional[str],
        ui_context: Optional[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        workflow_lines = []
        for wf in workflows:
            workflow_lines.append(
                "- {name} | status={status} | chat_id={chat_id} | artifact={artifact}".format(
                    name=wf.get("workflow_name"),
                    status=wf.get("status"),
                    chat_id=wf.get("chat_id"),
                    artifact=wf.get("artifact_id") or wf.get("artifact_preview") or "n/a",
                )
            )
        workflow_summary = "\n".join(workflow_lines) if workflow_lines else "(no workflows currently running)"

        ui_lines = []
        if ui_context:
            for key, value in ui_context.items():
                ui_lines.append(f"- {key}: {value}")
        ui_summary = "\n".join(ui_lines) if ui_lines else "(no additional UI context provided)"

        system_prompt = (
            "You are Ask Mozaiks, the resident runtime companion."
            " Help users understand their progress across workflows, suggest next steps."
            "\n\nTenant context:"
            f"\n- app_id: {app_id or 'unknown'}"
            f"\n- user_id: {user_id or 'unknown'}"
            "\n\nWorkflow summary:\n" + workflow_summary
            + "\n\nUI context:\n" + ui_summary
            + "\n\nAlways keep answers concise, actionable, and reference specific workflows when helpful."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]


_service: Optional[AskMozaiksService] = None


def get_ask_mozaiks_service() -> AskMozaiksService:
    """Return module-level singleton."""
    global _service
    if _service is None:
        _service = AskMozaiksService()
    return _service
