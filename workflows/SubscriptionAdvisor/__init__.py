"""
SubscriptionAdvisor Workflow

Advisory-only workflow for subscription recommendations.
MozaiksAI observes and recommends; Control-Plane decides and enforces.

Constraints (enforced at runtime):
- read_only = true
- no_external_mutations = true  
- tenant_scoped = true

This workflow NEVER:
- Calls Stripe or any payment processor
- Mutates subscription state
- Enforces entitlements or gates access
- Stores billing secrets or PII
"""

__version__ = "1.0.0"
__workflow_name__ = "SubscriptionAdvisor"
