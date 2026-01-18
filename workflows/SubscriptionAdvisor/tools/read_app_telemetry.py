"""
read_app_telemetry - Read app-level telemetry for SubscriptionAdvisor.

Collects:
- Workflow list and dependencies
- Tool usage patterns
- Token consumption per workflow
- Plugin access patterns

CONSTRAINTS (enforced):
- read_only = true
- no_external_mutations = true
- tenant_scoped = true (app-scoped)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict

_logger = logging.getLogger("tools.SubscriptionAdvisor.read_app_telemetry")

# ============================================================================
# CONSTRAINT ENFORCEMENT
# ============================================================================

TOOL_CONSTRAINTS = {
    "read_only": True,
    "no_external_mutations": True,
    "tenant_scoped": True,
    "allowed_collections": [
        "workflows",
        "tool_invocations",
        "token_usage",
        "plugin_usage",
        "apps",
    ],
    "forbidden_operations": [
        "insert",
        "update",
        "delete",
        "replace",
        "bulk_write",
        "create_index",
        "drop",
    ],
    "forbidden_apis": [
        "stripe",
        "payment",
        "billing",
        "subscription.update",
        "subscription.create",
        "subscription.delete",
    ],
}


class WorkflowInfo(TypedDict, total=False):
    """Information about a single workflow."""
    workflow_id: str
    name: str
    description: str
    avg_tokens_per_run: int
    invocation_count_30d: int
    avg_duration_ms: float
    tools_used: List[str]
    dependencies: List[str]  # Other workflows this depends on
    cost_tier: str  # "low", "medium", "high" based on tool complexity


class ToolUsage(TypedDict, total=False):
    """Tool usage statistics."""
    tool_name: str
    invocation_count: int
    avg_latency_ms: float
    has_external_api: bool
    estimated_cost_per_call: float  # Relative cost indicator


class PluginUsage(TypedDict, total=False):
    """Plugin access patterns."""
    plugin_id: str
    plugin_name: str
    invocation_count: int
    has_external_cost: bool
    access_tier: str  # Which tier typically uses this


class AppTelemetry(TypedDict, total=False):
    """Schema for app telemetry returned by this tool."""
    app_id: str
    app_name: str
    app_description: str
    target_market: str
    
    # Workflow analysis
    workflow_list: List[WorkflowInfo]
    workflow_count: int
    total_workflow_invocations_30d: int
    
    # Tool analysis
    tool_usage: List[ToolUsage]
    unique_tools_count: int
    external_api_tools_count: int
    
    # Token analysis
    total_tokens_30d: int
    avg_tokens_per_session: float
    token_by_workflow: Dict[str, int]
    
    # Plugin analysis
    plugin_usage: List[PluginUsage]
    plugins_with_external_cost: List[str]
    
    # Metadata
    collection_timestamp: str
    date_range_start: str
    date_range_end: str


def _cache_context_value(context_variables: Any, key: str, value: Any) -> None:
    """Cache a value in context variables for downstream agents."""
    if not context_variables:
        return
    try:
        setter = getattr(context_variables, "set", None)
        if callable(setter):
            setter(key, value)
            return
    except Exception as exc:
        _logger.debug("Unable to cache %s via context_variables.set: %s", key, exc)

    try:
        data = getattr(context_variables, "data", None)
        if isinstance(data, dict):
            data[key] = value
    except Exception as exc:
        _logger.debug("Unable to cache %s via context_variables.data: %s", key, exc)


async def _read_app_metadata(db: Any, app_id: str) -> Dict[str, Any]:
    """Read app metadata (read-only)."""
    metadata = {
        "app_name": "Unknown App",
        "app_description": "",
        "target_market": "general",
    }
    
    if db is None:
        return metadata
    
    try:
        app = await db.apps.find_one(
            {"_id": app_id},
            {"name": 1, "description": 1, "target_market": 1, "category": 1},
        )
        if app:
            metadata["app_name"] = app.get("name", "Unknown App")
            metadata["app_description"] = app.get("description", "")
            metadata["target_market"] = app.get("target_market") or app.get("category", "general")
    except Exception as exc:
        _logger.error("Error reading app metadata: %s", exc)
    
    return metadata


async def _read_workflow_list(
    db: Any,
    app_id: str,
    start_date: datetime,
    end_date: datetime,
) -> List[WorkflowInfo]:
    """Read workflow definitions and usage stats (read-only)."""
    workflows: List[WorkflowInfo] = []
    
    if db is None:
        return workflows
    
    try:
        # Read-only: fetch workflow definitions
        workflow_cursor = db.workflows.find(
            {"app_id": app_id},
            {
                "_id": 1,
                "name": 1,
                "description": 1,
                "tools": 1,
                "dependencies": 1,
            },
        )
        
        workflow_defs = await workflow_cursor.to_list(100)
        
        for wf in workflow_defs:
            wf_id = str(wf["_id"])
            
            # Read-only: get invocation stats
            pipeline = [
                {
                    "$match": {
                        "app_id": app_id,
                        "workflow_id": wf_id,
                        "timestamp": {"$gte": start_date, "$lte": end_date},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "count": {"$sum": 1},
                        "avg_tokens": {"$avg": "$tokens_used"},
                        "avg_duration": {"$avg": "$duration_ms"},
                    }
                },
            ]
            
            stats = await db.workflow_executions.aggregate(pipeline).to_list(1)
            stats = stats[0] if stats else {}
            
            # Determine cost tier based on tools
            tools = wf.get("tools", [])
            external_tools = [t for t in tools if _is_external_api_tool(t)]
            cost_tier = "high" if len(external_tools) > 2 else "medium" if external_tools else "low"
            
            workflows.append(WorkflowInfo(
                workflow_id=wf_id,
                name=wf.get("name", "Unnamed"),
                description=wf.get("description", ""),
                avg_tokens_per_run=int(stats.get("avg_tokens", 0)),
                invocation_count_30d=stats.get("count", 0),
                avg_duration_ms=stats.get("avg_duration", 0.0),
                tools_used=tools,
                dependencies=wf.get("dependencies", []),
                cost_tier=cost_tier,
            ))
        
    except Exception as exc:
        _logger.error("Error reading workflow list: %s", exc)
    
    return workflows


def _is_external_api_tool(tool_name: str) -> bool:
    """Check if a tool makes external API calls (heuristic)."""
    external_indicators = [
        "api", "fetch", "http", "webhook", "external",
        "send_email", "sms", "slack", "discord",
        "openai", "anthropic", "google",
    ]
    tool_lower = tool_name.lower()
    return any(ind in tool_lower for ind in external_indicators)


async def _read_tool_usage(
    db: Any,
    app_id: str,
    start_date: datetime,
    end_date: datetime,
) -> List[ToolUsage]:
    """Read tool usage patterns (read-only)."""
    tool_usage: List[ToolUsage] = []
    
    if db is None:
        return tool_usage
    
    try:
        # Read-only: aggregate tool invocations
        pipeline = [
            {
                "$match": {
                    "app_id": app_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": "$tool_name",
                    "count": {"$sum": 1},
                    "avg_latency": {"$avg": "$latency_ms"},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 50},
        ]
        
        results = await db.tool_invocations.aggregate(pipeline).to_list(50)
        
        for r in results:
            tool_name = r["_id"]
            has_external = _is_external_api_tool(tool_name)
            
            # Relative cost estimate based on characteristics
            cost = 0.1 if has_external else 0.01
            if "openai" in tool_name.lower() or "anthropic" in tool_name.lower():
                cost = 0.5
            
            tool_usage.append(ToolUsage(
                tool_name=tool_name,
                invocation_count=r["count"],
                avg_latency_ms=r.get("avg_latency", 0.0),
                has_external_api=has_external,
                estimated_cost_per_call=cost,
            ))
        
    except Exception as exc:
        _logger.error("Error reading tool usage: %s", exc)
    
    return tool_usage


async def _read_token_consumption(
    db: Any,
    app_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, Any]:
    """Read token consumption by workflow (read-only)."""
    token_data = {
        "total_tokens_30d": 0,
        "avg_tokens_per_session": 0.0,
        "token_by_workflow": {},
    }
    
    if db is None:
        return token_data
    
    try:
        # Read-only: total tokens
        pipeline_total = [
            {
                "$match": {
                    "app_id": app_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": "$tokens_used"},
                    "sessions": {"$sum": 1},
                }
            },
        ]
        
        result = await db.token_usage.aggregate(pipeline_total).to_list(1)
        if result:
            token_data["total_tokens_30d"] = result[0].get("total", 0)
            sessions = result[0].get("sessions", 1) or 1
            token_data["avg_tokens_per_session"] = token_data["total_tokens_30d"] / sessions
        
        # Read-only: tokens by workflow
        pipeline_by_wf = [
            {
                "$match": {
                    "app_id": app_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": "$workflow_id",
                    "tokens": {"$sum": "$tokens_used"},
                }
            },
        ]
        
        wf_results = await db.token_usage.aggregate(pipeline_by_wf).to_list(100)
        token_data["token_by_workflow"] = {
            r["_id"]: r["tokens"] for r in wf_results if r["_id"]
        }
        
    except Exception as exc:
        _logger.error("Error reading token consumption: %s", exc)
    
    return token_data


async def _read_plugin_usage(
    db: Any,
    app_id: str,
    start_date: datetime,
    end_date: datetime,
) -> List[PluginUsage]:
    """Read plugin access patterns (read-only)."""
    plugins: List[PluginUsage] = []
    
    if db is None:
        return plugins
    
    try:
        # Read-only: aggregate plugin usage
        pipeline = [
            {
                "$match": {
                    "app_id": app_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": "$plugin_id",
                    "plugin_name": {"$first": "$plugin_name"},
                    "count": {"$sum": 1},
                    "has_cost": {"$max": "$has_external_cost"},
                }
            },
            {"$sort": {"count": -1}},
        ]
        
        results = await db.plugin_usage.aggregate(pipeline).to_list(50)
        
        for r in results:
            # Determine typical access tier based on cost
            has_cost = r.get("has_cost", False)
            access_tier = "pro" if has_cost else "free"
            
            plugins.append(PluginUsage(
                plugin_id=r["_id"],
                plugin_name=r.get("plugin_name", r["_id"]),
                invocation_count=r["count"],
                has_external_cost=has_cost,
                access_tier=access_tier,
            ))
        
    except Exception as exc:
        _logger.error("Error reading plugin usage: %s", exc)
    
    return plugins


def read_app_telemetry(
    *,
    app_id: Annotated[str, "App ID to collect telemetry for"],
    include_workflows: Annotated[bool, "Include detailed workflow analysis"] = True,
    context_variables: Annotated[
        Optional[Any],
        "Context variables provided by AG2 runtime"
    ] = None,
) -> str:
    """
    Read app-level telemetry for SubscriptionAdvisor.
    
    This tool is READ-ONLY and APP-SCOPED. It:
    - Collects workflow definitions and usage patterns
    - Collects tool invocation statistics
    - Collects token consumption by workflow
    - Collects plugin access patterns
    
    It NEVER:
    - Writes to any collection
    - Calls Stripe or payment APIs
    - Accesses other apps' data
    """
    import asyncio
    
    async def _collect() -> AppTelemetry:
        # Get database connection from runtime context
        db = None
        if context_variables:
            db = getattr(context_variables, "db", None)
            if db is None:
                data = getattr(context_variables, "data", {})
                db = data.get("db") if isinstance(data, dict) else None
        
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=30)
        end_date = now
        
        _logger.info("Collecting app telemetry for app=%s", app_id)
        
        # Collect all telemetry in parallel (all read-only)
        metadata, workflows, tools, tokens, plugins = await asyncio.gather(
            _read_app_metadata(db, app_id),
            _read_workflow_list(db, app_id, start_date, end_date) if include_workflows else [],
            _read_tool_usage(db, app_id, start_date, end_date),
            _read_token_consumption(db, app_id, start_date, end_date),
            _read_plugin_usage(db, app_id, start_date, end_date),
        )
        
        # Identify plugins with external cost
        plugins_with_cost = [p["plugin_id"] for p in plugins if p.get("has_external_cost")]
        
        telemetry: AppTelemetry = {
            "app_id": app_id,
            "app_name": metadata["app_name"],
            "app_description": metadata["app_description"],
            "target_market": metadata["target_market"],
            "workflow_list": workflows,
            "workflow_count": len(workflows),
            "total_workflow_invocations_30d": sum(
                w.get("invocation_count_30d", 0) for w in workflows
            ),
            "tool_usage": tools,
            "unique_tools_count": len(tools),
            "external_api_tools_count": sum(1 for t in tools if t.get("has_external_api")),
            "total_tokens_30d": tokens["total_tokens_30d"],
            "avg_tokens_per_session": tokens["avg_tokens_per_session"],
            "token_by_workflow": tokens["token_by_workflow"],
            "plugin_usage": plugins,
            "plugins_with_external_cost": plugins_with_cost,
            "collection_timestamp": now.isoformat(),
            "date_range_start": start_date.isoformat(),
            "date_range_end": end_date.isoformat(),
        }
        
        return telemetry
    
    # Run async collection
    try:
        loop = asyncio.get_running_loop()
        telemetry = loop.run_until_complete(_collect())
    except RuntimeError:
        telemetry = asyncio.run(_collect())
    
    # Cache telemetry for downstream agents
    _cache_context_value(context_variables, "collected_kpis", telemetry)
    _cache_context_value(context_variables, "app_metadata", {
        "app_name": telemetry["app_name"],
        "app_description": telemetry["app_description"],
        "target_market": telemetry["target_market"],
    })
    
    _logger.info(
        "App telemetry collected: app=%s, workflows=%d, tokens_30d=%d",
        app_id,
        telemetry["workflow_count"],
        telemetry["total_tokens_30d"],
    )
    
    return (
        f"App telemetry collected for {telemetry['app_name']} ({app_id}):\n"
        f"- Workflows: {telemetry['workflow_count']}\n"
        f"- Total workflow invocations (30d): {telemetry['total_workflow_invocations_30d']:,}\n"
        f"- Unique tools: {telemetry['unique_tools_count']}\n"
        f"- External API tools: {telemetry['external_api_tools_count']}\n"
        f"- Total tokens (30d): {telemetry['total_tokens_30d']:,}\n"
        f"- Avg tokens/session: {telemetry['avg_tokens_per_session']:.0f}\n"
        f"- Plugins used: {len(telemetry['plugin_usage'])}\n"
        f"- Plugins with external cost: {len(telemetry['plugins_with_external_cost'])}\n"
        f"\nTelemetry cached in context_variables.collected_kpis"
    )
