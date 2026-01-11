# MozaiksAI Backend Coordination Runbook

## Overview

This runbook details the operational boundary between the **MozaiksAI Runtime** (this repository) and the **Mozaiks Backend** (platform services).

The Runtime is responsible for:
- Executing agent workflows (AppGenerator, etc.).
- Generating code bundles.
- Validating logic via E2B.

The Backend is responsible for:
- GitHub repository management (creation, secrets, PRs).
- Persistent storage of app metadata.
- Deployment pipelines.

## Architecture

Communication is one-way: **Runtime -> Backend**.
The Runtime uses the `BackendClient` (`core/transport/backend_client.py`) to invoke platform services.

### Authentication
All calls are authenticated via the `X-Internal-Api-Key` header.
The key is configured in the Runtime environment variable: `INTERNAL_API_KEY`.

### API Contract

| Operation | Endpoint | Description |
|-----------|----------|-------------|
| **Get App Spec** | `GET /api/enterprises/{entId}/appgen/spec` | Retrieve app definition/context. |
| **Get Repo Manifest** | `POST /api/apps/{appId}/deploy/repo/manifest` | Get current file hashes from GitHub. |
| **Initial Export** | `POST /api/apps/{appId}/deploy/repo/initial-export` | Create new repo from code bundle. |
| **Create PR** | `POST /api/apps/{appId}/deploy/repo/pull-requests` | Create update PR with patchset. |

## Operational Procedures

### 1. Setting up the Environment
Ensure the following environment variables are set in `.env` or the container environment:
```bash
MOZAIKS_BACKEND_URL=http://localhost:3000  # or production URL
INTERNAL_API_KEY=your-secret-key
```

### 2. Troubleshooting Connectivity
If the Runtime cannot talk to the Backend:
1.  **Check Logs**: Look for `[BackendClient]` errors in the runtime logs.
2.  **Verify Key**: Ensure `INTERNAL_API_KEY` matches the backend's expected key.
3.  **Network**: Ensure the Runtime container can reach the Backend host.

### 3. Handling Export Failures
If `export_app_code_to_github` fails:
- **401 Unauthorized**: Rotate/check `INTERNAL_API_KEY`.
- **404 Not Found**: The `app_id` or `enterprise_id` may be invalid.
- **500 Internal Error**: Check Backend logs for GitHub API rate limits or permission issues.

### 4. Local Development
For local testing, you can mock the Backend or run it locally on port 3000.
The `BackendClient` defaults to `http://localhost:3000` if `MOZAIKS_BACKEND_URL` is not set.

## Security
- **NEVER** log the `INTERNAL_API_KEY`.
- **NEVER** pass GitHub tokens to the Runtime. The Runtime should never know about GitHub credentials.
