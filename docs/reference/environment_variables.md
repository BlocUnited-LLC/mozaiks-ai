# Environment Variables Reference

**Document Type:** Reference  
**Last Updated:** October 2025  
**Intended Audience:** DevOps engineers, platform administrators, developers

---

## Purpose

This document provides a comprehensive reference for all environment variables used by the MozaiksAI runtime. These variables control database connections, API credentials, logging behavior, caching strategies, feature toggles, and operational parameters.

---

## Table of Contents

1. [Quick Reference Table](#quick-reference-table)
2. [Core Infrastructure](#core-infrastructure)
3. [Logging & Observability](#logging--observability)
4. [LLM Configuration](#llm-configuration)
5. [Caching & Performance](#caching--performance)
6. [Feature Toggles](#feature-toggles)
7. [Azure Key Vault](#azure-key-vault)
8. [Context Variables](#context-variables)
9. [Development & Debugging](#development--debugging)
10. [Configuration Profiles](#configuration-profiles)
11. [Validation & Defaults](#validation--defaults)
12. [Secret Management Best Practices](#secret-management-best-practices)

---

## Quick Reference Table

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| **Core Infrastructure** |
| `ENVIRONMENT` | string | `"development"` | No | Runtime environment: `development`, `staging`, `production` |
| `MONGO_URI` | string | None | **Yes** | MongoDB connection string (e.g., `mongodb://localhost:27017` or `mongodb+srv://...`) |
| `OPENAI_API_KEY` | string | None | **Yes** | OpenAI API key (format: `sk-proj-...`) |
| `DOCKERIZED` | boolean | `false` | No | Whether running in Docker container |
| **Logging** |
| `LOG_LEVEL` | string | `"INFO"` | No | Global log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOGS_BASE_DIR` | string | `"./logs"` | No | Base directory for log files |
| `LOGS_AS_JSON` | boolean | `false` | No | Enable JSON-formatted structured logs |
| `AG2_RUNTIME_LOGGING` | string | `"file"` | No | AG2 runtime logger type: `file`, `sqlite`, `disabled` |
| `AG2_RUNTIME_LOG_FILE` | string | `"runtime.log"` | No | Path to AG2 runtime log file |
| `AG2_RUNTIME_SQLITE_PATH` | string | `"ag2_runtime.db"` | No | Path to SQLite database for AG2 logger |
| `NO_COLOR` | boolean | `false` | No | Disable colored console output |
| `CLEAR_LOGS_ON_START` | boolean | `false` | No | Clear log files on server startup |
| **LLM Configuration** |
| `LLM_CONFIG_CACHE_TTL` | int | `300` | No | LLM config cache TTL in seconds (0 = disabled) |
| `LLM_DEFAULT_CACHE_SEED` | int | Random | No | Override default cache seed (deterministic caching) |
| `RANDOMIZE_DEFAULT_CACHE_SEED` | boolean | `false` | No | Use random cache seed on each startup |
| `DEFAULT_LLM_MODEL` | string | `"gpt-4o-mini"` | No | Fallback LLM model when not specified in workflow |
| `OPENAI_MODEL_FALLBACK` | string | None | No | Comma-separated fallback models (e.g., `"gpt-4o,gpt-4"`) |
| **Caching** |
| `CLEAR_TOOL_CACHE_ON_START` | boolean | `true` (dev)<br>`false` (prod) | No | Clear workflow tool cache on startup |
| `CLEAR_LLM_CACHES_ON_START` | boolean | `false` | No | Clear LLM config caches on startup |
| **Feature Toggles** |
| `FREE_TRIAL_ENABLED` | boolean | `true` | No | Enable free trial mode (skip token debits) |
| `CHAT_START_IDEMPOTENCY_SEC` | int | `15` | No | Idempotency window for duplicate `/api/start` requests |
| `ENABLE_MANUAL_INITIAL_PERSIST` | boolean | `false` | No | Enable manual initial message persistence (debug) |
| **Azure Key Vault** |
| `AZURE_KEY_VAULT_NAME` | string | None | No | Azure Key Vault name (e.g., `my-vault`) |
| `AZURE_TENANT_ID` | string | None | No | Azure AD tenant ID for authentication |
| `AZURE_CLIENT_ID` | string | None | No | Azure AD application (client) ID |
| `AZURE_CLIENT_SECRET` | string | None | No | Azure AD client secret |
| **Context Variables** |
| `CONTEXT_SCHEMA_TRUNCATE_CHARS` | int | `4000` | No | Max characters for context schema truncation |
| `CONTEXT_INCLUDE_SCHEMA` | boolean | `false` | No | Include database schema in context variables |
| `CONTEXT_SCHEMA_DB` | string | None | No | Database name for schema extraction |
| `CONTEXT_VERBOSE_DEBUG` | boolean | `false` | No | Enable verbose context variable debugging |

**Note:** Aliases for `MONGO_URI`: `MONGODB_URI`, `MONGO_URL` (all resolve to same connection string)

---

## Core Infrastructure

### ENVIRONMENT

**Type:** String  
**Default:** `"development"`  
**Values:** `development`, `staging`, `production`  
**Description:** Controls runtime behavior, logging verbosity, and default cache settings.

**Effects:**
- **Development:** Colored logs, verbose output, tool cache cleared on startup
- **Production:** JSON logs, minimal verbosity, tool cache preserved, structured logging

**Example:**
```bash
# Development (local)
export ENVIRONMENT=development

# Production (deployed)
export ENVIRONMENT=production
```

**Code Reference:**
```python
# shared_app.py
env = os.getenv("ENVIRONMENT", "development").lower()
if env == "production":
    setup_production_logging()
else:
    setup_development_logging()
```

---

### MONGO_URI

**Type:** String (Connection String)  
**Default:** None  
**Required:** **Yes**  
**Description:** MongoDB connection string for MozaiksAI and MozaiksDB databases.

**Formats:**
```bash
# Local MongoDB
MONGO_URI=mongodb://localhost:27017

# MongoDB with authentication
MONGO_URI=mongodb://username:password@localhost:27017

# MongoDB Atlas (cloud)
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority

# MongoDB with options
MONGO_URI=mongodb://localhost:27017/?maxPoolSize=50&minPoolSize=10
```

**Validation:**
- Must start with `mongodb://` or `mongodb+srv://`
- Credentials should be URL-encoded if they contain special characters
- Connection string should include authentication database if auth is enabled

**Fallback Order:**
1. `MONGO_URI` environment variable
2. `MONGODB_URI` environment variable (alias)
3. `MONGO_URL` environment variable (alias)
4. Azure Key Vault secret `MongoURI` (if Key Vault configured)

**Errors:**
```
ValueError: MONGO_URI is not configured
```
→ Set `MONGO_URI` in environment or configure Azure Key Vault

**Code Reference:**
```python
# core/core_config.py
conn_str = os.getenv("MONGO_URI")
if not conn_str:
    conn_str = get_secret("MongoURI")  # Key Vault fallback
if not conn_str:
    raise ValueError("MONGO_URI is not configured")
```

---

### OPENAI_API_KEY

**Type:** String (API Key)  
**Default:** None  
**Required:** **Yes**  
**Description:** OpenAI API key for LLM requests (GPT models).

**Format:**
```bash
OPENAI_API_KEY=sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789
```

**Validation:**
- Must start with `sk-` (standard keys) or `sk-proj-` (project keys)
- Minimum length: 48 characters
- Should be kept secret (never commit to version control)

**Fallback Order:**
1. `OPENAI_API_KEY` environment variable
2. Azure Key Vault secret `OpenAIApiKey` (if Key Vault configured)

**Errors:**
```
openai.AuthenticationError: Incorrect API key provided
```
→ Verify API key format and validity on OpenAI platform

**Code Reference:**
```python
# core/workflow/llm_config.py
api_key = p.get("api_key") or p.get("ApiKey") or p.get("OPENAI_API_KEY")
if not api_key:
    api_key = get_secret("OpenAIApiKey") if get_secret else os.getenv("OPENAI_API_KEY", "")
```

---

### DOCKERIZED

**Type:** Boolean  
**Default:** `false`  
**Description:** Indicates whether the runtime is running in a Docker container. Used for path resolution and service discovery.

**Example:**
```bash
# In docker-compose.yml
environment:
  DOCKERIZED: "true"
```

**Effects:**
- May adjust log file paths to use Docker volumes
- May affect service name resolution (e.g., `mongodb` vs `localhost`)

---

## Logging & Observability

### LOG_LEVEL

**Type:** String (Enum)  
**Default:** `"INFO"`  
**Values:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`  
**Description:** Global logging threshold for all loggers.

**Example:**
```bash
# Development: verbose debugging
export LOG_LEVEL=DEBUG

# Production: errors and warnings only
export LOG_LEVEL=WARNING
```

**Effects:**
- `DEBUG`: All messages (including verbose AG2 internal logs)
- `INFO`: Informational messages, agent turns, tool calls
- `WARNING`: Warnings and errors only
- `ERROR`: Errors and critical issues only
- `CRITICAL`: Only critical failures

**Performance Impact:**
- `DEBUG` can generate 10-20x more log volume than `INFO`
- Recommend `INFO` for production, `DEBUG` for troubleshooting

---

### LOGS_BASE_DIR

**Type:** String (Path)  
**Default:** `"./logs"`  
**Description:** Base directory for log file storage.

**Example:**
```bash
# Custom log directory
export LOGS_BASE_DIR=/var/log/mozaiksai

# Docker volume mount
export LOGS_BASE_DIR=/app/logs
```

**Log Files Created:**
- `workflow_execution.log` - Workflow orchestration logs
- `performance.log` - Performance metrics and timing
- `tools.log` - Tool execution logs
- `autogen_file.log` - AG2 internal event logs (if AG2_RUNTIME_LOGGING=file)

**Permissions:**
- Directory must be writable by application user
- Recommend `chmod 755` for directory, `644` for log files

---

### LOGS_AS_JSON

**Type:** Boolean  
**Default:** `false`  
**Description:** Enable JSON-formatted structured logs for machine parsing (recommended for production).

**Example:**
```bash
# Production: JSON logs for ELK/Datadog
export LOGS_AS_JSON=true

# Development: human-readable logs
export LOGS_AS_JSON=false
```

**JSON Format:**
```json
{
  "timestamp": "2025-10-02T14:30:15.123Z",
  "level": "INFO",
  "logger": "workflow_execution",
  "message": "Agent turn completed",
  "chat_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "507f1f77bcf86cd799439011",
  "agent_name": "ArchitectAgent",
  "duration_ms": 1234
}
```

**Benefits:**
- Easy parsing with `jq`, Filebeat, Logstash
- Structured querying in Elasticsearch/Splunk
- Automatic field extraction

---

### AG2_RUNTIME_LOGGING

**Type:** String (Enum)  
**Default:** `"file"`  
**Values:** `file`, `sqlite`, `disabled`  
**Description:** AG2 internal event logging strategy.

**Options:**

**`file` (Default):**
- Logs AG2 events to `autogen_file.log`
- Human-readable format
- Supports log rotation with `logrotate`

**`sqlite`:**
- Logs AG2 events to SQLite database
- Queryable with SQL
- Better for structured analysis
- Path: `AG2_RUNTIME_SQLITE_PATH`

**`disabled`:**
- No AG2 internal logging
- Reduces disk I/O
- Not recommended (loses AG2 event trail)

**Example:**
```bash
# Production: SQLite for structured queries
export AG2_RUNTIME_LOGGING=sqlite
export AG2_RUNTIME_SQLITE_PATH=/var/lib/mozaiksai/ag2.db

# Development: file for human reading
export AG2_RUNTIME_LOGGING=file
```

**Code Reference:**
```python
# core/observability/ag2_runtime_logger.py
mode = os.getenv("AG2_RUNTIME_LOGGING", "file").strip().lower()
```

---

### AG2_RUNTIME_LOG_FILE

**Type:** String (Path)  
**Default:** `"runtime.log"` (relative to LOGS_BASE_DIR)  
**Description:** Path to AG2 runtime log file when `AG2_RUNTIME_LOGGING=file`.

**Example:**
```bash
export AG2_RUNTIME_LOG_FILE=/var/log/mozaiksai/autogen_file.log
```

---

### AG2_RUNTIME_SQLITE_PATH

**Type:** String (Path)  
**Default:** `"ag2_runtime.db"`  
**Description:** Path to SQLite database when `AG2_RUNTIME_LOGGING=sqlite`.

**Example:**
```bash
export AG2_RUNTIME_SQLITE_PATH=/var/lib/mozaiksai/ag2_events.db
```

**Querying:**
```bash
sqlite3 /var/lib/mozaiksai/ag2_events.db "SELECT * FROM events WHERE chat_id = '550e...' ORDER BY timestamp DESC LIMIT 10;"
```

---

### NO_COLOR

**Type:** Boolean  
**Default:** `false`  
**Description:** Disable colored console output (ANSI escape codes).

**Example:**
```bash
# CI/CD environments, non-TTY terminals
export NO_COLOR=1
```

**When to Enable:**
- CI/CD pipelines (Jenkins, GitHub Actions)
- Log aggregation systems that don't support ANSI colors
- Non-interactive terminals

---

### CLEAR_LOGS_ON_START

**Type:** Boolean  
**Default:** `false`  
**Description:** Clear all log files on server startup (useful for development).

**Example:**
```bash
# Development: fresh logs each run
export CLEAR_LOGS_ON_START=true

# Production: preserve logs
export CLEAR_LOGS_ON_START=false
```

**Warning:** Enabling in production causes log data loss. Use log rotation instead.

---

## LLM Configuration

### LLM_CONFIG_CACHE_TTL

**Type:** Integer (Seconds)  
**Default:** `300` (5 minutes)  
**Range:** `0` (disabled) to `3600` (1 hour)  
**Description:** Time-to-live for LLM configuration cache.

**Example:**
```bash
# Aggressive caching (cost optimization)
export LLM_CONFIG_CACHE_TTL=3600

# Disabled (always rebuild config)
export LLM_CONFIG_CACHE_TTL=0

# Default (5 minutes)
export LLM_CONFIG_CACHE_TTL=300
```

**Performance Impact:**
- `TTL=0`: Rebuilds config on every request (+10-20ms latency per agent turn)
- `TTL=300`: Balances cache freshness with performance
- `TTL=3600`: Maximum performance, minimal config reloading

**Cost Impact:**
- Higher TTL → More LLM response cache hits → 50-90% cost reduction
- Lower TTL → More cache misses → Higher API costs

**Code Reference:**
```python
# core/workflow/llm_config.py
_CACHE_TTL = int(os.getenv("LLM_CONFIG_CACHE_TTL", "300"))
```

---

### LLM_DEFAULT_CACHE_SEED

**Type:** Integer  
**Default:** Random (or deterministic from chat_id)  
**Description:** Override default cache seed for LLM response caching.

**Example:**
```bash
# Deterministic seed (reproducible responses)
export LLM_DEFAULT_CACHE_SEED=42

# Use per-chat deterministic seeds (default behavior)
# (no env var set, runtime derives from chat_id)
```

**Caching Strategy:**
- **Per-Chat Seeds (Default):** Each chat session gets deterministic seed from `chat_id` hash
- **Global Seed:** Set `LLM_DEFAULT_CACHE_SEED` for cross-chat caching (not recommended)
- **Random Seed:** Set `RANDOMIZE_DEFAULT_CACHE_SEED=true` for no caching

**Cost Optimization:**
- Per-chat deterministic seeds: 50-70% cache hit rate (best for multi-turn conversations)
- Global seed: 80-90% cache hit rate (best for repetitive queries, but loses per-chat context)

---

### RANDOMIZE_DEFAULT_CACHE_SEED

**Type:** Boolean  
**Default:** `false`  
**Description:** Use random cache seed on each startup (disables LLM response caching).

**Example:**
```bash
# Disable caching (testing, non-deterministic responses)
export RANDOMIZE_DEFAULT_CACHE_SEED=true
```

**When to Enable:**
- Testing non-deterministic LLM behavior
- Benchmarking without cache effects
- Ensuring fresh responses (not recommended for production)

---

### DEFAULT_LLM_MODEL

**Type:** String (Model Name)  
**Default:** `"gpt-4o-mini"`  
**Description:** Fallback LLM model when not specified in workflow manifest.

**Example:**
```bash
# Use GPT-4 as default
export DEFAULT_LLM_MODEL=gpt-4

# Use GPT-4o-mini (cost-optimized)
export DEFAULT_LLM_MODEL=gpt-4o-mini

# Use GPT-4 Turbo
export DEFAULT_LLM_MODEL=gpt-4-turbo
```

**Model Cost Comparison (per 1M tokens):**
- `gpt-4o-mini`: $0.15 input / $0.60 output (cheapest)
- `gpt-4o`: $2.50 input / $10.00 output
- `gpt-4`: $30.00 input / $60.00 output (most capable)
- `gpt-4-turbo`: $10.00 input / $30.00 output

**Recommendation:** Use `gpt-4o-mini` for routing/orchestration, `gpt-4` for complex reasoning tasks.

---

### OPENAI_MODEL_FALLBACK

**Type:** String (Comma-Separated)  
**Default:** None (uses `DEFAULT_LLM_MODEL` as single fallback)  
**Description:** Comma-separated list of fallback models for retries.

**Example:**
```bash
# Try GPT-4, fall back to GPT-4o-mini
export OPENAI_MODEL_FALLBACK=gpt-4,gpt-4o-mini

# Multi-tier fallback
export OPENAI_MODEL_FALLBACK=gpt-4-turbo,gpt-4o,gpt-4o-mini
```

**Behavior:**
- On API error (rate limit, model unavailable), runtime retries with next model in list
- Useful for handling GPT-4 capacity issues

---

## Caching & Performance

### CLEAR_TOOL_CACHE_ON_START

**Type:** Boolean  
**Default:** `true` (development), `false` (production)  
**Description:** Clear Python module cache for workflow tools on server startup.

**Example:**
```bash
# Development: always reload tools (see code changes)
export CLEAR_TOOL_CACHE_ON_START=true

# Production: preserve tool cache (faster startup)
export CLEAR_TOOL_CACHE_ON_START=false
```

**Effects:**
- `true`: Tools reloaded from disk on every startup (adds ~500ms startup time)
- `false`: Tools cached in memory (faster startup, requires restart to see tool changes)

**Code Reference:**
```python
# shared_app.py
clear_tools = _env_bool("CLEAR_TOOL_CACHE_ON_START", default=(env != "production"))
if clear_tools:
    from core.workflow.agent_tools import clear_tool_cache
    cleared = clear_tool_cache()
```

---

### CLEAR_LLM_CACHES_ON_START

**Type:** Boolean  
**Default:** `false`  
**Description:** Clear LLM configuration caches on server startup.

**Example:**
```bash
# Force config rebuild (debug)
export CLEAR_LLM_CACHES_ON_START=true
```

**When to Enable:**
- After modifying workflow manifest LLM configs
- Testing with different model configurations
- Clearing stale cache after environment changes

---

## Feature Toggles

### FREE_TRIAL_ENABLED

**Type:** Boolean  
**Default:** `true`  
**Description:** Enable free trial mode (skip wallet token debits).

**Example:**
```bash
# Production: enforce token billing
export FREE_TRIAL_ENABLED=false

# Development: free trial mode
export FREE_TRIAL_ENABLED=true
```

**Effects:**
- `true`: Token usage tracked but not debited from wallets
- `false`: Token debits enforced, sessions pause on insufficient balance

**Code Reference:**
```python
# core/core_config.py
def get_free_trial_config() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("FREE_TRIAL_ENABLED", "true").lower() == "true"
    }

# In persistence_manager.py
cfg = get_free_trial_config()
if not cfg.get("enabled", False):
    await self.debit_tokens(user_id, app_id, total_tokens, reason="realtime_usage")
```

---

### CHAT_START_IDEMPOTENCY_SEC

**Type:** Integer (Seconds)  
**Default:** `15`  
**Range:** `5` to `60`  
**Description:** Idempotency window for duplicate `/api/start` requests (prevents double session creation).

**Example:**
```bash
# Strict idempotency (5 seconds)
export CHAT_START_IDEMPOTENCY_SEC=5

# Relaxed (30 seconds for slow networks)
export CHAT_START_IDEMPOTENCY_SEC=30
```

**Behavior:**
- If same `(app_id, user_id, workflow_name)` requested within window, returns existing `chat_id`
- Prevents race conditions from double-click or network retries

**Code Reference:**
```python
# shared_app.py
IDEMPOTENCY_WINDOW_SEC = int(os.getenv("CHAT_START_IDEMPOTENCY_SEC", "15"))
```

---

### ENABLE_MANUAL_INITIAL_PERSIST

**Type:** Boolean  
**Default:** `false`  
**Description:** Enable manual initial message persistence (debug flag for testing message flow).

**Example:**
```bash
# Enable for debugging message persistence
export ENABLE_MANUAL_INITIAL_PERSIST=true
```

**Warning:** Internal debug flag. Do not enable in production.

---

## Azure Key Vault

Azure Key Vault integration provides centralized secret management as a fallback when environment variables are not set.

### AZURE_KEY_VAULT_NAME

**Type:** String  
**Default:** None  
**Description:** Azure Key Vault name (not the full URI).

**Example:**
```bash
export AZURE_KEY_VAULT_NAME=mozaiksai-prod-kv
```

**Constructed URI:**
```
https://{AZURE_KEY_VAULT_NAME}.vault.azure.net/
```

**Secrets Retrieved:**
- `MongoURI` → `MONGO_URI`
- `OpenAIApiKey` → `OPENAI_API_KEY`

---

### AZURE_TENANT_ID

**Type:** String (UUID)  
**Default:** None  
**Description:** Azure AD tenant ID for authentication.

**Example:**
```bash
export AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**When Required:**
- Using Service Principal authentication (non-managed identity)
- Required alongside `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`

---

### AZURE_CLIENT_ID

**Type:** String (UUID)  
**Default:** None  
**Description:** Azure AD application (client) ID.

**Example:**
```bash
export AZURE_CLIENT_ID=yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
```

---

### AZURE_CLIENT_SECRET

**Type:** String  
**Default:** None  
**Description:** Azure AD client secret for Service Principal authentication.

**Example:**
```bash
export AZURE_CLIENT_SECRET=my-secret-value
```

**Security:**
- Keep secret secure (never commit to version control)
- Rotate regularly (recommend 90-day rotation)
- Use Managed Identity instead when possible (Azure VMs, App Service, AKS)

---

### Authentication Methods

**Preferred Order (DefaultAzureCredential):**
1. **Managed Identity** (Azure VM, App Service, AKS) - No credentials needed
2. **Azure CLI** (`az login`) - Local development
3. **Service Principal** (`AZURE_TENANT_ID` + `AZURE_CLIENT_ID` + `AZURE_CLIENT_SECRET`)

**Configuration Examples:**

**Managed Identity (Production):**
```bash
# No credentials needed; identity assigned to Azure resource
export AZURE_KEY_VAULT_NAME=mozaiksai-prod-kv
```

**Service Principal (CI/CD):**
```bash
export AZURE_KEY_VAULT_NAME=mozaiksai-prod-kv
export AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
export AZURE_CLIENT_ID=yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
export AZURE_CLIENT_SECRET=my-secret-value
```

**Local Development (Azure CLI):**
```bash
# Authenticate with Azure CLI
az login

# Set Key Vault name
export AZURE_KEY_VAULT_NAME=mozaiksai-dev-kv
```

---

## Context Variables

Context variables provide workflow agents with runtime data from databases, environment, or static configuration.

### CONTEXT_SCHEMA_TRUNCATE_CHARS

**Type:** Integer  
**Default:** `4000`  
**Range:** `1000` to `10000`  
**Description:** Maximum characters for database schema context truncation (prevents LLM context overflow).

**Example:**
```bash
# Larger schemas (more context)
export CONTEXT_SCHEMA_TRUNCATE_CHARS=8000

# Smaller schemas (conserve tokens)
export CONTEXT_SCHEMA_TRUNCATE_CHARS=2000
```

---

### CONTEXT_INCLUDE_SCHEMA

**Type:** Boolean  
**Default:** `false`  
**Description:** Include database schema in context variables for SQL generation workflows.

**Example:**
```bash
# Enable for SQL agent workflows
export CONTEXT_INCLUDE_SCHEMA=true
```

**Effects:**
- Adds database table/column metadata to agent context
- Useful for text-to-SQL agents
- Increases token usage by ~1000-4000 tokens per turn

---

### CONTEXT_SCHEMA_DB

**Type:** String (Database Name)  
**Default:** None  
**Description:** Database name for schema extraction when `CONTEXT_INCLUDE_SCHEMA=true`.

**Example:**
```bash
export CONTEXT_INCLUDE_SCHEMA=true
export CONTEXT_SCHEMA_DB=MozaiksAI
```

---

### CONTEXT_VERBOSE_DEBUG

**Type:** Boolean  
**Default:** `false`  
**Description:** Enable verbose debugging for context variable resolution.

**Example:**
```bash
# Debug context variable loading
export CONTEXT_VERBOSE_DEBUG=true
```

**Output:**
```
[CONTEXT] Loaded environment variable MONGO_URI: mongodb://...
[CONTEXT] Resolved database variable user_count: 1234
[CONTEXT] Derived variable formatted_date: 2025-10-02
```

---

## Development & Debugging

### Development-Specific Variables

```bash
# Enable all debug features
export ENVIRONMENT=development
export LOG_LEVEL=DEBUG
export LOGS_AS_JSON=false
export CLEAR_TOOL_CACHE_ON_START=true
export CLEAR_LLM_CACHES_ON_START=true
export CLEAR_LOGS_ON_START=true
export CONTEXT_VERBOSE_DEBUG=true
export AG2_RUNTIME_LOGGING=file
export FREE_TRIAL_ENABLED=true
```

### Debugging Specific Features

**LLM Cache Debugging:**
```bash
export LLM_CONFIG_CACHE_TTL=0  # Disable caching
export RANDOMIZE_DEFAULT_CACHE_SEED=true  # Force fresh responses
```

**Tool Loading Debugging:**
```bash
export CLEAR_TOOL_CACHE_ON_START=true
export LOG_LEVEL=DEBUG
# Check logs for: "TOOL_CACHE: Cleared X cached tool modules"
```

**Message Persistence Debugging:**
```bash
export ENABLE_MANUAL_INITIAL_PERSIST=true
export LOG_LEVEL=DEBUG
# Check logs for: "[INIT_MSG_PERSIST] Inserted initial message"
```

---

## Configuration Profiles

### Development Profile

**`.env.development`:**
```bash
ENVIRONMENT=development
MONGO_URI=mongodb://localhost:27017
OPENAI_API_KEY=sk-proj-your-dev-key

LOG_LEVEL=DEBUG
LOGS_AS_JSON=false
CLEAR_LOGS_ON_START=true

CLEAR_TOOL_CACHE_ON_START=true
CLEAR_LLM_CACHES_ON_START=true
LLM_CONFIG_CACHE_TTL=60

FREE_TRIAL_ENABLED=true
AG2_RUNTIME_LOGGING=file
```

**Characteristics:**
- Verbose logging for debugging
- Aggressive cache clearing for code changes
- Free trial mode enabled
- Human-readable logs

---

### Staging Profile

**`.env.staging`:**
```bash
ENVIRONMENT=staging
MONGO_URI=mongodb+srv://user:pass@staging-cluster.mongodb.net/?retryWrites=true&w=majority

# Retrieve from Azure Key Vault
AZURE_KEY_VAULT_NAME=mozaiksai-staging-kv

LOG_LEVEL=INFO
LOGS_AS_JSON=true

CLEAR_TOOL_CACHE_ON_START=false
CLEAR_LLM_CACHES_ON_START=false
LLM_CONFIG_CACHE_TTL=300

FREE_TRIAL_ENABLED=true
AG2_RUNTIME_LOGGING=sqlite
AG2_RUNTIME_SQLITE_PATH=/var/lib/mozaiksai/ag2_staging.db
```

**Characteristics:**
- Production-like logging (JSON)
- Cache preservation for performance testing
- Key Vault for secrets
- Free trial enabled for QA testing

---

### Production Profile

**`.env.production`:**
```bash
ENVIRONMENT=production

# Secrets managed via Azure Key Vault
AZURE_KEY_VAULT_NAME=mozaiksai-prod-kv
# MONGO_URI and OPENAI_API_KEY retrieved from Key Vault

LOG_LEVEL=WARNING
LOGS_AS_JSON=true
LOGS_BASE_DIR=/var/log/mozaiksai

CLEAR_TOOL_CACHE_ON_START=false
CLEAR_LLM_CACHES_ON_START=false
LLM_CONFIG_CACHE_TTL=600

FREE_TRIAL_ENABLED=false
CHAT_START_IDEMPOTENCY_SEC=15

AG2_RUNTIME_LOGGING=sqlite
AG2_RUNTIME_SQLITE_PATH=/var/lib/mozaiksai/ag2_prod.db

DEFAULT_LLM_MODEL=gpt-4o-mini
OPENAI_MODEL_FALLBACK=gpt-4o,gpt-4o-mini

NO_COLOR=true
```

**Characteristics:**
- Minimal logging (WARNING level)
- JSON structured logs for aggregation
- Key Vault for all secrets
- Token billing enforced
- Aggressive LLM caching for cost optimization
- Model fallback for reliability

---

## Validation & Defaults

### Boolean Parsing

**Truthy Values:** `"1"`, `"true"`, `"True"`, `"yes"`, `"on"`  
**Falsy Values:** `"0"`, `"false"`, `"False"`, `"no"`, `"off"`, `""` (empty string)

**Example:**
```python
def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off", ""):
        return False
    return default
```

---

### Integer Parsing

**Validation:**
```python
try:
    ttl = int(os.getenv("LLM_CONFIG_CACHE_TTL", "300"))
except ValueError:
    ttl = 300  # Use default on parse error
```

**Range Checking:**
```python
ttl = max(0, min(3600, ttl))  # Clamp to [0, 3600]
```

---

### Required Variables

**Startup Validation:**
```python
# shared_app.py startup
required_vars = ["MONGO_URI", "OPENAI_API_KEY"]
missing = [var for var in required_vars if not os.getenv(var) and not get_secret(var)]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
```

**Error Messages:**
```
ValueError: MONGO_URI is not configured
ValueError: Secret 'OpenAIApiKey' not found in environment or Key Vault
```

---

## Secret Management Best Practices

### 1. Never Commit Secrets to Version Control

**Use `.gitignore`:**
```
.env
.env.local
.env.*.local
*.key
*.pem
secrets/
```

**Example `.env` Template:**
```bash
# .env.example (commit this)
ENVIRONMENT=development
MONGO_URI=mongodb://localhost:27017
OPENAI_API_KEY=sk-proj-your-key-here

# .env (DO NOT commit)
ENVIRONMENT=development
MONGO_URI=mongodb://localhost:27017
OPENAI_API_KEY=sk-proj-ABC123...actual-key
```

---

### 2. Use Azure Key Vault in Production

**Benefits:**
- Centralized secret rotation
- Access audit logs
- RBAC (Role-Based Access Control)
- Automatic secret expiration

**Setup:**
```bash
# Create Key Vault
az keyvault create --name mozaiksai-prod-kv --resource-group mozaiksai-rg

# Add secrets
az keyvault secret set --vault-name mozaiksai-prod-kv --name MongoURI --value "mongodb+srv://..."
az keyvault secret set --vault-name mozaiksai-prod-kv --name OpenAIApiKey --value "sk-proj-..."

# Grant access to Managed Identity
az keyvault set-policy --name mozaiksai-prod-kv \
  --object-id <managed-identity-object-id> \
  --secret-permissions get list
```

---

### 3. Rotate Secrets Regularly

**Recommended Rotation Schedule:**
- `OPENAI_API_KEY`: 90 days
- `MONGO_URI` credentials: 90 days
- `AZURE_CLIENT_SECRET`: 90 days

**Rotation Process:**
1. Generate new secret in provider (OpenAI, Azure)
2. Update Key Vault or environment variable
3. Restart application (zero-downtime: blue-green deployment)
4. Revoke old secret after verification

---

### 4. Use Environment-Specific Secrets

**Development:**
```bash
# Local .env
OPENAI_API_KEY=sk-proj-dev-key-with-low-rate-limits
MONGO_URI=mongodb://localhost:27017
```

**Production:**
```bash
# Azure Key Vault
OPENAI_API_KEY=sk-proj-prod-key-with-high-rate-limits
MONGO_URI=mongodb+srv://prod-cluster.mongodb.net/
```

**Benefits:**
- Prevents accidental production data access in dev
- Different rate limits for dev vs prod
- Isolated failure domains

---

### 5. Audit Secret Access

**Enable Key Vault Diagnostics:**
```bash
az monitor diagnostic-settings create \
  --name kv-audit-logs \
  --resource /subscriptions/.../providers/Microsoft.KeyVault/vaults/mozaiksai-prod-kv \
  --logs '[{"category": "AuditEvent", "enabled": true}]' \
  --workspace /subscriptions/.../resourceGroups/.../providers/Microsoft.OperationalInsights/workspaces/...
```

**Query Logs:**
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where OperationName == "SecretGet"
| project TimeGenerated, CallerIPAddress, id_s, properties_s
| order by TimeGenerated desc
```

---

### 6. Least Privilege Access

**Key Vault Permissions:**
```bash
# Application only needs 'get' and 'list'
az keyvault set-policy --name mozaiksai-prod-kv \
  --object-id <app-identity-id> \
  --secret-permissions get list

# Deny 'set', 'delete' to application identity
```

---

### 7. Secret Redaction in Logs

**Automatic Redaction (Built-in):**
```python
# logs/logging_config.py
_AZURE_ACC_KEY_RE = re.compile(r"(AccountKey=)([^;]+)(;)", re.IGNORECASE)

def _redact_secrets(msg: str) -> str:
    msg = re.sub(r'(sk-[a-zA-Z0-9]{20,})', '***REDACTED_OPENAI_KEY***', msg)
    msg = _AZURE_ACC_KEY_RE.sub(lambda m: m.group(1) + "***REDACTED***" + m.group(3), msg)
    return msg
```

**Patterns Redacted:**
- OpenAI API keys: `sk-proj-...` → `***REDACTED_OPENAI_KEY***`
- Azure Storage Account Keys: `AccountKey=...;` → `AccountKey=***REDACTED***;`
- MongoDB connection strings with credentials (partial)

---

## Troubleshooting

### Issue: "MONGO_URI is not configured"

**Check:**
```bash
# Verify environment variable
echo $MONGO_URI

# Check .env file
cat .env | grep MONGO_URI

# Verify Key Vault configuration (if using)
az keyvault secret show --vault-name mozaiksai-prod-kv --name MongoURI
```

**Solution:**
```bash
export MONGO_URI=mongodb://localhost:27017
# Or add to .env file
```

---

### Issue: "Incorrect API key provided" (OpenAI)

**Check:**
```bash
# Verify API key format
echo $OPENAI_API_KEY | head -c 8
# Should output: sk-proj-

# Test API key with curl
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Solution:**
- Verify key on OpenAI platform (https://platform.openai.com/api-keys)
- Check for extra whitespace: `export OPENAI_API_KEY=$(echo $OPENAI_API_KEY | xargs)`
- Rotate key if compromised

---

### Issue: Logs not appearing

**Check:**
```bash
# Verify log directory exists and is writable
ls -la ./logs

# Check LOG_LEVEL
echo $LOG_LEVEL

# Check CLEAR_LOGS_ON_START (may be deleting logs)
echo $CLEAR_LOGS_ON_START
```

**Solution:**
```bash
# Create logs directory
mkdir -p ./logs
chmod 755 ./logs

# Set appropriate log level
export LOG_LEVEL=INFO

# Disable log clearing
export CLEAR_LOGS_ON_START=false
```

---

### Issue: Cache not working (high costs)

**Check:**
```bash
# Verify cache TTL
echo $LLM_CONFIG_CACHE_TTL

# Check if random seed enabled (disables caching)
echo $RANDOMIZE_DEFAULT_CACHE_SEED
```

**Solution:**
```bash
# Enable caching with 5-minute TTL
export LLM_CONFIG_CACHE_TTL=300

# Ensure deterministic seeds
unset RANDOMIZE_DEFAULT_CACHE_SEED
```

---

### Issue: Azure Key Vault authentication fails

**Check:**
```bash
# Verify Key Vault name
echo $AZURE_KEY_VAULT_NAME

# Test Azure CLI authentication
az account show

# Test Key Vault access
az keyvault secret list --vault-name $AZURE_KEY_VAULT_NAME
```

**Solution (Managed Identity):**
```bash
# Verify Managed Identity is assigned
az vm identity show --name my-vm --resource-group my-rg

# Grant Key Vault access to Managed Identity
az keyvault set-policy --name mozaiksai-prod-kv \
  --object-id <identity-object-id> \
  --secret-permissions get list
```

**Solution (Service Principal):**
```bash
# Verify all credentials are set
echo $AZURE_TENANT_ID
echo $AZURE_CLIENT_ID
echo $AZURE_CLIENT_SECRET

# Test authentication
az login --service-principal \
  -u $AZURE_CLIENT_ID \
  -p $AZURE_CLIENT_SECRET \
  --tenant $AZURE_TENANT_ID
```

---

## Related Documentation

- **[Configuration Reference](../runtime/configuration_reference.md):** Runtime configuration patterns and workflow manifest settings
- **[Deployment Guide](../operations/deployment.md):** Environment variable configuration in Docker Compose, systemd, and Kubernetes
- **[Troubleshooting](../operations/troubleshooting.md):** Common errors related to missing or invalid environment variables
- **[Performance Tuning](../operations/performance_tuning.md):** Cache optimization with `LLM_CONFIG_CACHE_TTL` and other performance variables
- **[Database Schema](./database_schema.md):** MongoDB connection string format and authentication
- **[Key Vault Integration](../docs/KEY_VAULT_INTEGRATION.md):** Detailed Azure Key Vault setup and usage

---

**End of Environment Variables Reference**

For questions or additional variables, consult the platform engineering team or review `core/core_config.py` and `shared_app.py` source code.
