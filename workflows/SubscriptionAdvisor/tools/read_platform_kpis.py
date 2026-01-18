"""
read_platform_kpis - Read platform-level KPIs for SubscriptionAdvisor.

Collects telemetry from:
- MozaiksPay token ledger
- Runtime event store
- Performance metrics
- App registry

CONSTRAINTS (enforced):
- read_only = true
- no_external_mutations = true
- tenant_scoped = true
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, Optional, TypedDict

_logger = logging.getLogger("tools.SubscriptionAdvisor.read_platform_kpis")

# ============================================================================
# CONSTRAINT ENFORCEMENT
# ============================================================================

# These are compile-time markers that the runtime and tests verify
TOOL_CONSTRAINTS = {
    "read_only": True,
    "no_external_mutations": True,
    "tenant_scoped": True,
    "allowed_collections": [
        "token_usage",
        "workflow_executions",
        "session_metrics",
        "artifacts",
        "apps",
        "notifications",
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


class PlatformKPIs(TypedDict, total=False):
    """Schema for platform KPIs returned by this tool."""
    
    # Token usage KPIs
    tokens_used_30d: int
    tokens_used_7d_trend: float  # Week-over-week growth rate
    peak_tokens_per_hour: int
    model_tier_distribution: Dict[str, float]  # e.g., {"gpt-4": 0.65, "gpt-3.5-turbo": 0.35}
    tier_allocation: int
    
    # Hosting & compute KPIs
    workflow_executions_30d: int
    workflow_executions_limit: int
    avg_workflow_duration_ms: float
    concurrent_sessions_peak: int
    concurrent_sessions_limit: int
    storage_artifacts_gb: float
    storage_limit_gb: float
    
    # Domain & email KPIs
    apps_published: int
    apps_with_custom_domain: int
    email_volume_30d: int
    brand_consistency_score: float  # 0.0-1.0 heuristic
    
    # Metadata
    current_tier: str
    collection_timestamp: str
    date_range_start: str
    date_range_end: str


def _get_date_range(
    date_range: Optional[Dict[str, str]]
) -> tuple[datetime, datetime]:
    """Calculate date range for KPI collection."""
    now = datetime.now(timezone.utc)
    end_date = now
    start_date = now - timedelta(days=30)
    
    if date_range:
        if date_range.get("start"):
            try:
                start_date = datetime.fromisoformat(date_range["start"]).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
        if date_range.get("end"):
            try:
                end_date = datetime.fromisoformat(date_range["end"]).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
    
    return start_date, end_date


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


async def _read_token_usage(
    db: Any,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, Any]:
    """Read token usage KPIs from MozaiksPay ledger (read-only)."""
    # NOTE: This is a read-only aggregation pipeline
    # The actual implementation would connect to MongoDB
    
    token_kpis = {
        "tokens_used_30d": 0,
        "tokens_used_7d_trend": 0.0,
        "peak_tokens_per_hour": 0,
        "model_tier_distribution": {},
        "tier_allocation": 100000,  # Default, would be read from user's tier
    }
    
    if db is None:
        _logger.warning("No database connection available, returning defaults")
        return token_kpis
    
    try:
        # Read-only aggregation for 30-day token usage
        pipeline_30d = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_tokens": {"$sum": "$tokens_used"},
                }
            },
        ]
        
        result = await db.token_usage.aggregate(pipeline_30d).to_list(1)
        if result:
            token_kpis["tokens_used_30d"] = result[0].get("total_tokens", 0)
        
        # Read-only aggregation for 7-day trend
        seven_days_ago = end_date - timedelta(days=7)
        fourteen_days_ago = end_date - timedelta(days=14)
        
        pipeline_current_week = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": seven_days_ago, "$lte": end_date},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$tokens_used"}}},
        ]
        
        pipeline_prev_week = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": fourteen_days_ago, "$lt": seven_days_ago},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$tokens_used"}}},
        ]
        
        current_week = await db.token_usage.aggregate(pipeline_current_week).to_list(1)
        prev_week = await db.token_usage.aggregate(pipeline_prev_week).to_list(1)
        
        current_total = current_week[0]["total"] if current_week else 0
        prev_total = prev_week[0]["total"] if prev_week else 1  # Avoid division by zero
        
        if prev_total > 0:
            token_kpis["tokens_used_7d_trend"] = (current_total - prev_total) / prev_total
        
        # Read-only aggregation for model distribution
        pipeline_models = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": "$model",
                    "tokens": {"$sum": "$tokens_used"},
                }
            },
        ]
        
        model_results = await db.token_usage.aggregate(pipeline_models).to_list(100)
        total_tokens = sum(r["tokens"] for r in model_results) or 1
        token_kpis["model_tier_distribution"] = {
            r["_id"]: r["tokens"] / total_tokens for r in model_results
        }
        
    except Exception as exc:
        _logger.error("Error reading token usage: %s", exc)
    
    return token_kpis


async def _read_hosting_metrics(
    db: Any,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, Any]:
    """Read hosting and compute KPIs (read-only)."""
    hosting_kpis = {
        "workflow_executions_30d": 0,
        "workflow_executions_limit": 1000,
        "avg_workflow_duration_ms": 0.0,
        "concurrent_sessions_peak": 0,
        "concurrent_sessions_limit": 10,
        "storage_artifacts_gb": 0.0,
        "storage_limit_gb": 5.0,
    }
    
    if db is None:
        return hosting_kpis
    
    try:
        # Read-only: workflow execution count
        pipeline_executions = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "avg_duration": {"$avg": "$duration_ms"},
                }
            },
        ]
        
        result = await db.workflow_executions.aggregate(pipeline_executions).to_list(1)
        if result:
            hosting_kpis["workflow_executions_30d"] = result[0].get("count", 0)
            hosting_kpis["avg_workflow_duration_ms"] = result[0].get("avg_duration", 0.0)
        
        # Read-only: peak concurrent sessions
        pipeline_sessions = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d-%H", "date": "$timestamp"}},
                    "concurrent": {"$max": "$concurrent_count"},
                }
            },
            {"$sort": {"concurrent": -1}},
            {"$limit": 1},
        ]
        
        session_result = await db.session_metrics.aggregate(pipeline_sessions).to_list(1)
        if session_result:
            hosting_kpis["concurrent_sessions_peak"] = session_result[0].get("concurrent", 0)
        
        # Read-only: storage usage
        pipeline_storage = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total_bytes": {"$sum": "$size_bytes"}}},
        ]
        
        storage_result = await db.artifacts.aggregate(pipeline_storage).to_list(1)
        if storage_result:
            total_bytes = storage_result[0].get("total_bytes", 0)
            hosting_kpis["storage_artifacts_gb"] = total_bytes / (1024 ** 3)
        
    except Exception as exc:
        _logger.error("Error reading hosting metrics: %s", exc)
    
    return hosting_kpis


async def _read_upsell_metrics(
    db: Any,
    user_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Dict[str, Any]:
    """Read domain and email upsell KPIs (read-only)."""
    upsell_kpis = {
        "apps_published": 0,
        "apps_with_custom_domain": 0,
        "email_volume_30d": 0,
        "brand_consistency_score": 0.0,
    }
    
    if db is None:
        return upsell_kpis
    
    try:
        # Read-only: app count and domain status
        apps_cursor = db.apps.find(
            {"user_id": user_id, "status": "published"},
            {"_id": 1, "custom_domain": 1, "branding": 1},
        )
        
        apps = await apps_cursor.to_list(1000)
        upsell_kpis["apps_published"] = len(apps)
        upsell_kpis["apps_with_custom_domain"] = sum(
            1 for app in apps if app.get("custom_domain")
        )
        
        # Calculate brand consistency score (heuristic)
        brand_scores = []
        for app in apps:
            branding = app.get("branding", {})
            score = 0.0
            if branding.get("logo"):
                score += 0.4
            if branding.get("primary_color"):
                score += 0.3
            if branding.get("secondary_color"):
                score += 0.2
            if branding.get("font_family"):
                score += 0.1
            brand_scores.append(score)
        
        if brand_scores:
            upsell_kpis["brand_consistency_score"] = sum(brand_scores) / len(brand_scores)
        
        # Read-only: email volume
        pipeline_email = [
            {
                "$match": {
                    "user_id": user_id,
                    "type": "email",
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {"$count": "total"},
        ]
        
        email_result = await db.notifications.aggregate(pipeline_email).to_list(1)
        if email_result:
            upsell_kpis["email_volume_30d"] = email_result[0].get("total", 0)
        
    except Exception as exc:
        _logger.error("Error reading upsell metrics: %s", exc)
    
    return upsell_kpis


async def _get_user_tier(db: Any, user_id: str) -> str:
    """Read user's current subscription tier (read-only)."""
    if db is None:
        return "free"
    
    try:
        # Read-only: fetch user tier from users collection
        user = await db.users.find_one(
            {"_id": user_id},
            {"subscription_tier": 1},
        )
        if user:
            return user.get("subscription_tier", "free")
    except Exception as exc:
        _logger.error("Error reading user tier: %s", exc)
    
    return "free"


def read_platform_kpis(
    *,
    user_id: Annotated[str, "Platform user ID to collect KPIs for"],
    date_range: Annotated[
        Optional[Dict[str, str]],
        "Optional date range with 'start' and 'end' ISO dates"
    ] = None,
    context_variables: Annotated[
        Optional[Any],
        "Context variables provided by AG2 runtime"
    ] = None,
) -> str:
    """
    Read platform-level KPIs for SubscriptionAdvisor.
    
    This tool is READ-ONLY and TENANT-SCOPED. It:
    - Collects token usage from MozaiksPay ledger
    - Collects hosting metrics from runtime event store
    - Collects upsell signals from app registry
    
    It NEVER:
    - Writes to any collection
    - Calls Stripe or payment APIs
    - Accesses other users' data
    """
    import asyncio
    
    async def _collect() -> PlatformKPIs:
        # Get database connection from runtime context
        db = None
        if context_variables:
            db = getattr(context_variables, "db", None)
            if db is None:
                data = getattr(context_variables, "data", {})
                db = data.get("db") if isinstance(data, dict) else None
        
        start_date, end_date = _get_date_range(date_range)
        
        _logger.info(
            "Collecting platform KPIs for user=%s, range=%s to %s",
            user_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        
        # Collect all KPIs in parallel (all read-only)
        token_kpis, hosting_kpis, upsell_kpis, current_tier = await asyncio.gather(
            _read_token_usage(db, user_id, start_date, end_date),
            _read_hosting_metrics(db, user_id, start_date, end_date),
            _read_upsell_metrics(db, user_id, start_date, end_date),
            _get_user_tier(db, user_id),
        )
        
        # Combine all KPIs
        kpis: PlatformKPIs = {
            **token_kpis,
            **hosting_kpis,
            **upsell_kpis,
            "current_tier": current_tier,
            "collection_timestamp": datetime.now(timezone.utc).isoformat(),
            "date_range_start": start_date.isoformat(),
            "date_range_end": end_date.isoformat(),
        }
        
        return kpis
    
    # Run async collection
    try:
        loop = asyncio.get_running_loop()
        kpis = loop.run_until_complete(_collect())
    except RuntimeError:
        kpis = asyncio.run(_collect())
    
    # Cache KPIs for downstream agents
    _cache_context_value(context_variables, "collected_kpis", kpis)
    _cache_context_value(context_variables, "current_tier", kpis.get("current_tier", "free"))
    
    _logger.info(
        "Platform KPIs collected: tokens_30d=%d, workflows_30d=%d, tier=%s",
        kpis.get("tokens_used_30d", 0),
        kpis.get("workflow_executions_30d", 0),
        kpis.get("current_tier", "unknown"),
    )
    
    return (
        f"Platform KPIs collected for user {user_id}:\n"
        f"- Token usage (30d): {kpis.get('tokens_used_30d', 0):,} / {kpis.get('tier_allocation', 0):,}\n"
        f"- 7-day trend: {kpis.get('tokens_used_7d_trend', 0):.1%}\n"
        f"- Workflow executions (30d): {kpis.get('workflow_executions_30d', 0):,}\n"
        f"- Peak concurrent sessions: {kpis.get('concurrent_sessions_peak', 0)}\n"
        f"- Storage: {kpis.get('storage_artifacts_gb', 0):.2f} GB\n"
        f"- Apps published: {kpis.get('apps_published', 0)}\n"
        f"- Custom domains: {kpis.get('apps_with_custom_domain', 0)}\n"
        f"- Current tier: {kpis.get('current_tier', 'unknown')}\n"
        f"\nKPIs cached in context_variables.collected_kpis"
    )
