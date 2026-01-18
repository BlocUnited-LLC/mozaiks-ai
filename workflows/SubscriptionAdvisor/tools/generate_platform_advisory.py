"""
generate_platform_advisory - Generate MozaiksPlatformAdvisory from KPIs.

Analyzes platform KPIs and produces advisory recommendations for:
- Token limit increases
- Hosting tier upgrades
- Custom domain upsells
- Email add-ons

CONSTRAINTS (enforced):
- read_only = true (no DB writes)
- no_external_mutations = true
- tenant_scoped = true
- allowed_external_calls = ["POST /internal/advisory/ingest"]
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import httpx

_logger = logging.getLogger("tools.SubscriptionAdvisor.generate_platform_advisory")

# ============================================================================
# CONSTRAINT ENFORCEMENT
# ============================================================================

TOOL_CONSTRAINTS = {
    "read_only": True,
    "no_external_mutations": True,
    "tenant_scoped": True,
    "allowed_external_calls": [
        "POST /internal/advisory/ingest",
    ],
    "forbidden_apis": [
        "stripe",
        "payment",
        "billing",
        "subscription.update",
        "subscription.create",
        "subscription.delete",
    ],
    "forbidden_operations": [
        "insert",
        "update",
        "delete",
        "replace",
        "bulk_write",
    ],
}

# Webhook endpoint for Control-Plane (internal only)
ADVISORY_WEBHOOK_URL = "/internal/advisory/ingest"


class Recommendation(TypedDict, total=False):
    """Single recommendation in an advisory."""
    type: str
    reason: str
    confidence: float
    suggested_action: str
    supporting_kpis: Dict[str, Any]
    urgency: str


class MozaiksPlatformAdvisory(TypedDict, total=False):
    """Schema for platform advisory payload (matches SubscriptionAdvisor_SYSTEM.md)."""
    advisory_id: str
    timestamp: str
    user_id: str
    current_tier: str
    recommendations: List[Recommendation]
    next_review_date: str


# ============================================================================
# THRESHOLD RULES
# ============================================================================

# Tier allocations (read from config in production)
TIER_ALLOCATIONS = {
    "free": {
        "tokens_monthly": 10000,
        "workflow_executions": 100,
        "concurrent_sessions": 2,
        "storage_gb": 1.0,
    },
    "starter": {
        "tokens_monthly": 100000,
        "workflow_executions": 1000,
        "concurrent_sessions": 5,
        "storage_gb": 5.0,
    },
    "pro": {
        "tokens_monthly": 500000,
        "workflow_executions": 10000,
        "concurrent_sessions": 20,
        "storage_gb": 25.0,
    },
    "enterprise": {
        "tokens_monthly": 5000000,
        "workflow_executions": 100000,
        "concurrent_sessions": 100,
        "storage_gb": 100.0,
    },
}

# Upgrade paths
TIER_UPGRADE_PATH = {
    "free": "starter",
    "starter": "pro",
    "pro": "enterprise",
    "enterprise": "enterprise",  # No upgrade available
}


def _calculate_token_recommendations(
    kpis: Dict[str, Any],
    current_tier: str,
) -> List[Recommendation]:
    """Analyze token KPIs and generate recommendations."""
    recommendations = []
    
    tier_alloc = TIER_ALLOCATIONS.get(current_tier, TIER_ALLOCATIONS["free"])
    tokens_used = kpis.get("tokens_used_30d", 0)
    tier_limit = tier_alloc["tokens_monthly"]
    usage_pct = tokens_used / tier_limit if tier_limit > 0 else 0
    trend_7d = kpis.get("tokens_used_7d_trend", 0)
    
    # High usage threshold (>80%)
    if usage_pct > 0.8:
        urgency = "high" if usage_pct > 0.95 else "medium"
        confidence = min(0.95, 0.5 + usage_pct * 0.5)
        
        recommendations.append(Recommendation(
            type="token_limit_increase",
            reason=(
                f"Token usage at {usage_pct:.0%} of monthly allocation "
                f"({tokens_used:,} / {tier_limit:,}). "
                + (f"7-day trend shows {trend_7d:.0%} growth." if trend_7d > 0 else "")
            ),
            confidence=confidence,
            suggested_action=TIER_UPGRADE_PATH.get(current_tier, "pro"),
            supporting_kpis={
                "tokens_used_30d": tokens_used,
                "tier_allocation": tier_limit,
                "usage_percent": usage_pct,
                "tokens_used_7d_trend": trend_7d,
            },
            urgency=urgency,
        ))
    
    # High growth trend (>15% week-over-week)
    elif trend_7d > 0.15 and usage_pct > 0.5:
        recommendations.append(Recommendation(
            type="token_limit_increase",
            reason=(
                f"Token usage growing rapidly ({trend_7d:.0%} week-over-week). "
                f"Currently at {usage_pct:.0%} of allocation. "
                f"Projected to exceed limit within 2 weeks."
            ),
            confidence=0.7,
            suggested_action=TIER_UPGRADE_PATH.get(current_tier, "pro"),
            supporting_kpis={
                "tokens_used_30d": tokens_used,
                "tier_allocation": tier_limit,
                "usage_percent": usage_pct,
                "tokens_used_7d_trend": trend_7d,
            },
            urgency="medium",
        ))
    
    # Premium model heavy usage
    model_dist = kpis.get("model_tier_distribution", {})
    premium_usage = sum(
        pct for model, pct in model_dist.items()
        if "gpt-4" in model.lower() or "claude-3" in model.lower()
    )
    
    if premium_usage > 0.6 and current_tier in ("free", "starter"):
        recommendations.append(Recommendation(
            type="token_limit_increase",
            reason=(
                f"High premium model usage ({premium_usage:.0%} of tokens on GPT-4/Claude-3). "
                f"Consider upgrading for better premium model rates."
            ),
            confidence=0.6,
            suggested_action="pro",
            supporting_kpis={
                "model_tier_distribution": model_dist,
                "premium_usage_percent": premium_usage,
            },
            urgency="low",
        ))
    
    return recommendations


def _calculate_hosting_recommendations(
    kpis: Dict[str, Any],
    current_tier: str,
) -> List[Recommendation]:
    """Analyze hosting KPIs and generate recommendations."""
    recommendations = []
    
    tier_alloc = TIER_ALLOCATIONS.get(current_tier, TIER_ALLOCATIONS["free"])
    
    # Workflow execution limits
    wf_executions = kpis.get("workflow_executions_30d", 0)
    wf_limit = tier_alloc["workflow_executions"]
    wf_usage_pct = wf_executions / wf_limit if wf_limit > 0 else 0
    
    if wf_usage_pct > 0.8:
        recommendations.append(Recommendation(
            type="hosting_tier_upgrade",
            reason=(
                f"Workflow executions at {wf_usage_pct:.0%} of monthly limit "
                f"({wf_executions:,} / {wf_limit:,})."
            ),
            confidence=min(0.9, 0.5 + wf_usage_pct * 0.4),
            suggested_action=TIER_UPGRADE_PATH.get(current_tier, "pro"),
            supporting_kpis={
                "workflow_executions_30d": wf_executions,
                "workflow_executions_limit": wf_limit,
                "usage_percent": wf_usage_pct,
            },
            urgency="high" if wf_usage_pct > 0.95 else "medium",
        ))
    
    # Concurrent session limits
    sessions_peak = kpis.get("concurrent_sessions_peak", 0)
    sessions_limit = tier_alloc["concurrent_sessions"]
    sessions_pct = sessions_peak / sessions_limit if sessions_limit > 0 else 0
    
    if sessions_pct > 0.7:
        recommendations.append(Recommendation(
            type="concurrency_boost",
            reason=(
                f"Peak concurrent sessions at {sessions_pct:.0%} of limit "
                f"({sessions_peak} / {sessions_limit}). "
                f"Users may experience delays during peak times."
            ),
            confidence=min(0.85, 0.5 + sessions_pct * 0.4),
            suggested_action=TIER_UPGRADE_PATH.get(current_tier, "pro"),
            supporting_kpis={
                "concurrent_sessions_peak": sessions_peak,
                "concurrent_sessions_limit": sessions_limit,
                "usage_percent": sessions_pct,
            },
            urgency="medium",
        ))
    
    # Storage limits
    storage_gb = kpis.get("storage_artifacts_gb", 0)
    storage_limit = tier_alloc["storage_gb"]
    storage_pct = storage_gb / storage_limit if storage_limit > 0 else 0
    
    if storage_pct > 0.8:
        recommendations.append(Recommendation(
            type="storage_expansion",
            reason=(
                f"Artifact storage at {storage_pct:.0%} of limit "
                f"({storage_gb:.2f} GB / {storage_limit} GB)."
            ),
            confidence=min(0.9, 0.5 + storage_pct * 0.4),
            suggested_action=TIER_UPGRADE_PATH.get(current_tier, "pro"),
            supporting_kpis={
                "storage_artifacts_gb": storage_gb,
                "storage_limit_gb": storage_limit,
                "usage_percent": storage_pct,
            },
            urgency="medium",
        ))
    
    # Long workflow durations (infra strain)
    avg_duration = kpis.get("avg_workflow_duration_ms", 0)
    if avg_duration > 30000:  # > 30 seconds
        recommendations.append(Recommendation(
            type="hosting_tier_upgrade",
            reason=(
                f"Average workflow duration is {avg_duration / 1000:.1f}s, "
                f"indicating potential infrastructure strain. "
                f"Higher tiers include performance optimizations."
            ),
            confidence=0.6,
            suggested_action=TIER_UPGRADE_PATH.get(current_tier, "pro"),
            supporting_kpis={
                "avg_workflow_duration_ms": avg_duration,
            },
            urgency="low",
        ))
    
    return recommendations


def _calculate_upsell_recommendations(
    kpis: Dict[str, Any],
    current_tier: str,
) -> List[Recommendation]:
    """Analyze upsell opportunities (domain, email)."""
    recommendations = []
    
    apps_published = kpis.get("apps_published", 0)
    apps_with_domain = kpis.get("apps_with_custom_domain", 0)
    brand_score = kpis.get("brand_consistency_score", 0)
    email_volume = kpis.get("email_volume_30d", 0)
    
    # Custom domain recommendation
    if apps_published > 0 and apps_with_domain == 0:
        confidence = 0.4 + (brand_score * 0.3) + (min(apps_published, 5) * 0.06)
        
        if confidence > 0.5:  # Only recommend if reasonably confident
            recommendations.append(Recommendation(
                type="custom_domain",
                reason=(
                    f"{apps_published} published app(s) with no custom domain. "
                    f"Brand consistency score: {brand_score:.0%}. "
                    f"Custom domains improve user trust and SEO."
                ),
                confidence=confidence,
                suggested_action="domain_addon",
                supporting_kpis={
                    "apps_published": apps_published,
                    "apps_with_custom_domain": apps_with_domain,
                    "brand_consistency_score": brand_score,
                },
                urgency="low",
            ))
    
    # Email add-on recommendation
    if email_volume > 500 and current_tier in ("free", "starter"):
        recommendations.append(Recommendation(
            type="email_addon",
            reason=(
                f"Email volume of {email_volume:,} in the past 30 days. "
                f"Consider email add-on for higher deliverability and custom sender domains."
            ),
            confidence=0.65,
            suggested_action="email_addon",
            supporting_kpis={
                "email_volume_30d": email_volume,
            },
            urgency="low",
        ))
    
    return recommendations


async def _post_advisory_to_control_plane(
    advisory: MozaiksPlatformAdvisory,
    control_plane_base_url: Optional[str],
    service_token: Optional[str],
) -> bool:
    """
    POST advisory to Control-Plane webhook.
    
    This is the ONLY external call allowed by this tool.
    """
    if not control_plane_base_url:
        _logger.warning("No control_plane_base_url configured, skipping webhook")
        return False
    
    url = f"{control_plane_base_url.rstrip('/')}{ADVISORY_WEBHOOK_URL}"
    
    payload = {
        "source": "mozaiks_ai_runtime",
        "advisory_type": "platform",
        "payload": advisory,
    }
    
    headers = {"Content-Type": "application/json"}
    if service_token:
        headers["Authorization"] = f"Bearer {service_token}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            _logger.info(
                "Advisory %s posted to Control-Plane: status=%d",
                advisory["advisory_id"],
                response.status_code,
            )
            return True
    except httpx.HTTPStatusError as exc:
        _logger.error(
            "Control-Plane webhook failed: status=%d, body=%s",
            exc.response.status_code,
            exc.response.text[:500],
        )
    except Exception as exc:
        _logger.error("Control-Plane webhook error: %s", exc)
    
    return False


def _cache_context_value(context_variables: Any, key: str, value: Any) -> None:
    """Cache a value in context variables."""
    if not context_variables:
        return
    try:
        setter = getattr(context_variables, "set", None)
        if callable(setter):
            setter(key, value)
            return
    except Exception:
        pass
    try:
        data = getattr(context_variables, "data", None)
        if isinstance(data, dict):
            data[key] = value
    except Exception:
        pass


def generate_platform_advisory(
    *,
    kpis: Annotated[
        Optional[Dict[str, Any]],
        "Platform KPIs from read_platform_kpis (or context_variables.collected_kpis)"
    ] = None,
    user_id: Annotated[Optional[str], "User ID for the advisory"] = None,
    post_to_webhook: Annotated[bool, "Whether to POST to Control-Plane"] = True,
    context_variables: Annotated[
        Optional[Any],
        "Context variables provided by AG2 runtime"
    ] = None,
) -> str:
    """
    Generate MozaiksPlatformAdvisory from platform KPIs.
    
    This tool:
    - Analyzes KPIs against threshold rules
    - Generates recommendations with confidence scores
    - POSTs advisory to Control-Plane webhook (if enabled)
    
    It NEVER:
    - Writes to any database collection
    - Calls Stripe or payment APIs
    - Modifies subscription state
    - Auto-upgrades users
    """
    import asyncio
    
    # Get KPIs from context if not provided
    if kpis is None and context_variables:
        kpis = getattr(context_variables, "collected_kpis", None)
        if kpis is None:
            data = getattr(context_variables, "data", {})
            kpis = data.get("collected_kpis") if isinstance(data, dict) else None
    
    if not kpis:
        _logger.error("No KPIs provided for advisory generation")
        return "ERROR: No KPIs available. Run read_platform_kpis first."
    
    # Get user_id
    if not user_id and context_variables:
        user_id = getattr(context_variables, "target_id", None)
        if not user_id:
            data = getattr(context_variables, "data", {})
            user_id = data.get("target_id") if isinstance(data, dict) else None
    
    if not user_id:
        _logger.error("No user_id provided for advisory")
        return "ERROR: No user_id specified."
    
    current_tier = kpis.get("current_tier", "free")
    
    # Generate recommendations
    all_recommendations: List[Recommendation] = []
    all_recommendations.extend(_calculate_token_recommendations(kpis, current_tier))
    all_recommendations.extend(_calculate_hosting_recommendations(kpis, current_tier))
    all_recommendations.extend(_calculate_upsell_recommendations(kpis, current_tier))
    
    # Sort by urgency and confidence
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    all_recommendations.sort(
        key=lambda r: (urgency_order.get(r.get("urgency", "medium"), 1), -r.get("confidence", 0))
    )
    
    # Build advisory
    advisory_id = f"adv-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    next_review = now + timedelta(days=14)  # Review in 2 weeks
    
    advisory: MozaiksPlatformAdvisory = {
        "advisory_id": advisory_id,
        "timestamp": now.isoformat(),
        "user_id": user_id,
        "current_tier": current_tier,
        "recommendations": all_recommendations,
        "next_review_date": next_review.date().isoformat(),
    }
    
    # Cache advisory in context
    _cache_context_value(context_variables, "advisory_payload", advisory)
    _cache_context_value(context_variables, "advisory_id", advisory_id)
    
    # POST to Control-Plane
    delivery_status = "skipped"
    if post_to_webhook:
        control_plane_url = None
        service_token = None
        
        if context_variables:
            data = getattr(context_variables, "data", {})
            if isinstance(data, dict):
                control_plane_url = data.get("control_plane_base_url")
                service_token = data.get("service_token")
        
        async def _post():
            return await _post_advisory_to_control_plane(
                advisory, control_plane_url, service_token
            )
        
        try:
            loop = asyncio.get_running_loop()
            success = loop.run_until_complete(_post())
        except RuntimeError:
            success = asyncio.run(_post())
        
        delivery_status = "delivered" if success else "failed"
    
    _cache_context_value(context_variables, "delivery_status", delivery_status)
    
    _logger.info(
        "Platform advisory generated: id=%s, recommendations=%d, delivery=%s",
        advisory_id,
        len(all_recommendations),
        delivery_status,
    )
    
    # Format summary
    rec_summary = "\n".join(
        f"  - [{r.get('urgency', 'medium').upper()}] {r['type']}: {r['reason'][:80]}..."
        for r in all_recommendations[:5]
    ) or "  No recommendations at this time."
    
    return (
        f"Platform Advisory Generated\n"
        f"===========================\n"
        f"Advisory ID: {advisory_id}\n"
        f"User: {user_id}\n"
        f"Current Tier: {current_tier}\n"
        f"Recommendations: {len(all_recommendations)}\n"
        f"Delivery: {delivery_status}\n"
        f"Next Review: {next_review.date().isoformat()}\n\n"
        f"Top Recommendations:\n{rec_summary}\n\n"
        f"Advisory cached in context_variables.advisory_payload"
    )
