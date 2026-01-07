# Self-Hosting MozaiksAI

MozaiksAI can run in two broad modes:

- **Hosted runtime** (you operate it for multiple tenants)
- **Self-hosted runtime** (a customer operates it for their environment)

The runtime behavior is intentionally the same in both cases.

## What You Need

- Python runtime + dependencies (or container image)
- MongoDB
- Model provider credentials (for AG2/OpenAI if you use those backends)

## Recommended Shape

- Put MozaiksAI behind HTTPS
- Terminate TLS at a gateway/load balancer
- Keep MongoDB on a private network

## Auth In Development vs Production

- Local dev: you can run with auth disabled (fast iteration)
- Production: enable auth and treat the runtime as an authenticated execution surface

See: [Auth Boundary](../concepts/auth-boundary.md).
