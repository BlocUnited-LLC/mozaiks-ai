"""
generate_app_advisory - Generate AppSubscriptionAdvisor from app telemetry.

Analyzes app telemetry and produces advisory recommendations for:
- Pricing strategy (freemium, tiered, usage-based, flat-rate)
- Tier structure with feature gating
- Token budget per tier
- Plugin access rules

CONSTRAINTS (enforced):
- read_only = true (no DB writes)
- no_external_mutations = true
- tenant_scoped = true
- allowed_external_calls = ["POST /internal/advisory/ingest"]

OUTPUT: AppSubscriptionAdvisor document (NOT subscription_config.json)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import httpx

_logger = logging.getLogger("tools.SubscriptionAdvisor.generate_app_advisory")

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
    "forbidden_outputs": [
        "subscription_config.json",  # We output advisory docs, not config
    ],
}

ADVISORY_WEBHOOK_URL = "/internal/advisory/ingest"


class PriceRange(TypedDict, total=False):
    """Suggested price range for a tier."""
    min_usd: float
    max_usd: float
    billing_period: str


class TokenBudget(TypedDict, total=False):
    """Token budget for a tier."""
    monthly_tokens: int
    burst_allowance: int


class TierProposal(TypedDict, total=False):
    """Proposed subscription tier."""
    name: str
    suggested_price_range: PriceRange
    included_features: List[str]
    excluded_features: List[str]
    token_budget: TokenBudget
    plugin_access: List[str]


class ProposedModel(TypedDict, total=False):
    """Proposed subscription model."""
    pricing_strategy: str
    tiers: List[TierProposal]
    rationale: str


class AlternativeModel(TypedDict, total=False):
    """Alternative pricing model."""
    strategy: str
    brief: str


class AppSubscriptionAdvisor(TypedDict, total=False):
    """Schema for app SubscriptionAdvisor (matches SubscriptionAdvisor_SYSTEM.md)."""
    advisory_id: str
    app_id: str
    timestamp: str
    proposed_model: ProposedModel
    confidence: float
    alternative_models: List[AlternativeModel]


# ============================================================================
# PRICING STRATEGY ANALYSIS
# ============================================================================

def _determine_pricing_strategy(telemetry: Dict[str, Any]) -> tuple[str, float, str]:
    """
    Determine recommended pricing strategy based on app telemetry.
    
    Returns: (strategy, confidence, rationale)
    """
    workflow_count = telemetry.get("workflow_count", 0)
    external_tools = telemetry.get("external_api_tools_count", 0)
    total_tokens = telemetry.get("total_tokens_30d", 0)
    avg_tokens = telemetry.get("avg_tokens_per_session", 0)
    target_market = telemetry.get("target_market", "general").lower()
    plugins_with_cost = len(telemetry.get("plugins_with_external_cost", []))
    
    # Signals for each strategy
    freemium_score = 0.0
    tiered_score = 0.0
    usage_score = 0.0
    flat_score = 0.0
    
    # B2C indicators favor freemium
    if any(m in target_market for m in ["consumer", "b2c", "personal", "fitness", "health", "education"]):
        freemium_score += 0.3
    
    # B2B indicators favor tiered
    if any(m in target_market for m in ["business", "b2b", "enterprise", "saas", "professional"]):
        tiered_score += 0.3
    
    # High workflow count suggests tiered (feature differentiation)
    if workflow_count > 5:
        tiered_score += 0.2
    elif workflow_count <= 2:
        flat_score += 0.2
    
    # High external API usage suggests usage-based (cost pass-through)
    if external_tools > 3 or plugins_with_cost > 2:
        usage_score += 0.3
    
    # High token variance suggests usage-based
    if avg_tokens > 0:
        token_variance = total_tokens / (avg_tokens * 30) if avg_tokens > 0 else 1
        if token_variance > 2:  # High variance
            usage_score += 0.2
    
    # Simple apps favor flat rate
    if workflow_count <= 3 and external_tools <= 1:
        flat_score += 0.25
    
    # Default boost for freemium (proven adoption driver)
    freemium_score += 0.15
    
    # Select strategy
    scores = {
        "freemium": freemium_score,
        "tiered": tiered_score,
        "usage_based": usage_score,
        "flat_rate": flat_score,
    }
    
    strategy = max(scores, key=scores.get)
    confidence = min(0.9, scores[strategy] + 0.3)  # Base confidence + score
    
    rationales = {
        "freemium": (
            f"Freemium model recommended based on {target_market} market. "
            f"Core features free to drive adoption, premium features for conversion."
        ),
        "tiered": (
            f"Tiered model recommended due to {workflow_count} workflows offering "
            f"clear feature differentiation. Good for {target_market} segment."
        ),
        "usage_based": (
            f"Usage-based model recommended due to high API/plugin costs "
            f"({external_tools} external tools, {plugins_with_cost} paid plugins). "
            f"Aligns cost with value delivered."
        ),
        "flat_rate": (
            f"Flat-rate model recommended for simple app structure "
            f"({workflow_count} workflows). Easy to understand, predictable revenue."
        ),
    }
    
    return strategy, confidence, rationales[strategy]


def _generate_tier_proposals(
    telemetry: Dict[str, Any],
    strategy: str,
) -> List[TierProposal]:
    """Generate tier proposals based on telemetry and strategy."""
    
    workflows = telemetry.get("workflow_list", [])
    tools = telemetry.get("tool_usage", [])
    plugins = telemetry.get("plugin_usage", [])
    avg_tokens = telemetry.get("avg_tokens_per_session", 1000)
    
    # Categorize workflows by cost tier
    free_workflows = [w["name"] for w in workflows if w.get("cost_tier") == "low"]
    pro_workflows = [w["name"] for w in workflows if w.get("cost_tier") == "medium"]
    enterprise_workflows = [w["name"] for w in workflows if w.get("cost_tier") == "high"]
    
    # Categorize plugins
    free_plugins = [p["plugin_id"] for p in plugins if not p.get("has_external_cost")]
    paid_plugins = [p["plugin_id"] for p in plugins if p.get("has_external_cost")]
    
    # All features for reference
    all_features = free_workflows + pro_workflows + enterprise_workflows
    
    if strategy == "freemium":
        return [
            TierProposal(
                name="Free",
                suggested_price_range=PriceRange(min_usd=0, max_usd=0, billing_period="monthly"),
                included_features=free_workflows or all_features[:2],
                excluded_features=pro_workflows + enterprise_workflows,
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 10),  # ~10 sessions
                    burst_allowance=int(avg_tokens * 2),
                ),
                plugin_access=free_plugins[:2] if free_plugins else [],
            ),
            TierProposal(
                name="Pro",
                suggested_price_range=PriceRange(min_usd=9, max_usd=19, billing_period="monthly"),
                included_features=free_workflows + pro_workflows,
                excluded_features=enterprise_workflows,
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 100),  # ~100 sessions
                    burst_allowance=int(avg_tokens * 20),
                ),
                plugin_access=free_plugins + paid_plugins[:2],
            ),
            TierProposal(
                name="Enterprise",
                suggested_price_range=PriceRange(min_usd=49, max_usd=99, billing_period="monthly"),
                included_features=all_features,
                excluded_features=[],
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 500),  # ~500 sessions
                    burst_allowance=int(avg_tokens * 100),
                ),
                plugin_access=free_plugins + paid_plugins,
            ),
        ]
    
    elif strategy == "tiered":
        return [
            TierProposal(
                name="Starter",
                suggested_price_range=PriceRange(min_usd=9, max_usd=15, billing_period="monthly"),
                included_features=free_workflows or all_features[:3],
                excluded_features=pro_workflows + enterprise_workflows,
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 30),
                    burst_allowance=int(avg_tokens * 5),
                ),
                plugin_access=free_plugins[:3] if free_plugins else [],
            ),
            TierProposal(
                name="Professional",
                suggested_price_range=PriceRange(min_usd=29, max_usd=49, billing_period="monthly"),
                included_features=free_workflows + pro_workflows,
                excluded_features=enterprise_workflows,
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 150),
                    burst_allowance=int(avg_tokens * 30),
                ),
                plugin_access=free_plugins + paid_plugins[:3],
            ),
            TierProposal(
                name="Enterprise",
                suggested_price_range=PriceRange(min_usd=99, max_usd=199, billing_period="monthly"),
                included_features=all_features,
                excluded_features=[],
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 1000),
                    burst_allowance=int(avg_tokens * 200),
                ),
                plugin_access=free_plugins + paid_plugins,
            ),
        ]
    
    elif strategy == "usage_based":
        return [
            TierProposal(
                name="Pay-as-you-go",
                suggested_price_range=PriceRange(min_usd=0, max_usd=0, billing_period="monthly"),
                included_features=all_features,
                excluded_features=[],
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 5),  # Small free tier
                    burst_allowance=0,
                ),
                plugin_access=free_plugins,
            ),
            TierProposal(
                name="Growth",
                suggested_price_range=PriceRange(min_usd=19, max_usd=39, billing_period="monthly"),
                included_features=all_features,
                excluded_features=[],
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 100),
                    burst_allowance=int(avg_tokens * 50),
                ),
                plugin_access=free_plugins + paid_plugins,
            ),
            TierProposal(
                name="Scale",
                suggested_price_range=PriceRange(min_usd=99, max_usd=249, billing_period="monthly"),
                included_features=all_features,
                excluded_features=[],
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 500),
                    burst_allowance=int(avg_tokens * 250),
                ),
                plugin_access=free_plugins + paid_plugins,
            ),
        ]
    
    else:  # flat_rate
        return [
            TierProposal(
                name="Standard",
                suggested_price_range=PriceRange(min_usd=15, max_usd=29, billing_period="monthly"),
                included_features=all_features,
                excluded_features=[],
                token_budget=TokenBudget(
                    monthly_tokens=int(avg_tokens * 200),
                    burst_allowance=int(avg_tokens * 50),
                ),
                plugin_access=free_plugins + paid_plugins,
            ),
        ]


def _generate_alternative_models(
    primary_strategy: str,
    telemetry: Dict[str, Any],
) -> List[AlternativeModel]:
    """Generate alternative pricing model suggestions."""
    
    alternatives = []
    
    all_strategies = {
        "freemium": (
            "Free tier with premium upgrades. "
            "Good for consumer adoption and viral growth."
        ),
        "tiered": (
            "Multiple feature-differentiated tiers. "
            "Good for B2B with clear upgrade paths."
        ),
        "usage_based": (
            "Pay-per-use pricing aligned with consumption. "
            "Good for variable workloads and cost-sensitive users."
        ),
        "flat_rate": (
            "Single price for full access. "
            "Simple to understand, predictable for both sides."
        ),
    }
    
    for strategy, brief in all_strategies.items():
        if strategy != primary_strategy:
            alternatives.append(AlternativeModel(strategy=strategy, brief=brief))
    
    return alternatives


async def _post_advisory_to_control_plane(
    advisory: AppSubscriptionAdvisor,
    control_plane_base_url: Optional[str],
    service_token: Optional[str],
) -> bool:
    """POST advisory to Control-Plane webhook (only allowed external call)."""
    if not control_plane_base_url:
        _logger.warning("No control_plane_base_url configured, skipping webhook")
        return False
    
    url = f"{control_plane_base_url.rstrip('/')}{ADVISORY_WEBHOOK_URL}"
    
    payload = {
        "source": "mozaiks_ai_runtime",
        "advisory_type": "app",
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
                "App advisory %s posted to Control-Plane: status=%d",
                advisory["advisory_id"],
                response.status_code,
            )
            return True
    except httpx.HTTPStatusError as exc:
        _logger.error(
            "Control-Plane webhook failed: status=%d",
            exc.response.status_code,
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


def generate_app_advisory(
    *,
    telemetry: Annotated[
        Optional[Dict[str, Any]],
        "App telemetry from read_app_telemetry (or context_variables.collected_kpis)"
    ] = None,
    app_id: Annotated[Optional[str], "App ID for the advisory"] = None,
    include_alternatives: Annotated[bool, "Include alternative pricing models"] = True,
    post_to_webhook: Annotated[bool, "Whether to POST to Control-Plane"] = True,
    context_variables: Annotated[
        Optional[Any],
        "Context variables provided by AG2 runtime"
    ] = None,
) -> str:
    """
    Generate AppSubscriptionAdvisor from app telemetry.
    
    This tool:
    - Analyzes app workflows, tools, and usage patterns
    - Recommends pricing strategy and tier structure
    - Proposes token budgets and feature gating
    - POSTs advisory to Control-Plane webhook (if enabled)
    
    OUTPUT: AppSubscriptionAdvisor document
    NOT: subscription_config.json (Control-Plane translates advisory to config)
    
    It NEVER:
    - Writes to any database collection
    - Calls Stripe or payment APIs
    - Generates subscription_config.json directly
    """
    import asyncio
    
    # Get telemetry from context if not provided
    if telemetry is None and context_variables:
        telemetry = getattr(context_variables, "collected_kpis", None)
        if telemetry is None:
            data = getattr(context_variables, "data", {})
            telemetry = data.get("collected_kpis") if isinstance(data, dict) else None
    
    if not telemetry:
        _logger.error("No telemetry provided for advisory generation")
        return "ERROR: No telemetry available. Run read_app_telemetry first."
    
    # Get app_id
    if not app_id:
        app_id = telemetry.get("app_id")
    if not app_id and context_variables:
        app_id = getattr(context_variables, "target_id", None)
        if not app_id:
            data = getattr(context_variables, "data", {})
            app_id = data.get("target_id") if isinstance(data, dict) else None
    
    if not app_id:
        _logger.error("No app_id provided for advisory")
        return "ERROR: No app_id specified."
    
    # Get include_alternatives from context if not explicitly set
    if context_variables:
        data = getattr(context_variables, "data", {})
        if isinstance(data, dict) and "include_alternatives" in data:
            include_alternatives = data["include_alternatives"]
    
    # Determine pricing strategy
    strategy, confidence, rationale = _determine_pricing_strategy(telemetry)
    
    # Generate tier proposals
    tiers = _generate_tier_proposals(telemetry, strategy)
    
    # Generate alternatives
    alternatives = []
    if include_alternatives:
        alternatives = _generate_alternative_models(strategy, telemetry)
    
    # Build advisory
    advisory_id = f"app-adv-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    
    advisory: AppSubscriptionAdvisor = {
        "advisory_id": advisory_id,
        "app_id": app_id,
        "timestamp": now.isoformat(),
        "proposed_model": ProposedModel(
            pricing_strategy=strategy,
            tiers=tiers,
            rationale=rationale,
        ),
        "confidence": confidence,
        "alternative_models": alternatives,
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
        "App advisory generated: id=%s, strategy=%s, tiers=%d, delivery=%s",
        advisory_id,
        strategy,
        len(tiers),
        delivery_status,
    )
    
    # Format tier summary
    tier_summary = "\n".join(
        f"  - {t['name']}: ${t['suggested_price_range']['min_usd']}-${t['suggested_price_range']['max_usd']}/mo, "
        f"{t['token_budget']['monthly_tokens']:,} tokens"
        for t in tiers
    )
    
    return (
        f"App SubscriptionAdvisor Generated\n"
        f"====================================\n"
        f"Advisory ID: {advisory_id}\n"
        f"App: {telemetry.get('app_name', app_id)} ({app_id})\n"
        f"Strategy: {strategy} (confidence: {confidence:.0%})\n"
        f"Delivery: {delivery_status}\n\n"
        f"Rationale:\n{rationale}\n\n"
        f"Proposed Tiers:\n{tier_summary}\n\n"
        f"Alternatives: {', '.join(a['strategy'] for a in alternatives) if alternatives else 'None'}\n\n"
        f"Advisory cached in context_variables.advisory_payload\n"
        f"NOTE: This is an advisory document. Control-Plane will translate to subscription_config.json if approved."
    )
