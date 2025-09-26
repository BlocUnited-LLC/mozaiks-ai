# ==============================================================================
# FILE: core/workflow/context_variables.py
# DESCRIPTION: Context variable loading for the Mozaiks runtime (agent-centric schema)
# ==============================================================================

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .context_adapter import create_context_container
from .context_schema import (
    ContextVariablesPlan,
    ContextVariableDefinition,
    load_context_variables_config,
)
from .workflow_manager import workflow_manager
from logs.logging_config import get_workflow_logger

business_logger = get_workflow_logger("context_variables")

_TRUE_FLAG_VALUES = {"1", "true", "yes", "on"}
TRUNCATE_CHARS = int(os.getenv("CONTEXT_SCHEMA_TRUNCATE_CHARS", "4000") or 4000)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _context_to_dict(container: Any) -> Dict[str, Any]:
    try:
        if hasattr(container, "to_dict"):
            return dict(container.to_dict())  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        pass
    data = getattr(container, "data", None)
    if isinstance(data, dict):
        return dict(data)
    if isinstance(container, dict):
        return dict(container)
    return {}


def _coerce_value(definition: Optional[ContextVariableDefinition], raw_value: Any) -> Any:
    if definition is None:
        return raw_value
    if raw_value is None:
        return None
    dtype = (definition.type or "").lower()
    if dtype in {"boolean", "bool"}:
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in _TRUE_FLAG_VALUES
        return bool(raw_value)
    if dtype in {"integer", "int"}:
        try:
            return int(raw_value)
        except Exception:
            return raw_value
    return raw_value


def _resolve_environment(definition: ContextVariableDefinition) -> Any:
    source = definition.source
    env_var = source.env_var
    if not env_var:
        return _coerce_value(definition, source.default)
    env_value = os.getenv(env_var)
    if env_value is None:
        return _coerce_value(definition, source.default)
    return _coerce_value(definition, env_value)


def _resolve_static(definition: ContextVariableDefinition) -> Any:
    return _coerce_value(definition, definition.source.value)


def _resolve_derived_default(definition: ContextVariableDefinition) -> Any:
    return _coerce_value(definition, definition.source.default)


def _create_minimal_context(workflow_name: str, enterprise_id: Optional[str]):
    context = create_context_container()
    if enterprise_id:
        context.set("enterprise_id", enterprise_id)
    if workflow_name:
        context.set("workflow_name", workflow_name)
    business_logger.info(
        "Created minimal context",
        extra={
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "environment": os.getenv("ENVIRONMENT", "unknown"),
        },
    )
    return context


def _database_defaults(raw_section: Dict[str, Any]) -> Optional[str]:
    defaults = None
    if isinstance(raw_section, dict):
        candidate = raw_section.get("database_defaults")
        if isinstance(candidate, dict):
            defaults = candidate.get("database_name")
        defaults = defaults or raw_section.get("default_database_name")
        defaults = defaults or raw_section.get("default_database")
    return defaults


# ---------------------------------------------------------------------------
# Database loading
# ---------------------------------------------------------------------------

async def _load_database_variables(
    items: List[Tuple[str, ContextVariableDefinition]],
    default_database_name: Optional[str],
    enterprise_id: str,
) -> Dict[str, Any]:
    loaded: Dict[str, Any] = {}
    if not items:
        return loaded

    try:
        from core.core_config import get_mongo_client
        from bson import ObjectId
    except Exception as import_err:  # pragma: no cover
        business_logger.error(f"Database load unavailable: {import_err}")
        return loaded

    client = get_mongo_client()

    for name, definition in items:
        source = definition.source
        db_name = source.database_name or default_database_name
        collection = source.collection
        if not db_name or not collection:
            business_logger.warning(
                f"Skipping database variable '{name}' (database_name={db_name}, collection={collection})"
            )
            continue

        search_by = source.search_by or "enterprise_id"
        field = source.field

        try:
            db = client[db_name]
            business_logger.info(f"Loading {name} from database", extra={"database": db_name, "collection": collection})
            if search_by == "enterprise_id":
                try:
                    query = {search_by: ObjectId(enterprise_id)}
                except Exception:
                    query = {search_by: enterprise_id}
            else:
                query = {search_by: enterprise_id}

            document = await db[collection].find_one(query)
            if not document:
                business_logger.info(f"No document found for {name}")
                continue

            if field:
                loaded[name] = document.get(field)
            else:
                loaded[name] = document
        except Exception as load_err:
            business_logger.error(f"Failed loading database variable '{name}': {load_err}")

    return loaded


# ---------------------------------------------------------------------------
# Workflow config loading
# ---------------------------------------------------------------------------

def _load_workflow_plan(workflow_name: str) -> Tuple[ContextVariablesPlan, Dict[str, Any]]:
    raw_section: Dict[str, Any] = {}
    try:
        workflow_config = workflow_manager.get_config(workflow_name) or {}
        context_section = workflow_config.get("context_variables") or {}
        if isinstance(context_section, dict):
            raw_section = context_section
        if not raw_section:
            from pathlib import Path
            import json

            wf_info = getattr(workflow_manager, "_workflows", {}).get(workflow_name.lower())
            if wf_info and hasattr(wf_info, "path"):
                ext_file = Path(wf_info.path) / "context_variables.json"
                if ext_file.exists():
                    raw = ext_file.read_text(encoding="utf-8-sig")
                    data = json.loads(raw)
                    ctx_section = data.get("context_variables") or data
                    if isinstance(ctx_section, dict):
                        raw_section = ctx_section
    except Exception as err:  # pragma: no cover
        business_logger.warning(f"Unable to load context config for {workflow_name}: {err}")

    try:
        plan = load_context_variables_config(raw_section)
    except ValueError as err:
        business_logger.warning(
            f"Context variables validation failed for {workflow_name}: {err}"
        )
        plan = ContextVariablesPlan()
        raw_section = {}
    return plan, raw_section


# ---------------------------------------------------------------------------
# Schema utilities (optional, reused from legacy implementation)
# ---------------------------------------------------------------------------

async def _get_all_collections_first_docs(database_name: str) -> Dict[str, Any]:
    from core.core_config import get_mongo_client  # local import

    result: Dict[str, Any] = {}
    try:
        client = get_mongo_client()
        db = client[database_name]
        try:
            names = await db.list_collection_names()
        except Exception as err:  # pragma: no cover
            business_logger.error(f"list_collection_names failed for {database_name}: {err}")
            return result
        for cname in names:
            try:
                doc = await db[cname].find_one()
                if not doc:
                    result[cname] = {"_note": "empty_collection"}
                else:
                    cleaned = {k: v for k, v in doc.items() if k != "_id"}
                    result[cname] = cleaned
            except Exception as ce:
                result[cname] = {"_error": str(ce)}
    except Exception as outer:
        business_logger.error(f"Failed collecting first docs for {database_name}: {outer}")
    return result


async def _get_database_schema_async(database_name: str) -> Dict[str, Any]:
    schema_info: Dict[str, Any] = {}

    try:
        from core.core_config import get_mongo_client

        client = get_mongo_client()
        db = client[database_name]
        collection_names = await db.list_collection_names()

        schema_lines: List[str] = []
        schema_lines.append(f"DATABASE: {database_name}")
        schema_lines.append(f"TOTAL COLLECTIONS: {len(collection_names)}")
        schema_lines.append("")

        enterprise_collections: List[str] = []
        collection_schemas: Dict[str, Dict[str, str]] = {}

        for collection_name in collection_names:
            try:
                collection = db[collection_name]
                sample_doc = await collection.find_one()
                if not sample_doc:
                    collection_schemas[collection_name] = {"note": "No sample data available"}
                    continue

                field_types: Dict[str, str] = {}
                for field_name, value in sample_doc.items():
                    if field_name == "_id":
                        continue
                    field_type = type(value).__name__
                    if field_type == "ObjectId":
                        field_type = "ObjectId"
                    field_types[field_name] = field_type
                collection_schemas[collection_name] = field_types

                if "enterprise_id" in sample_doc:
                    enterprise_collections.append(collection_name)
            except Exception as err:
                business_logger.debug(f"Could not analyze {collection_name}: {err}")
                collection_schemas[collection_name] = {"error": f"Analysis failed: {err}"}

        for collection_name, fields in collection_schemas.items():
            note = fields.get("note") if isinstance(fields, dict) else None
            error = fields.get("error") if isinstance(fields, dict) else None
            if note or error:
                continue
            is_enterprise = " [Enterprise-specific]" if collection_name in enterprise_collections else ""
            schema_lines.append(f"{collection_name.upper()}{is_enterprise}:")
            schema_lines.append("  Fields:")
            for field_name, field_type in fields.items():
                schema_lines.append(f"    - {field_name}: {field_type}")
            schema_lines.append("")

        schema_info["schema_overview"] = "\n".join(schema_lines)
        business_logger.info(
            "Schema loaded",
            extra={
                "database": database_name,
                "collections": len(collection_names),
                "enterprise_collections": len(enterprise_collections),
            },
        )
    except Exception as err:
        business_logger.error(f"Database schema loading failed: {err}")
        schema_info["error"] = f"Could not load schema: {err}"

    return schema_info


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

async def _load_context_async(workflow_name: str, enterprise_id: Optional[str]):
    business_logger.info(f"Loading context for workflow={workflow_name}")
    context = _create_minimal_context(workflow_name, enterprise_id)
    internal_enterprise_id = enterprise_id or ""

    plan, raw_context_section = _load_workflow_plan(workflow_name)

    # Optional schema overview (gated by env)
    if isinstance(raw_context_section, dict):
        try:
            include_schema = os.getenv("CONTEXT_INCLUDE_SCHEMA", "false").lower() in _TRUE_FLAG_VALUES
            if include_schema:
                db_name = os.getenv("CONTEXT_SCHEMA_DB")
                if not db_name:
                    schema_cfg = raw_context_section.get("schema_overview")
                    if isinstance(schema_cfg, dict):
                        db_name = schema_cfg.get("database_name")
                if db_name:
                    overview_info = await _get_database_schema_async(db_name)
                    overview_text = overview_info.get("schema_overview")
                    if overview_text:
                        if len(overview_text) > TRUNCATE_CHARS:
                            overview_text = f"{overview_text[:TRUNCATE_CHARS]}... [truncated {len(overview_text) - TRUNCATE_CHARS} chars]"
                        context.set("schema_overview", overview_text)
                    try:
                        first_docs = await _get_all_collections_first_docs(db_name)
                        context.set("collections_first_docs_full", first_docs)
                    except Exception as doc_err:
                        business_logger.debug(f"collections_first_docs_full attachment failed: {doc_err}")
        except Exception as schema_err:  # pragma: no cover
            business_logger.debug(f"Schema overview skipped: {schema_err}")

    definitions = plan.definitions or {}

    database_items: List[Tuple[str, ContextVariableDefinition]] = []
    for name, definition in definitions.items():
        source = definition.source
        if source.type == "environment":
            value = _resolve_environment(definition)
            context.set(name, value)
            business_logger.info(f"Loaded environment variable {name}", extra={"value": value})
        elif source.type == "static":
            value = _resolve_static(definition)
            context.set(name, value)
            business_logger.info(f"Loaded static variable {name}")
        elif source.type == "derived":
            value = _resolve_derived_default(definition)
            context.set(name, value)
            business_logger.info(f"Seeded derived variable {name} with default={value}")
        elif source.type == "database":
            database_items.append((name, definition))
        else:
            business_logger.debug(f"Unsupported source type for {name}: {source.type}")

    if database_items and internal_enterprise_id:
        default_db = _database_defaults(raw_context_section)
        db_values = await _load_database_variables(database_items, default_db, internal_enterprise_id)
        for name, value in db_values.items():
            coerced = _coerce_value(definitions.get(name), value) if definitions.get(name) else value
            context.set(name, coerced)

    # Expose definitions and agent plan on the context container for downstream consumers
    if definitions:
        setattr(context, "_mozaiks_context_definitions", definitions)
    if plan.agents:
        setattr(context, "_mozaiks_context_agents", plan.agents)
        exposures_map: Dict[str, List[Dict[str, Any]]] = {}
        for agent_name, agent_view in plan.agents.items():
            exposures = [exp.model_dump(exclude_none=True) for exp in agent_view.exposures]
            if exposures:
                exposures_map[agent_name] = exposures
        if exposures_map:
            setattr(context, "_mozaiks_context_exposures", exposures_map)

    # Log context summary
    try:
        keys = [k for k in context.keys() if k != "enterprise_id"]  # type: ignore[attr-defined]
    except Exception:
        keys = list(_context_to_dict(context).keys())
    business_logger.info(
        "Context loaded",
        extra={
            "workflow": workflow_name,
            "variable_count": len(keys),
            "variables": keys,
        },
    )
    for key in keys:
        try:
            business_logger.debug(f"    {key} => {context.get(key)}")
        except Exception:
            pass

    if internal_enterprise_id and not (hasattr(context, "contains") and context.contains("enterprise_id")):
        context.set("enterprise_id", internal_enterprise_id)

    return context


__all__ = ["_create_minimal_context", "_load_context_async"]


