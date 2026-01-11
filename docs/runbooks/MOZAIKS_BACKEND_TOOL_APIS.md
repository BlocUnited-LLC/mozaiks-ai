# MOZAIKS_BACKEND_TOOL_APIS.md

Runbook for MozaiksAI Tool API Endpoints in AuthServer.Api

---

## What this enables

MozaiksAI (the AI-powered app generation wizard) can call the backend to:

1. **Fetch app generation specs** — Get TechStack, design inputs, and metadata needed for code generation (no secrets exposed)
2. **Request repo manifest** — Get the current state of a GitHub repository (file listing, base commit SHA)
3. **Request initial export** — Push initial code files to a new or existing GitHub repository
4. **Request PR creation** — Create a pull request with code changes (patchset)
5. **Generate deployment templates** — Generate Dockerfiles and GitHub Actions workflows via the DeploymentManager/Jinja-style template engine

All long-lived secrets (GitHub tokens, Azure credentials, DockerHub tokens) stay in the backend — MozaiksAI never sees them.

---

## Auth

All endpoints support two authentication modes:

### 1. S2S (Service-to-Service) Authentication
- **Header**: `X-Internal-Api-Key`
- **Config**: `Deployment:InternalApiKey` in appsettings
- **Usage**: MozaiksAI runtime calls backend with this key
- **Response on failure**: `401 Unauthorized` with `{ error: "Unauthorized", reason: "InvalidInternalApiKey" }`

### 2. JWT Bearer Authentication
- **Header**: `Authorization: Bearer <token>`
- **Usage**: Direct user calls (e.g., from Moz UI)
- **Response on failure**: `401 Unauthorized`

**Key validation uses constant-time comparison** to prevent timing attacks.

**Configuration**:
```json
{
  "Deployment": {
    "InternalApiKey": "<your-secure-key-here>"  // REQUIRED for S2S
  }
}
```

**⚠️ WARNING**: If `InternalApiKey` is `"replace_me"` or empty, S2S auth will reject all requests.

---

## Stored secrets & encryption

### Secrets Boundary
The backend is the **only** holder of:
- **GitHub Personal Access Token** (`GitHub:AccessToken`)
- **Azure SP Credentials** (`AZURE_CREDENTIALS` in GitHub Secrets)
- **DockerHub Token** (`DOCKERHUB_TOKEN` in GitHub Secrets)
- **Database connection strings** (stored encrypted in MongoDB)
- **App API keys** (hashed with SHA-256)

### Encryption at Rest
ASP.NET Core Data Protection is configured for persistent key storage:

```csharp
var dataProtectionKeysPath = builder.Configuration.GetValue<string>("DataProtection:KeysPath");
if (!string.IsNullOrWhiteSpace(dataProtectionKeysPath))
{
    Directory.CreateDirectory(dataProtectionKeysPath);
    dataProtection.PersistKeysToFileSystem(new DirectoryInfo(dataProtectionKeysPath));
}
```

**Configuration**:
```json
{
  "DataProtection": {
    "KeysPath": "/app/keys"  // Mounted volume in containers
  }
}
```

**Production Requirements**:
- Mount a persistent volume at `DataProtection:KeysPath`
- Or use Azure Blob Storage / Azure Key Vault for key ring storage
- Keys must be shared across all AuthServer instances for decryption to work

---

## Endpoints

### 1. GET /api/apps/{appId}/appgen/spec
**Purpose**: Fetch app generation spec (non-sensitive data only)

**Response**: `AppGenSpecResponse`
```json
{
  "appId": "string",
  "appName": "string",
  "description": "string",
  "industry": "string",
  "ownerUserId": "string",
  "techStack": {
    "frontend": { "framework": "react", "port": 3000 },
    "backend": { "framework": "fastapi", "port": 8000 }
  },
  "featureFlags": { "ai": true },
  "gitHubRepoFullName": "org/repo-name",
  "databaseName": "app_db",
  "status": "Active"
}
```

**🔒 NEVER returns**: API keys, tokens, credentials, connection strings

---

### 2. POST /api/apps/{appId}/deploy/repo/manifest
**Purpose**: Get current repo state for diffing

**Request**: `RepoManifestRequest`
```json
{
  "repoUrl": "https://github.com/org/repo",  // optional if app has repo configured
  "userId": "user-id"  // for S2S calls
}
```

**Response**: `RepoManifestResponse`
```json
{
  "baseCommitSha": "abc123...",
  "files": [
    { "path": "src/main.py", "sha256": "...", "sizeBytes": 1234 }
  ]
}
```

---

### 3. POST /api/apps/{appId}/deploy/repo/pull-requests
**Purpose**: Create a PR with code changes

**Request**: `CreatePullRequestRequest`
```json
{
  "repoUrl": "https://github.com/org/repo",
  "userId": "user-id",
  "baseCommitSha": "abc123...",
  "branchName": "mozaiksai/update-001",
  "title": "MozaiksAI: Add new feature",
  "body": "Description of changes",
  "changes": [
    { "path": "src/new_file.py", "operation": "add", "contentBase64": "..." },
    { "path": "src/old_file.py", "operation": "modify", "contentBase64": "..." },
    { "path": "src/delete_me.py", "operation": "delete" }
  ]
}
```

**Response**: `CreatePullRequestResponse`
```json
{
  "prUrl": "https://github.com/org/repo/pull/123"
}
```

---

### 4. POST /api/apps/{appId}/deploy/repo/initial-export
**Purpose**: Export initial code to a new or existing repo

**Request**: `InitialExportRequest`
```json
{
  "repoUrl": "https://github.com/org/repo",  // required if createRepo=false
  "userId": "user-id",
  "createRepo": true,
  "repoName": "my-new-app",  // used when createRepo=true
  "files": [
    { "path": "src/main.py", "operation": "add", "contentBase64": "..." }
  ],
  "commitMessage": "Initial export from MozaiksAI"
}
```

**Response**: `InitialExportResponse`
```json
{
  "success": true,
  "repoUrl": "https://github.com/org/my-new-app",
  "repoFullName": "org/my-new-app",
  "baseCommitSha": "abc123..."
}
```

---

### 5. POST /api/apps/{appId}/deploy/templates/generate
**Purpose**: Generate Dockerfiles and GitHub Actions workflows

**Request**: `GenerateTemplatesRequest`
```json
{
  "userId": "user-id",
  "techStack": {
    "frontend": { "framework": "react", "port": 3000 },
    "backend": { "framework": "fastapi", "port": 8000 }
  },
  "includeWorkflow": true,
  "includeDockerfiles": true,
  "outputFormat": "files"
}
```

**Response**: `GenerateTemplatesResponse`
```json
{
  "success": true,
  "files": [
    { "path": "backend/Dockerfile", "contentBase64": "...", "description": "Backend Dockerfile" },
    { "path": "frontend/Dockerfile", "contentBase64": "...", "description": "Frontend Dockerfile" },
    { "path": ".github/workflows/deploy.yml", "contentBase64": "...", "description": "GitHub Actions workflow" }
  ]
}
```

---

### 6. POST /api/apps/{appId}/deploy/scaffold ⭐ NEW
**Purpose**: Generate complete app scaffold including all framework-specific boilerplate files.
This endpoint replaces FileManager's framework-specific file generation logic from project-aid-v2.

**Request**: `GenerateScaffoldRequest`
```json
{
  "userId": "user-id",
  "dependencies": {
    "frontend": ["axios", "chart.js", "tailwindcss"],
    "backend": ["motor", "pydantic", "python-jose"]
  },
  "includeDockerfiles": true,
  "includeWorkflow": true,
  "includeBoilerplate": true,
  "includeInitFiles": true,
  "techStackOverride": {
    "frontend": { "framework": "react", "port": 3000 },
    "backend": { "framework": "fastapi", "port": 8000 }
  }
}
```

**Response**: `GenerateScaffoldResponse`
```json
{
  "success": true,
  "appId": "...",
  "techStack": {
    "frontend": { "framework": "react", "language": "javascript", "port": 3000 },
    "backend": { "framework": "fastapi", "language": "python", "port": 8000 }
  },
  "files": [
    { "path": "frontend/public/index.html", "contentBase64": "...", "category": "boilerplate", "description": "React HTML entry point with env.js reference" },
    { "path": "frontend/public/env.js", "contentBase64": "...", "category": "boilerplate", "description": "Runtime environment variables injection" },
    { "path": "frontend/public/nginx.conf", "contentBase64": "...", "category": "boilerplate", "description": "Nginx config for SPA routing" },
    { "path": "frontend/public/entrypoint.sh", "contentBase64": "...", "category": "boilerplate", "description": "Docker entrypoint for env var substitution" },
    { "path": "frontend/package.json", "contentBase64": "...", "category": "dependencies", "description": "React dependencies file" },
    { "path": "backend/__init__.py", "contentBase64": "...", "category": "init", "description": "Python init file for backend root" },
    { "path": "backend/routers/__init__.py", "contentBase64": "...", "category": "init", "description": "Python init file for routers module" },
    { "path": "backend/requirements.txt", "contentBase64": "...", "category": "dependencies", "description": "FastAPI dependencies file" },
    { "path": "backend/Dockerfile", "contentBase64": "...", "category": "dockerfile", "description": "Backend Dockerfile" },
    { "path": "frontend/Dockerfile", "contentBase64": "...", "category": "dockerfile", "description": "Frontend Dockerfile" },
    { "path": ".github/workflows/deploy.yml", "contentBase64": "...", "category": "workflow", "description": "GitHub Actions deployment workflow" }
  ],
  "summary": {
    "totalFiles": 11,
    "categories": { "boilerplate": 4, "dependencies": 2, "init": 2, "dockerfile": 2, "workflow": 1 },
    "frontendFramework": "react",
    "backendFramework": "fastapi"
  }
}
```

**Key Features**:
- Replaces FileManager's framework-specific logic
- Generates React boilerplate: `index.html`, `env.js`, `nginx.conf`, `entrypoint.sh`
- Generates `__init__.py` files for Python backends
- Merges custom dependencies with framework base packages
- Filters Python built-in modules from requirements.txt
- Handles package conflicts (e.g., removes `bson` when `pymongo` is present)
- All files returned as base64 for easy PR creation

---

### 7. GET /api/appgen/supported-stacks ⭐ NEW
**Purpose**: Get list of supported tech stacks for app creation.

**Response**: `SupportedTechStacksResponse`
```json
{
  "frontend": [
    { "framework": "react", "displayName": "React", "language": "javascript", "defaultPort": 3000, "isDefault": true },
    { "framework": "streamlit", "displayName": "Streamlit", "language": "python", "defaultPort": 8501, "isDefault": false }
  ],
  "backend": [
    { "framework": "fastapi", "displayName": "FastAPI", "language": "python", "defaultPort": 8000, "isDefault": true },
    { "framework": "flask", "displayName": "Flask", "language": "python", "defaultPort": 5000, "isDefault": false }
  ],
  "databases": [
    { "type": "mongodb", "displayName": "MongoDB", "provider": "Atlas", "isDefault": true }
  ],
  "defaultStack": {
    "frontend": { "framework": "react", "language": "javascript", "port": 3000 },
    "backend": { "framework": "fastapi", "language": "python", "port": 8000 },
    "database": { "type": "mongodb", "provider": "Atlas" }
  }
}
```

---

## Database Endpoints (DBManager Migration)

These endpoints replace DBManager's database provisioning logic from project-aid-v2.
**All endpoints support both JWT and S2S authentication**.

### 8. POST /api/apps/{appId}/database/provision ⭐ DBManager
**Purpose**: Provision a new MongoDB database for an app (`appdb_{appId}`).

**Request**: `ProvisionDatabaseRequest`
```json
{
  "userId": "user-id"  // optional, for audit trail (defaults to "system" for S2S)
}
```

**Response**:
```json
{
  "databaseName": "appdb_abc123",
  "connectionString": "mongodb://...",  // only shown on first provision
  "message": "Database provisioned. Save the connection string - it won't be shown again."
}
```

**Notes**:
- Creates database named `appdb_{appId}`
- Connection string is shown ONCE on first provisioning
- Subsequent calls return `"message": "Database already provisioned."` without connection string
- Connection string is encrypted and stored in `MozaiksApps` collection

---

### 9. POST /api/apps/{appId}/database/schema ⭐ DBManager
**Purpose**: Apply schema definition to an app's database (create collections, validators, indexes).

**Request**: `ApplySchemaRequest`
```json
{
  "userId": "user-id",  // optional
  "schema": {
    "tables": [
      {
        "name": "users",
        "columns": [
          { "name": "email", "type": "string", "constraints": ["unique", "required"] },
          { "name": "name", "type": "string" },
          { "name": "createdAt", "type": "datetime" },
          { "name": "tags", "type": "array", "itemType": "string" }
        ],
        "indices": ["email", "createdAt"]
      },
      {
        "name": "posts",
        "columns": [
          { "name": "title", "type": "string", "constraints": ["required"] },
          { "name": "authorId", "type": "string" },
          { "name": "content", "type": "string" }
        ],
        "constraints": { "unique": ["title"] }
      }
    ]
  }
}
```

**Response**:
```json
{
  "message": "Schema applied successfully"
}
```

**Type mappings** (from DatabaseAgent output to MongoDB validators):
- `string` → `{ bsonType: "string" }`
- `int` / `integer` → `{ bsonType: "int" }`
- `float` / `double` → `{ bsonType: "double" }`
- `bool` / `boolean` → `{ bsonType: "bool" }`
- `datetime` → `{ bsonType: "date" }`
- `array` → `{ bsonType: "array", items: { bsonType: "..." } }` (uses `itemType`)
- `object` → `{ bsonType: "object" }`

---

### 10. POST /api/apps/{appId}/database/seed ⭐ DBManager
**Purpose**: Seed an app's database with initial data.

**Request**: `SeedDatabaseRequest`
```json
{
  "userId": "user-id",  // optional
  "seedData": {
    "users": [
      { "email": "admin@example.com", "name": "Admin User", "tags": ["admin", "active"] },
      { "email": "test@example.com", "name": "Test User", "tags": ["user"] }
    ],
    "posts": [
      { "title": "Welcome", "authorId": "user-1", "content": "Hello world!" }
    ]
  }
}
```

**Alternative format** (explicit collections wrapper):
```json
{
  "userId": "user-id",
  "seedData": {
    "collections": {
      "users": [...],
      "posts": [...]
    }
  }
}
```

**Response**:
```json
{
  "message": "Database seeded successfully"
}
```

**Notes**:
- Inserts documents into existing collections
- Does not create collections (call `/schema` first)
- Handles both flat format and `{ collections: {...} }` wrapper

---

### 11. GET /api/apps/{appId}/database/status
**Purpose**: Get provisioning status of an app's database.

**Request**: Query parameter `userId` (optional, for S2S calls)

**Response**:
```json
{
  "provisioned": true,
  "databaseName": "appdb_abc123",
  "provisionedAt": "2024-01-15T10:30:00Z"
}
```

---

## DBManager Migration Summary

The database endpoints replace these DBManager responsibilities:

| DBManager (project-aid-v2) | DatabaseProvisioningService (backend) |
|---------------------------|---------------------------------------|
| Create per-app database | `POST /database/provision` |
| Parse `schema.json` from DatabaseAgent | `POST /database/schema` |
| Apply JSON Schema validators | Built into ApplySchemaAsync |
| Create indexes from schema | Index creation from `indices` array |
| Parse `seed.json` from DatabaseAgent | `POST /database/seed` |
| Insert seed documents | Built into SeedDatabaseAsync |
| Store encrypted connection string | Encrypted via Data Protection |

**MozaiksAI Usage**:
```python
# After DatabaseAgent generates schema.json and seed.json:

# 1. Provision database
provision = requests.post(
    f"{BACKEND_URL}/api/apps/{app_id}/database/provision",
    headers={"X-Internal-Api-Key": API_KEY},
    json={"userId": "mozaiksai"}
).json()

# 2. Apply schema from DatabaseAgent output
schema = load_agent_output("schema.json")
requests.post(
    f"{BACKEND_URL}/api/apps/{app_id}/database/schema",
    headers={"X-Internal-Api-Key": API_KEY},
    json={"userId": "mozaiksai", "schema": schema}
)

# 3. Seed with initial data from DatabaseAgent output
seed = load_agent_output("seed.json")
requests.post(
    f"{BACKEND_URL}/api/apps/{app_id}/database/seed",
    headers={"X-Internal-Api-Key": API_KEY},
    json={"userId": "mozaiksai", "seedData": seed}
)
```

---

## Copy/paste examples

### Fetch app spec (S2S)
```bash
curl -X GET "http://localhost:8020/api/apps/APP_ID_HERE/appgen/spec" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json"
```

### Get repo manifest (S2S)
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/deploy/repo/manifest" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"userId": "internal"}'
```

### Create pull request (S2S)
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/deploy/repo/pull-requests" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "internal",
    "baseCommitSha": "abc123...",
    "branchName": "mozaiksai/test-update",
    "title": "Test PR",
    "changes": [
      {
        "path": "MOZAIKS_TEST.txt",
        "operation": "add",
        "content": "Hello from MozaiksAI"
      }
    ]
  }'
```

### Generate templates (S2S)
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/deploy/templates/generate" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "internal",
    "techStack": {
      "frontend": { "framework": "react", "port": 3000 },
      "backend": { "framework": "fastapi", "port": 8000 }
    },
    "includeWorkflow": true,
    "includeDockerfiles": true
  }'
```

### Generate complete scaffold (S2S) ⭐ REPLACES FileManager
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/deploy/scaffold" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "internal",
    "dependencies": {
      "frontend": ["axios", "chart.js"],
      "backend": ["motor", "pydantic"]
    },
    "includeDockerfiles": true,
    "includeWorkflow": true,
    "includeBoilerplate": true,
    "includeInitFiles": true
  }'
```

### Get supported tech stacks
```bash
curl -X GET "http://localhost:8020/api/appgen/supported-stacks" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY"
```

### Provision database (S2S) ⭐ REPLACES DBManager
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/database/provision" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"userId": "mozaiksai"}'
```

### Apply database schema (S2S)
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/database/schema" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "mozaiksai",
    "schema": {
      "tables": [
        {
          "name": "users",
          "columns": [
            { "name": "email", "type": "string", "constraints": ["unique", "required"] },
            { "name": "name", "type": "string" }
          ],
          "indices": ["email"]
        }
      ]
    }
  }'
```

### Seed database (S2S)
```bash
curl -X POST "http://localhost:8020/api/apps/APP_ID_HERE/database/seed" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "mozaiksai",
    "seedData": {
      "users": [
        { "email": "admin@example.com", "name": "Admin User" }
      ]
    }
  }'
```

### Get database status
```bash
curl -X GET "http://localhost:8020/api/apps/APP_ID_HERE/database/status?userId=mozaiksai" \
  -H "X-Internal-Api-Key: YOUR_INTERNAL_API_KEY"
```

---

## Local dev configuration

### Required appsettings.Development.json
```json
{
  "MongoDB": {
    "ConnectionString": "mongodb://localhost:27017",
    "DatabaseName": "MozaiksDB"
  },
  "GitHub": {
    "AccessToken": "ghp_YOUR_GITHUB_PAT_HERE",
    "OrganizationName": ""
  },
  "Deployment": {
    "PlatformApiUrl": "http://localhost:8010",
    "InternalApiKey": "dev-internal-key-change-in-prod"
  },
  "DataProtection": {
    "KeysPath": "./keys"
  }
}
```

### Run locally
```powershell
cd src/Services/AuthServer/AuthServer.Api
dotnet run --launch-profile "http"
```

### Swagger UI
Open: `http://localhost:8020/swagger`

---

## Troubleshooting

### 401 Unauthorized on S2S calls
1. **Check `X-Internal-Api-Key` header is present**
2. **Check `Deployment:InternalApiKey` is not `"replace_me"`**
3. **Check for whitespace** — keys are trimmed, but verify no encoding issues
4. **Check logs** for `AppGen.*.Requested` events with `internalCall: true/false`

### 403 Forbidden
- User JWT is valid but user is not the app owner
- For S2S calls, this shouldn't happen (internal calls bypass ownership check)

### 500 Internal Server Error on repo operations
1. **Check `GitHub:AccessToken`** is valid and not expired
2. **Check repo exists** and token has access
3. **Check logs** for `Deploy.Repo.*.Failed` events

### Data Protection key errors
- Error: "The key ring does not contain a valid default protection key"
- Fix: Ensure `DataProtection:KeysPath` is configured and persisted across restarts
- Production: Mount a shared volume or use Azure Blob Storage

### Template generation returns empty files
1. **Check `techStack`** is provided in request
2. **Check `includeWorkflow`/`includeDockerfiles`** are true
3. **Check logs** for `AppGen.Templates.Failed` events

### GitHub rate limiting
- Error: "API rate limit exceeded"
- Fix: Use a GitHub token with higher rate limits (5000 req/hour for authenticated)
- Consider caching manifests if polling frequently

---

## Related Files

- **Controller**: `src/Services/AuthServer/AuthServer.Api/Controllers/AppGenController.cs`
- **Repo Export Controller**: `src/Services/AuthServer/AuthServer.Api/Controllers/AppRepoExportController.cs`
- **Database Provisioning Controller**: `src/Services/AuthServer/AuthServer.Api/Controllers/DatabaseProvisioningController.cs` ⭐ DBManager migration
- **Scaffold Service**: `src/Services/AuthServer/AuthServer.Api/Services/ScaffoldService.cs` ⭐ FileManager migration
- **Scaffold DTOs**: `src/Services/AuthServer/AuthServer.Api/DTOs/ScaffoldDtos.cs`
- **Database Provisioning Service**: `src/Services/AuthServer/AuthServer.Api/Services/DatabaseProvisioningService.cs`
- **Database Provisioning DTOs**: `src/Services/AuthServer/AuthServer.Api/DTOs/DatabaseProvisioningDtos.cs`
- **Template Service**: `src/Services/AuthServer/AuthServer.Api/Services/DeploymentTemplateService.cs`
- **GitHub Service**: `src/Services/AuthServer/AuthServer.Api/Services/GitHubRepoExportService.cs`
- **AppGen DTOs**: `src/Services/AuthServer/AuthServer.Api/DTOs/AppGenDtos.cs`
- **Smoke Script**: `scripts/smoke_mozaiks_tool_api.ps1`

---

## FileManager Migration Summary

The `/deploy/scaffold` endpoint replaces these FileManager responsibilities:

| FileManager (project-aid-v2) | ScaffoldService (backend) |
|------------------------------|---------------------------|
| Create `public/`, `src/` for React | Included in boilerplate files |
| Generate `index.html` with env.js reference | `react_index_html` template |
| Generate `env.js` placeholder | `react_env_js` template |
| Generate `nginx.conf` for SPA | `nginx_spa_conf` template |
| Generate `entrypoint.sh` | `entrypoint_sh` template |
| Create `__init__.py` for Python | `includeInitFiles: true` |
| Merge dependencies + base packages | Automatic in scaffold |
| Filter Python builtins | `PythonBuiltins` HashSet |
| Handle bson/pymongo conflict | `KnownConflicts` dict |
| Generate Dockerfiles | Delegates to `DeploymentTemplateService` |
| Generate workflows | Delegates to `DeploymentTemplateService` |

**MozaiksAI Usage**:
```python
# Instead of FileManager doing this locally:
# file_manager.write_agent_outputs(...)
# file_manager.generate_workflow_files()

# Call the backend:
scaffold = requests.post(
    f"{BACKEND_URL}/api/apps/{app_id}/deploy/scaffold",
    headers={"X-Internal-Api-Key": API_KEY},
    json={"userId": "mozaiksai", "dependencies": agent_deps}
).json()

# Then create PR with scaffold files + agent-generated code
all_files = scaffold["files"] + agent_code_files
requests.post(f"{BACKEND_URL}/api/apps/{app_id}/deploy/repo/pull-requests", ...)
```
