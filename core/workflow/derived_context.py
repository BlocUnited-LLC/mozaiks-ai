# ==============================================================================
# FILE: core\workflow\derived_context.py
# DESCRIPTION: Derived context variable management
# PURPOSE: Allows workflows to declare context variables derived from runtime events

#This module allows workflows to declare context variables that are derived from
#runtime events (e.g., agent messages) using declarative JSON configuration.

#Definition lives under `context_variables.json`:

#{
#  "context_variables": {
#    "derived": [
#      {
#        "name": "interview_complete",
#        "default": false,
#        "triggers": [
#          {
#            "type": "agent_text",
#            "agent": "InterviewAgent",
#            "match": {"equals": "TERMINATE"}
#          }
#        ]
#      }
#    ]
#  }
#}
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from autogen.events.agent_events import TextEvent

from logs.logging_config import get_workflow_logger
from .workflow_manager import workflow_manager


logger = get_workflow_logger("derived_context")


def _extract_sender_name(event: TextEvent) -> Optional[str]:
    """Best-effort extraction of the logical sender name from a TextEvent."""

    sender_obj = getattr(event, "sender", None)
    name = getattr(sender_obj, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()

    raw_content = getattr(event, "content", None)

    def _convert(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            try:
                return obj.model_dump()
            except Exception:  # pragma: no cover
                return obj
        if hasattr(obj, "dict"):
            try:
                return obj.dict()
            except Exception:  # pragma: no cover
                return obj
        return obj

    raw_content = _convert(raw_content)
    if isinstance(raw_content, dict):
        for key in ("sender", "agent", "agent_name", "name"):
            value = raw_content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_text_content(event: TextEvent) -> str:
    """Return best effort string representation of a TextEvent's content."""

    raw_content = getattr(event, "content", None)

    def _dig(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if hasattr(value, "model_dump"):
            try:
                return _dig(value.model_dump())
            except Exception:  # pragma: no cover
                return None
        if hasattr(value, "dict"):
            try:
                return _dig(value.dict())
            except Exception:  # pragma: no cover
                return None
        if isinstance(value, dict):
            # Prefer standard content keys first
            for preferred in ("content", "message", "text", "value"):
                if preferred in value:
                    found = _dig(value[preferred])
                    if found:
                        return found
            for item in value.values():
                found = _dig(item)
                if found:
                    return found
        if isinstance(value, (list, tuple)):
            for item in value:
                found = _dig(item)
                if found:
                    return found
        return None

    text = _dig(raw_content)
    if text is None:
        return ""
    return text

@dataclass
class AgentTextTrigger:
    agent: str
    equals: str

    def matches(self, event: TextEvent) -> bool:
        sender = _extract_sender_name(event)
        if not sender or sender != self.agent:
            return False

        text = _extract_text_content(event)
        return text == self.equals


TRIGGER_LOADERS = {
    "agent_text": AgentTextTrigger,
}


@dataclass
class DerivedVariableSpec:
    name: str
    default: Any
    triggers: List[AgentTextTrigger]

    def seed(self, providers: Iterable[Any]) -> None:
        for provider in providers:
            if hasattr(provider, "contains") and provider.contains(self.name):
                continue
            if hasattr(provider, "get"):
                existing = provider.get(self.name, None)
                if existing is not None:
                    continue
            if hasattr(provider, "set"):
                try:
                    provider.set(self.name, self.default)
                except Exception as err:  # pragma: no cover
                    logger.debug(f"Derived variable seed failed: {err}")

    def apply(self, event: TextEvent, providers: Iterable[Any]) -> bool:
        for trigger in self.triggers:
            if trigger.matches(event):
                for provider in providers:
                    if hasattr(provider, "set"):
                        try:
                            provider.set(self.name, True)
                        except Exception as err:  # pragma: no cover
                            logger.debug(f"Derived variable update failed: {err}")
                return True
        return False


class DerivedContextManager:
    """Runtime helper that enforces declarative derived context variables."""

    def __init__(
        self,
        workflow_name: str,
        agents: Dict[str, Any],
        base_context: Any,
    ) -> None:
        self.workflow_name = workflow_name
        self.agents = agents
        self.base_context = base_context
        self.providers: List[Any] = []
        if base_context is not None:
            self.providers.append(base_context)
        self.providers.extend(
            [getattr(agent, "context_variables", None) for agent in agents.values() if getattr(agent, "context_variables", None)]
        )

        config = workflow_manager.get_config(workflow_name) or {}
        ctx_cfg = (config.get("context_variables") or {}).get("context_variables") or {}
        raw_derived = (
            ctx_cfg.get("derived_variables")
            or ctx_cfg.get("derived")
            or []
        )
        self.variables: List[DerivedVariableSpec] = []
        for item in raw_derived:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            default = item.get("default")
            triggers = []
            for trig in item.get("triggers", []) or []:
                if not isinstance(trig, dict):
                    continue
                trig_type = trig.get("type")
                if not isinstance(trig_type, str):
                    continue
                loader = TRIGGER_LOADERS.get(trig_type)
                if not loader:
                    continue
                try:
                    match_cfg = trig.get("match", {}) if isinstance(trig.get("match"), dict) else {}
                    equals_value = match_cfg.get("equals") if match_cfg else trig.get("equals")
                    agent_name = trig.get("agent")
                    if not isinstance(agent_name, str) or not agent_name:
                        continue
                    if not isinstance(equals_value, str) or not equals_value:
                        continue
                    trigger_obj = loader(
                        agent=agent_name,
                        equals=equals_value,
                    )
                    if isinstance(trigger_obj.agent, str) and trigger_obj.agent:
                        triggers.append(trigger_obj)
                except TypeError as err:  # pragma: no cover
                    logger.debug(f"Failed to construct derived context trigger: {err}")
            if triggers:
                self.variables.append(DerivedVariableSpec(name=name, default=default, triggers=triggers))

    def has_variables(self) -> bool:
        return bool(self.variables)

    def register_additional_provider(self, provider: Any) -> None:
        if provider and provider not in self.providers:
            self.providers.append(provider)
            for var in self.variables:
                var.seed([provider])

    def seed_defaults(self) -> None:
        for var in self.variables:
            var.seed(self.providers)

    def handle_event(self, event: Any) -> None:
        if not self.variables:
            return
        if not isinstance(event, TextEvent):
            return
        for var in self.variables:
            if var.apply(event, self.providers):
                new_value = True
                logger.info(
                    f"[DERIVED_CONTEXT] {self.workflow_name}: {var.name} -> {new_value}"
                )
