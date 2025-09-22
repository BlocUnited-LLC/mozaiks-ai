"""Typed schema for declarative context variable specifications.

This module normalizes workflow JSON into Pydantic models so the runtime can
reason about environment, database, declarative (static), and derived context
variables in a consistent way.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, model_validator


class EnvironmentSource(BaseModel):
    """Environment variable lookup definition."""

    type: Literal["environment"] = "environment"
    env_var: str = Field(..., description="Environment variable to read")
    default: Optional[Any] = Field(None, description="Fallback when env var missing")


class DatabaseSource(BaseModel):
    """Database lookup definition."""

    type: Literal["database"] = "database"
    database_name: Optional[str] = Field(
        None, description="Optional override when variable differs from workflow default"
    )
    collection: str
    search_by: str = Field("enterprise_id", description="Field used to scope the query")
    field: Optional[str] = Field(None, description="Field to project from the matched document")


class StaticSource(BaseModel):
    """Declarative/static value definition."""

    type: Literal["static"] = "static"
    value: Any

    @model_validator(mode="before")
    def _alias_declarative(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("type") == "declarative":
            data = data.copy()
            data["type"] = "static"
        return data


SourceConfig = Union[EnvironmentSource, DatabaseSource, StaticSource]


class BaseVariableSpec(BaseModel):
    name: str
    description: Optional[str] = None
    type: Optional[str] = None


class EnvironmentVariableSpec(BaseVariableSpec):
    source: EnvironmentSource

    @model_validator(mode="before")
    def _inject_source(cls, data: Any) -> Any:
        if isinstance(data, dict) and "source" not in data:
            env_key = data.get("env_var")
            if env_key:
                data = data.copy()
                data["source"] = {"type": "environment", "env_var": env_key, "default": data.get("default")}
        return data


class DatabaseVariableSpec(BaseVariableSpec):
    source: DatabaseSource

    @model_validator(mode="before")
    def _inject_source(cls, data: Any) -> Any:
        if isinstance(data, dict) and "source" not in data:
            db_cfg = data.get("database")
            if isinstance(db_cfg, dict):
                new = db_cfg.copy()
                new.setdefault("type", "database")
                data = data.copy()
                data["source"] = new
        return data


class DeclarativeVariableSpec(BaseVariableSpec):
    source: StaticSource

    @model_validator(mode="before")
    def _inject_source(cls, data: Any) -> Any:
        if isinstance(data, dict) and "source" not in data:
            if "value" in data:
                data = data.copy()
                data["source"] = {"type": "static", "value": data["value"]}
        return data


class AgentTextTriggerMatch(BaseModel):
    equals: str


class AgentTextTriggerSpec(BaseModel):
    type: Literal["agent_text"]
    agent: str
    match: AgentTextTriggerMatch

    @model_validator(mode="before")
    def _support_flat_equals(cls, data: Any) -> Any:
        if isinstance(data, dict) and "match" not in data:
            equals_val = data.get("equals")
            if equals_val is not None:
                data = data.copy()
                data["match"] = {"equals": equals_val}
        return data


class DerivedVariableSpec(BaseModel):
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    default: Any = False
    triggers: List[AgentTextTriggerSpec] = Field(default_factory=list)


class ContextVariablesConfig(BaseModel):
    database_variables: List[DatabaseVariableSpec] = Field(default_factory=list)
    environment_variables: List[EnvironmentVariableSpec] = Field(default_factory=list)
    declarative_variables: List[DeclarativeVariableSpec] = Field(default_factory=list)
    derived_variables: List[DerivedVariableSpec] = Field(default_factory=list)

    @model_validator(mode="before")
    def _unwrap_nested(cls, data: Any) -> Any:
        if isinstance(data, dict):
            candidate = data
            if "context_variables" in candidate and isinstance(candidate["context_variables"], dict):
                candidate = candidate["context_variables"]
            # Some legacy configs stored values under 'variables'
            if "variables" in candidate and isinstance(candidate["variables"], dict):
                merged = candidate["variables"].copy()
                merged.setdefault("database_variables", candidate.get("database_variables", []))
                merged.setdefault("environment_variables", candidate.get("environment_variables", []))
                merged.setdefault("declarative_variables", candidate.get("declarative_variables", []))
                merged.setdefault("derived_variables", candidate.get("derived_variables", []))
                candidate = merged
            return candidate
        return data

    def model_dump_runtime(self) -> Dict[str, Any]:
        """Return a dict aligned with runtime expectations."""

        return self.model_dump(exclude_none=True)


def load_context_variables_config(raw: Dict[str, Any]) -> ContextVariablesConfig:
    """Parse raw workflow JSON into a ContextVariablesConfig model."""

    try:
        return ContextVariablesConfig.model_validate(raw)
    except ValidationError as err:
        raise ValueError(f"Invalid context variables configuration: {err}") from err
