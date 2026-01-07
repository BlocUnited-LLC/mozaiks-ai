# Runtime Boundaries

MozaiksAI is an **execution engine**. Keeping boundaries strict prevents platform creep.

## Allowed

- Execute declarative workflows
- Validate transport tokens
- Persist session history/state
- Stream events and tool results
- Emit usage metrics

## Not allowed

- Authorization (RBAC, tenant permissions)
- Billing, quotas, subscription enforcement
- Platform policy enforcement (rate limits, moderation)
- Business-specific tools hardcoded into runtime

## Integration pattern

Your platform should enforce auth/billing/policy before issuing a JWT, then MozaiksAI validates the token and runs the workflow.
