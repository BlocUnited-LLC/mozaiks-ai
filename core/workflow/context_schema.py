"""Typed schema for agent-centric context variable specifications."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator


class ContextTriggerMatch(BaseModel):
    """Declarative trigger match conditions."""

    equals: Optional[str] = None
    contains: Optional[str] = None
    regex: Optional[str] = None


class ContextTriggerSpec(BaseModel):
    """Declarative trigger definition for derived variables."""

    type: Literal["agent_text"]
    agent: str
    match: ContextTriggerMatch

    @model_validator(mode="before")
    def _normalize_match(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        match_cfg = data.get("match")
        if not isinstance(match_cfg, dict):
            data = data.copy()
            data["match"] = {
                "equals": data.get("equals"),
                "contains": data.get("contains"),
                "regex": data.get("regex"),
            }
        return data


class ContextVariableSource(BaseModel):
    """Source metadata for resolving a context variable."""

    type: Literal["database", "environment", "static", "derived"]
    database_name: Optional[str] = None
    collection: Optional[str] = None
    search_by: Optional[str] = None
    field: Optional[str] = None
    env_var: Optional[str] = None
    default: Optional[Any] = None
    value: Optional[Any] = None
    triggers: List[ContextTriggerSpec] = Field(default_factory=list)

    @model_validator(mode="before")
    def _ensure_triggers(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("type") != "derived":
            data = data.copy()
            data.setdefault("triggers", [])
        return data


class ContextVariableDefinition(BaseModel):
    """Full definition for a context variable."""

    type: Optional[str] = None
    description: Optional[str] = None
    source: ContextVariableSource


class ContextExposureTemplate(BaseModel):
    """Exposure template for injecting context into system prompts."""

    variables: List[str]
    template: Optional[str] = None
    header: Optional[str] = None
    null_label: Optional[str] = None
    placement: Literal["append", "prepend", "replace"] = "append"

    @model_validator(mode="before")
    def _sanitize_variables(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_variables = data.get("variables")
            if isinstance(raw_variables, list):
                data = data.copy()
                data["variables"] = [
                    str(item).strip() for item in raw_variables if isinstance(item, str) and item.strip()
                ]
        return data


class ContextAgentView(BaseModel):
    """Per-agent context requirements and exposures."""

    variables: List[str] = Field(default_factory=list)
    exposures: List[ContextExposureTemplate] = Field(default_factory=list)

    @model_validator(mode="before")
    def _default_lists(cls, data: Any) -> Any:
        if isinstance(data, dict):
            updated = data.copy()
            if updated.get("variables") is None:
                updated["variables"] = []
            if updated.get("exposures") is None:
                updated["exposures"] = []
            return updated
        return data


class ContextVariablesPlan(BaseModel):
    """Canonical context plan consumed by the runtime."""

    definitions: Dict[str, ContextVariableDefinition] = Field(default_factory=dict)
    agents: Dict[str, ContextAgentView] = Field(default_factory=dict)


def load_context_variables_config(raw: Dict[str, Any]) -> ContextVariablesPlan:
    """Parse raw workflow JSON into a ContextVariablesPlan model."""

    candidate: Dict[str, Any] = {}
    if isinstance(raw, dict):
        candidate = raw.get("context_variables") if "context_variables" in raw else raw
        if not isinstance(candidate, dict):
            candidate = {}
    try:
        return ContextVariablesPlan.model_validate(candidate)
    except ValidationError as err:
        raise ValueError(f"Invalid context variables configuration: {err}") from err


__all__ = [
    "ContextVariablesPlan",
    "ContextVariableDefinition",
    "ContextVariableSource",
    "ContextExposureTemplate",
    "ContextAgentView",
    "ContextTriggerSpec",
    "ContextTriggerMatch",
    "load_context_variables_config",
]
