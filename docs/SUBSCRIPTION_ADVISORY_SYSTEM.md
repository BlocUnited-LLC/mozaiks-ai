# MozaiksAI SubscriptionAdvisor System

> **Status:** Design Specification  
> **Scope:** Advisory-only (never enforcement)  
> **Principle:** MozaiksAI observes and recommends; Control-Plane decides and enforces.

---

## Overview

MozaiksAI operates as a **SubscriptionAdvisor** for two distinct domains:

| Domain | Description | Consumer |
|--------|-------------|----------|
| **World A** | Mozaiks Platform subscriptions (the foundry itself) | MozaiksCore Control-Plane |
| **World B** | User App subscriptions (apps built on Mozaiks) | App Owners / Control-Plane |

MozaiksAI **never**:
- Calls Stripe or any payment processor
- Mutates subscription state
- Enforces entitlements or gates access
- Stores billing secrets or PII

---

## World A: Mozaiks Platform SubscriptionAdvisor

### KPIs Read from MozaiksAI Telemetry

MozaiksAI reads **its own runtime telemetry** to advise platform operators on subscription-related decisions:

#### 1. AI Token Usage KPIs

| KPI | Source | Advisory Trigger |
|-----|--------|------------------|
| `tokens_used_30d` | MozaiksPay token ledger | > 80% of tier allocation |
| `tokens_used_7d_trend` | Rolling 7-day average | > 15% week-over-week growth |
| `peak_tokens_per_hour` | Hourly max over 7 days | Exceeds burst allowance |
| `model_tier_distribution` | % usage by model (gpt-4 vs gpt-3.5) | > 60% premium model usage |

**Advisory Output:** Recommend token limit increase or tier upgrade.

#### 2. Hosting & Compute KPIs

| KPI | Source | Advisory Trigger |
|-----|--------|------------------|
| `workflow_executions_30d` | Runtime event store | > 80% of tier limit |
| `avg_workflow_duration_ms` | Perf metrics | > 30s average (infra strain) |
| `concurrent_sessions_peak` | WebSocket transport | > 70% of tier concurrency |
| `storage_artifacts_gb` | Artifact store size | > 80% of tier storage |

**Advisory Output:** Recommend hosting tier upgrade.

#### 3. Domain & Email Upsell KPIs

| KPI | Source | Advisory Trigger |
|-----|--------|------------------|
| `apps_with_custom_domain` | App registry | 0 custom domains + high traffic |
| `email_volume_30d` | Notification service | > 500 emails/month |
| `brand_consistency_score` | Heuristic (logo, colors set) | High brand investment, no domain |

**Advisory Output:** Recommend custom domain or email add-on.

---

### Recommendation Payload Schema (World A)

MozaiksAI emits recommendations to Control-Plane via this schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MozaiksPlatformAdvisory",
  "type": "object",
  "required": ["advisory_id", "timestamp", "user_id", "recommendations"],
  "properties": {
    "advisory_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for this advisory"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "user_id": {
      "type": "string",
      "description": "Platform user receiving the advisory"
    },
    "current_tier": {
      "type": "string",
      "enum": ["free", "starter", "pro", "enterprise"]
    },
    "recommendations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "reason", "confidence", "suggested_action"],
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "token_limit_increase",
              "hosting_tier_upgrade",
              "custom_domain",
              "email_addon",
              "storage_expansion",
              "concurrency_boost"
            ]
          },
          "reason": {
            "type": "string",
            "description": "Human-readable explanation"
          },
          "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "0.0-1.0 confidence score"
          },
          "suggested_action": {
            "type": "string",
            "description": "Recommended tier or add-on SKU"
          },
          "supporting_kpis": {
            "type": "object",
            "additionalProperties": true,
            "description": "KPI values that triggered this recommendation"
          },
          "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "default": "medium"
          }
        }
      }
    },
    "next_review_date": {
      "type": "string",
      "format": "date",
      "description": "Suggested date to re-evaluate"
    }
  }
}
```

**Example Payload:**

```json
{
  "advisory_id": "adv-7f3a9c12-4e5b-4d8a-9c3e-1a2b3c4d5e6f",
  "timestamp": "2026-01-16T14:30:00Z",
  "user_id": "usr_abc123",
  "current_tier": "starter",
  "recommendations": [
    {
      "type": "token_limit_increase",
      "reason": "Token usage at 87% of monthly allocation with 12 days remaining. 7-day trend shows 18% growth.",
      "confidence": 0.85,
      "suggested_action": "pro",
      "supporting_kpis": {
        "tokens_used_30d": 87000,
        "tier_allocation": 100000,
        "tokens_used_7d_trend": 0.18
      },
      "urgency": "high"
    },
    {
      "type": "custom_domain",
      "reason": "3 published apps with consistent branding. No custom domain configured.",
      "confidence": 0.65,
      "suggested_action": "domain_addon",
      "supporting_kpis": {
        "apps_published": 3,
        "brand_consistency_score": 0.82
      },
      "urgency": "low"
    }
  ],
  "next_review_date": "2026-02-01"
}
```

---

### World A Boundaries (What MozaiksAI Must NOT Do)

| Forbidden Action | Rationale |
|-----------------|-----------|
| Call Stripe API | Payment processing is Control-Plane only |
| Mutate `subscriptions` collection | Advisory is read-only |
| Block user access based on limits | Enforcement is Control-Plane only |
| Store credit card data | PCI compliance boundary |
| Auto-upgrade users | Requires explicit user consent |
| Send billing emails directly | Notification routing via Control-Plane |
| Access other users' billing data | Tenant isolation |
| Set prices or discounts | Business logic in Control-Plane |

---

## World B: User App SubscriptionAdvisor

MozaiksAI can advise **app owners** on how to structure their app's subscription model.

### Advisory Capabilities

#### 1. App Pricing Tier Proposals

MozaiksAI analyzes the app's feature set and suggests tier structures:

| Input Signal | Advisory Output |
|--------------|-----------------|
| Number of workflows | Suggest tier count (free/pro/enterprise) |
| Tool complexity (API calls, compute) | Suggest per-tier pricing brackets |
| Target market (from app description) | Suggest pricing psychology (freemium vs premium) |
| Competitor analysis (if provided) | Benchmark-aligned tier suggestions |

#### 2. Feature Gating Recommendations

| Input Signal | Advisory Output |
|--------------|-----------------|
| Workflow dependencies | Which workflows to gate behind which tier |
| Tool cost profile | Expensive tools → higher tiers |
| User journey analysis | Core workflows free, advanced workflows paid |

#### 3. Token Budget Proposals

| Input Signal | Advisory Output |
|--------------|-----------------|
| Average tokens per workflow run | Suggested per-user monthly token budget |
| Workflow frequency patterns | Burst vs steady usage tiers |
| Model requirements | Budget adjustments for GPT-4 vs GPT-3.5 |

#### 4. Plugin Access Rules

| Input Signal | Advisory Output |
|--------------|-----------------|
| Plugin cost (external API fees) | Tier-gate expensive plugins |
| Plugin criticality | Core plugins free, premium plugins gated |

---

### Output Format Decision: Advisory Document vs Config JSON

**Recommendation: Produce a higher-level Advisory Document.**

| Approach | Pros | Cons |
|----------|------|------|
| `subscription_config.json` | Directly usable | Too prescriptive, assumes Control-Plane schema |
| Advisory Document | Flexible, human-reviewable | Requires Control-Plane translation |

MozaiksAI outputs an **App SubscriptionAdvisor** that Control-Plane (or app owner) translates into the final `subscription_config.json`.

---

### App SubscriptionAdvisor Schema (World B)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AppSubscriptionAdvisor",
  "type": "object",
  "required": ["advisory_id", "app_id", "timestamp", "proposed_model"],
  "properties": {
    "advisory_id": {
      "type": "string",
      "format": "uuid"
    },
    "app_id": {
      "type": "string"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "proposed_model": {
      "type": "object",
      "properties": {
        "pricing_strategy": {
          "type": "string",
          "enum": ["freemium", "tiered", "usage_based", "flat_rate"],
          "description": "Recommended pricing model"
        },
        "tiers": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "suggested_price_range": {
                "type": "object",
                "properties": {
                  "min_usd": { "type": "number" },
                  "max_usd": { "type": "number" },
                  "billing_period": { 
                    "type": "string",
                    "enum": ["monthly", "yearly"]
                  }
                }
              },
              "included_features": {
                "type": "array",
                "items": { "type": "string" }
              },
              "excluded_features": {
                "type": "array",
                "items": { "type": "string" }
              },
              "token_budget": {
                "type": "object",
                "properties": {
                  "monthly_tokens": { "type": "integer" },
                  "burst_allowance": { "type": "integer" }
                }
              },
              "plugin_access": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Plugin IDs accessible in this tier"
              }
            }
          }
        },
        "rationale": {
          "type": "string",
          "description": "Explanation of why this model was recommended"
        }
      }
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    },
    "alternative_models": {
      "type": "array",
      "description": "Other viable pricing models considered",
      "items": {
        "type": "object",
        "properties": {
          "strategy": { "type": "string" },
          "brief": { "type": "string" }
        }
      }
    }
  }
}
```

**Example Advisory:**

```json
{
  "advisory_id": "app-adv-9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d",
  "app_id": "app_fitness_coach",
  "timestamp": "2026-01-16T15:00:00Z",
  "proposed_model": {
    "pricing_strategy": "freemium",
    "tiers": [
      {
        "name": "Free",
        "suggested_price_range": { "min_usd": 0, "max_usd": 0, "billing_period": "monthly" },
        "included_features": ["basic_workout_plans", "progress_tracking"],
        "excluded_features": ["ai_coach_chat", "nutrition_planner", "api_integrations"],
        "token_budget": { "monthly_tokens": 10000, "burst_allowance": 2000 },
        "plugin_access": ["calendar_sync"]
      },
      {
        "name": "Pro",
        "suggested_price_range": { "min_usd": 9, "max_usd": 15, "billing_period": "monthly" },
        "included_features": ["basic_workout_plans", "progress_tracking", "ai_coach_chat", "nutrition_planner"],
        "excluded_features": ["api_integrations"],
        "token_budget": { "monthly_tokens": 100000, "burst_allowance": 20000 },
        "plugin_access": ["calendar_sync", "health_api"]
      },
      {
        "name": "Enterprise",
        "suggested_price_range": { "min_usd": 49, "max_usd": 99, "billing_period": "monthly" },
        "included_features": ["basic_workout_plans", "progress_tracking", "ai_coach_chat", "nutrition_planner", "api_integrations"],
        "excluded_features": [],
        "token_budget": { "monthly_tokens": 500000, "burst_allowance": 100000 },
        "plugin_access": ["calendar_sync", "health_api", "crm_integration", "webhook_api"]
      }
    ],
    "rationale": "Freemium model recommended based on B2C fitness app pattern. Core tracking free to drive adoption. AI coach and nutrition are high-value differentiators for Pro. API access reserved for Enterprise to monetize power users and gym integrations."
  },
  "confidence": 0.78,
  "alternative_models": [
    {
      "strategy": "usage_based",
      "brief": "Per-AI-interaction pricing. Lower barrier, variable revenue. Consider if user engagement is unpredictable."
    }
  ]
}
```

---

## Workflow Implementation: `SubscriptionAdvisor`

**Recommendation: Yes, implement as a dedicated workflow + tool.**

### Workflow Definition

```
workflows/
  SubscriptionAdvisor/
    SubscriptionAdvisor.workflow.json
    tools/
      read_platform_kpis.py
      read_app_telemetry.py
      generate_platform_advisory.py
      generate_app_advisory.py
```

### Workflow JSON Sketch

```json
{
  "id": "SubscriptionAdvisor",
  "version": "1.0.0",
  "description": "Advisory-only workflow for subscription recommendations",
  "triggers": [
    { "type": "scheduled", "cron": "0 6 * * 1" },
    { "type": "manual", "endpoint": "/api/advisory/trigger" },
    { "type": "threshold", "condition": "token_usage > 0.8" }
  ],
  "inputs": {
    "scope": {
      "type": "string",
      "enum": ["platform", "app"],
      "required": true
    },
    "target_id": {
      "type": "string",
      "description": "user_id for platform scope, app_id for app scope",
      "required": true
    },
    "include_alternatives": {
      "type": "boolean",
      "default": true
    }
  },
  "agents": [
    {
      "name": "KPICollector",
      "role": "Gather telemetry data from runtime and token ledger",
      "tools": ["read_platform_kpis", "read_app_telemetry"]
    },
    {
      "name": "AdvisoryGenerator",
      "role": "Analyze KPIs and generate subscription recommendations",
      "tools": ["generate_platform_advisory", "generate_app_advisory"]
    }
  ],
  "outputs": {
    "advisory_payload": {
      "type": "object",
      "description": "MozaiksPlatformAdvisory or AppSubscriptionAdvisor JSON"
    },
    "delivery_target": {
      "type": "string",
      "enum": ["control_plane_webhook", "user_notification", "dashboard"]
    }
  },
  "constraints": {
    "read_only": true,
    "no_external_mutations": true,
    "tenant_scoped": true
  }
}
```

### Tool Specifications

#### `read_platform_kpis`

| Property | Value |
|----------|-------|
| **Input** | `{ user_id: string, date_range: { start: date, end: date } }` |
| **Output** | `{ tokens_used_30d, tokens_used_7d_trend, workflow_executions_30d, ... }` |
| **Data Sources** | MozaiksPay ledger, runtime event store, perf metrics |
| **Permissions** | Read-only, tenant-scoped |

#### `read_app_telemetry`

| Property | Value |
|----------|-------|
| **Input** | `{ app_id: string, include_workflows: boolean }` |
| **Output** | `{ workflow_list, tool_usage, token_consumption, plugin_usage }` |
| **Data Sources** | App workflow registry, runtime metrics |
| **Permissions** | Read-only, app-scoped |

#### `generate_platform_advisory`

| Property | Value |
|----------|-------|
| **Input** | KPI payload from `read_platform_kpis` |
| **Output** | `MozaiksPlatformAdvisory` JSON |
| **Logic** | Threshold-based rules + ML scoring (confidence) |
| **Permissions** | No mutations, no external calls |

#### `generate_app_advisory`

| Property | Value |
|----------|-------|
| **Input** | App telemetry + app description/market context |
| **Output** | `AppSubscriptionAdvisor` JSON |
| **Logic** | Feature analysis + pricing model matching |
| **Permissions** | No mutations, no external calls |

---

## Integration Points

### Control-Plane Webhook

MozaiksAI posts advisories to Control-Plane:

```
POST /internal/advisory/ingest
Authorization: Bearer <service_token>
Content-Type: application/json

{
  "source": "mozaiks_ai_runtime",
  "advisory_type": "platform|app",
  "payload": { ... }
}
```

Control-Plane then:
1. Persists the advisory
2. Optionally surfaces to user dashboard
3. Translates app advisories into `subscription_config.json` if user approves

### User Notification

For high-urgency advisories, Control-Plane (not MozaiksAI) sends:
- In-app notification
- Email digest
- Dashboard banner

---

## Governance & Audit

| Requirement | Implementation |
|-------------|----------------|
| Audit trail | All advisories logged with `advisory_id`, `user_id`, `timestamp` |
| User consent | Advisories are suggestions; no auto-actions |
| Transparency | Users can view advisory history and supporting KPIs |
| Override | Users can dismiss or snooze advisories |
| Bias review | Periodic review of advisory ML models for fairness |

---

## Summary

| Aspect | Decision |
|--------|----------|
| **Role** | Advisory-only, never enforcer |
| **World A Output** | `MozaiksPlatformAdvisory` JSON to Control-Plane |
| **World B Output** | `AppSubscriptionAdvisor` document (human-reviewable) |
| **Implementation** | Dedicated `SubscriptionAdvisor` workflow |
| **Boundaries** | No Stripe, no mutations, no enforcement, no PII storage |
| **Delivery** | Webhook to Control-Plane; Control-Plane handles UX |

---

## Appendix: File Locations

| Artifact | Path |
|----------|------|
| Workflow definition | `workflows/SubscriptionAdvisor/SubscriptionAdvisor.workflow.json` |
| Platform KPI tool | `workflows/SubscriptionAdvisor/tools/read_platform_kpis.py` |
| App telemetry tool | `workflows/SubscriptionAdvisor/tools/read_app_telemetry.py` |
| Platform advisory generator | `workflows/SubscriptionAdvisor/tools/generate_platform_advisory.py` |
| App advisory generator | `workflows/SubscriptionAdvisor/tools/generate_app_advisory.py` |
| JSON schemas | `config/schemas/advisory/` |
