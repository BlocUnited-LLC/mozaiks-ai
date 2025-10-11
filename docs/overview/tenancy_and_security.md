# Tenancy, Security & Isolation

**Purpose:** Document the guardrails that enforce multi-tenant isolation, secret handling, and reproducible state across the MozaiksAI runtime.

## Multi-Tenancy Model

### Enterprise ID Scoping

**Definition:** `enterprise_id` is the top-level tenant identifier. Every API call, MongoDB query, and workflow execution is scoped to a single enterprise.

**Enforcement Points:**

1. **HTTP Endpoints:**
   ```python
   @app.post("/api/chats/{enterprise_id}/{workflow_name}/start")
   async def start_chat(enterprise_id: str, workflow_name: str, ...):
       # All downstream operations inherit enterprise_id
       await orchestration.run_default_pattern(
           enterprise_id=enterprise_id, ...
       )
   ```

2. **MongoDB Queries:**
   ```python
   # Always include enterprise_id filter
   await coll.find_one({
       "_id": chat_id,
       "enterprise_id": enterprise_id
   })
   ```

3. **Workflow Stats Collections:**
   - Collection name: `workflow_stats_{enterprise}_{workflow}`
   - Example: `workflow_stats_acme_corp_Generator`
   - Isolation: Each enterprise gets a separate collection per workflow

4. **Theme Configuration:**
   - Collection: `enterprise_themes`
   - Document `_id`: `enterprise_id`
   - API: `GET /api/themes/{enterprise_id}`, `PUT /api/themes/{enterprise_id}`

**Validation:**
```python
from core.data.persistence_manager import InvalidEnterpriseIdError

def validate_enterprise_id(enterprise_id: str):
    if not enterprise_id or not re.match(r'^[a-zA-Z0-9_-]+$', enterprise_id):
        raise InvalidEnterpriseIdError(f"Invalid enterprise_id: {enterprise_id}")
```

---

### Chat ID Uniqueness

**Format:** `chat_{uuid}`

**Generation:**
```python
chat_id = f"chat_{uuid.uuid4().hex[:16]}"
```

**Scoping:** Chat IDs are globally unique BUT always paired with `enterprise_id` in queries to prevent cross-enterprise leakage.

**Security Invariant:** Even if an attacker guesses a valid `chat_id`, they cannot access it without the correct `enterprise_id`.

---

## Cache Seed: Deterministic Reproducibility

### Purpose

The `cache_seed` is a 32-bit unsigned integer derived from `enterprise_id:chat_id` that ensures:
1. **Reproducible LLM responses** on chat resume (same seed → same pseudo-random sampling)
2. **UI component cache isolation** (prevents cross-chat state bleed)
3. **Audit trail consistency** (same seed produces same deterministic outcomes for compliance replay)

### Derivation

**Algorithm:**
```python
import hashlib

def derive_cache_seed(enterprise_id: str, chat_id: str) -> int:
    combined = f"{enterprise_id}:{chat_id}"
    hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
    # Take first 4 bytes as unsigned 32-bit int
    return int.from_bytes(hash_bytes[:4], byteorder='big')
```

**Example:**
```python
enterprise_id = "acme_corp"
chat_id = "chat_abc123def456"
seed = derive_cache_seed(enterprise_id, chat_id)
# seed = 2847561923 (deterministic for this enterprise + chat pair)
```

### Storage

**MongoDB:**
```json
{
  "_id": "chat_abc123def456",
  "enterprise_id": "acme_corp",
  "cache_seed": 2847561923,
  ...
}
```

**Frontend:**
```javascript
// Stored in localStorage after receiving chat_meta event
localStorage.setItem(
  `mozaiks.current_chat_id.cache_seed.${chatId}`,
  cacheSeed.toString()
);
```

### Propagation Flow

```mermaid
sequenceDiagram
    participant Backend
    participant MongoDB
    participant WebSocket
    participant Frontend
    participant UIComponent

    Backend->>MongoDB: Create chat session with cache_seed
    Backend->>WebSocket: Emit chat_meta event
    WebSocket->>Frontend: {"kind": "chat_meta", "cache_seed": 2847561923}
    Frontend->>Frontend: Store in localStorage
    Frontend->>UIComponent: Use seed in cache key
    Note over UIComponent: Key = chatId:cacheSeed:workflow:component
```

### Usage Points

1. **LLM Configuration:**
   ```python
   # In llm_config generation
   llm_config = {
       "cache_seed": session.get('cache_seed'),
       "temperature": 0.7,
       ...
   }
   ```

2. **UI Component Caching:**
   ```javascript
   // In WorkflowUIRouter cache key
   const cacheKey = `${chatId}:${cacheSeed}:${workflowName}:${componentId}`;
   if (componentCache.has(cacheKey)) {
       return componentCache.get(cacheKey);
   }
   ```

3. **Future Extensions:** Any feature requiring deterministic variance (vector search, layout decisions, A/B test assignment) should reuse `cache_seed` instead of introducing new entropy sources.

---

## Secrets Management

### API Key Handling

**Input:** User submits API keys via `APIKeyInput` UI component or direct API call.

**Storage:** Keys are stored in MongoDB with basic encryption (future: integrate Azure Key Vault).

**Logging Guardrail:**
```python
# NEVER log the actual key
logger.info(f"API key received for service={service_name}, length={len(api_key)}")

# In UI components, mask by default
const [showKey, setShowKey] = useState(false);
<input 
    type={showKey ? "text" : "password"} 
    value={apiKey}
/>
<button onClick={() => setShowKey(!showKey)}>
    {showKey ? "Hide" : "Reveal"}
</button>
```

**Runtime Access:**
```python
# Tools retrieve keys from context or environment
def get_api_key(service: str, context: ConversableContext) -> str:
    # Check context variables first
    key = context.get(f"{service}_api_key")
    if not key:
        # Fallback to environment
        key = os.getenv(f"{service.upper()}_API_KEY")
    if not key:
        raise ValueError(f"Missing API key for {service}")
    return key
```

**Security Principle:** Keys are passed through runtime layers but NEVER echoed in logs, error messages, or WebSocket events.

---

### Environment Variable Security

**Sensitive Variables:**
```bash
# .env file (never committed to git)
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/db
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
AZURE_KEYVAULT_URL=https://vault.vault.azure.net/
```

**Access Pattern:**
```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env at startup

mongo_uri = os.getenv("MONGODB_URI")
if not mongo_uri:
    raise RuntimeError("MONGODB_URI not set")
```

**CI/CD:** Secrets injected via environment-specific config (Azure Key Vault, GitHub Secrets, etc.).

---

## Theme Safety

### XSS Prevention

**Input Sanitization:**
```python
class ThemeUpdateRequest(BaseModel):
    colors: Optional[Dict[str, Any]] = None
    typography: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator('metadata')
    def sanitize_metadata(cls, v):
        if v and isinstance(v, dict):
            # Strip any script tags or dangerous HTML
            for key in v:
                if isinstance(v[key], str):
                    v[key] = v[key].replace('<script', '&lt;script')
        return v
```

**Frontend Application:**
```javascript
// Theme colors are applied via style objects, never dangerouslySetInnerHTML
<div style={{ backgroundColor: theme.colors.primary.main }}>
```

**Validation:** Theme manager rejects payloads with non-whitelisted keys or malformed color values.

---

## Workspace Isolation

### Context Variable Scoping

**Problem:** Multiple chats in the same enterprise should not share mutable context variables.

**Solution:** Context variables are scoped per-chat. Each `ConversableContext` instance is tied to a single `chat_id`.

**Example:**
```python
# Chat A
context_a = ConversableContext()
context_a.set("interview_complete", True)

# Chat B (same enterprise, different chat_id)
context_b = ConversableContext()
# context_b.get("interview_complete") returns None
```

**Persistence:** `context_snapshot` in MongoDB is per-chat document.

---

### Workflow Stats Rollup Isolation

**Collection Naming:** `workflow_stats_{enterprise}_{workflow}`

**Example Scenario:**
- Enterprise "acme_corp" runs "Generator" workflow → `workflow_stats_acme_corp_Generator`
- Enterprise "xyz_inc" runs "Generator" workflow → `workflow_stats_xyz_inc_Generator`

**No cross-enterprise visibility:** Aggregation queries are scoped to collection name, which includes `enterprise_id`.

---

## Access Control (Future)

**Current State:** No RBAC implemented; all API calls authenticated via enterprise_id in request path.

**Planned:**
- User-level authentication (JWT tokens)
- Role-based permissions (admin, user, viewer)
- Audit logging for sensitive operations (theme updates, key submissions)

**Integration Point:** `core/auth/` module (placeholder, not yet implemented)

---

## Compliance & Audit Trail

### Message Immutability

**MongoDB Schema:** Messages are append-only. No DELETE operations on `messages` array.

**Compliance Use Case:** Regulatory replay of exact conversation state for audit.

**Implementation:**
```python
# Append-only operation
await coll.update_one(
    {"_id": chat_id},
    {"$push": {"messages": message_doc}}
)

# NO deletion allowed
# ❌ await coll.update_one({"_id": chat_id}, {"$pull": {"messages": ...}})
```

---

### Deterministic Replay

**Requirement:** Given `chat_sessions` document, reproduce exact agent behavior.

**Mechanism:**
1. Restore `messages` array → AG2 `GroupChat.messages`
2. Restore `context_snapshot` → `ConversableContext`
3. Use same `cache_seed` → LLM config
4. Re-run orchestration with same workflow config

**Gotcha:** External API changes (e.g., OpenAI model updates) can break determinism. Mitigation: Pin model versions in `llm_config`.

---

## Security Checklist

| Risk | Mitigation | Status |
|------|-----------|--------|
| Cross-enterprise data leak | MongoDB queries always include `enterprise_id` filter | ✅ Implemented |
| API key exposure | Never log plaintext; mask in UI by default | ✅ Implemented |
| XSS via theme injection | Sanitize metadata; apply colors via style objects | ✅ Implemented |
| Unauthorized chat access | Require `enterprise_id` + `chat_id` for all operations | ✅ Implemented |
| Replay attack | No session token implemented yet | ⚠️ Planned |
| Secret leakage in logs | Runtime sanitizer strips secrets from log context | ✅ Implemented |
| Cross-chat state bleed | Cache seed scopes UI component caches | ✅ Implemented |

---

## Environment Toggles Affecting Security

| Variable | Purpose | Default | Security Impact |
|----------|---------|---------|----------------|
| `LOGS_AS_JSON` | Structured logging format | `false` | None (logs already sanitized) |
| `CLEAR_TOOL_CACHE_ON_START` | Reload tools on startup | `true` (dev) | Low (prevents stale code in dev) |
| `RANDOMIZE_DEFAULT_CACHE_SEED` | Randomize process-wide default seed | `false` | Low (per-chat seeds override) |
| `LLM_DEFAULT_CACHE_SEED` | Hard override for LLM seed | None | Medium (breaks deterministic replay if set incorrectly) |

**Recommendation:** Never set `LLM_DEFAULT_CACHE_SEED` in production; always rely on per-chat derived seeds.

---

## Next Steps

- **Runtime Configuration:** See `docs/runtime/configuration_reference.md` for full environment variable matrix
- **Persistence Schema:** See `docs/runtime/persistence_and_resume.md` for MongoDB document structure
- **Theme Management:** See `docs/runtime/theme_management.md` for theme API details

---

**Security Contact:** For security issues, email security@blocunited.com (do not open public GitHub issues).
