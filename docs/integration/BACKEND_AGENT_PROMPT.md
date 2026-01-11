# Backend Agent Prompt — MozaiksAI Integration

**Role**: You build the session broker that connects your app's users to MozaiksAI.

**Your Job**: Validate users, create sessions, provide WebSocket URLs. That's it.

---

## 1. Architecture

```
Frontend ──► Your Backend (Session Broker) ──► MozaiksAI Runtime
                    │
                    ├── Validates user auth
                    ├── Creates MozaiksAI sessions
                    └── Returns WebSocket URL to frontend
```

---

## 2. Session Broker Implementation

### Service Class

```csharp
public class MozaiksSessionBroker
{
    private readonly HttpClient _client;
    private readonly MozaiksConfig _config;
    
    public MozaiksSessionBroker(HttpClient client, IOptions<MozaiksConfig> config)
    {
        _client = client;
        _client.BaseAddress = new Uri(config.Value.ApiUrl);
        _config = config.Value;
    }
    
    /// <summary>
    /// Create a new workflow session for an authenticated user.
    /// </summary>
    public async Task<SessionResult> CreateSessionAsync(
        string userId,
        string workflowName,
        Dictionary<string, object>? backendContext = null)
    {
        var response = await _client.PostAsJsonAsync("/api/chat/start", new
        {
            app_id = _config.AppId,
            user_id = userId,
            workflow_name = workflowName,
            initial_context = backendContext
        });
        
        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<CreateSessionResponse>();
        
        return new SessionResult
        {
            ChatId = result.ChatId,
            WebSocketUrl = $"{_config.WsUrl}/ws/{workflowName}/{_config.AppId}/{result.ChatId}/{userId}"
        };
    }
    
    /// <summary>
    /// Get all active sessions for a user.
    /// </summary>
    public async Task<List<ChatSession>> GetUserSessionsAsync(string userId)
    {
        var response = await _client.GetAsync($"/api/sessions/{_config.AppId}/{userId}");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<List<ChatSession>>();
    }
    
    /// <summary>
    /// Get the most recently updated in-progress session (for "resume workflow" scenarios).
    /// </summary>
    public async Task<MostRecentSessionResponse?> GetMostRecentActiveSessionAsync(string userId)
    {
        var response = await _client.GetAsync($"/api/sessions/recent/{_config.AppId}/{userId}");
        if (!response.IsSuccessStatusCode) return null;
        
        return await response.Content.ReadFromJsonAsync<MostRecentSessionResponse>();
    }
}
```

### API Controller

```csharp
[ApiController]
[Route("api/mozaiks")]
[Authorize]  // Your auth middleware
public class MozaiksController : ControllerBase
{
    private readonly MozaiksSessionBroker _broker;
    
    public MozaiksController(MozaiksSessionBroker broker)
    {
        _broker = broker;
    }
    
    /// <summary>
    /// Frontend calls this to get a chat session.
    /// </summary>
    [HttpPost("session")]
    public async Task<IActionResult> CreateSession([FromBody] CreateSessionRequest req)
    {
        var userId = User.GetUserId();  // From your auth
        
        // Inject backend-only context (user tier, permissions, etc.)
        var backendContext = new Dictionary<string, object>
        {
            ["user_tier"] = User.GetClaim("tier"),
            ["user_permissions"] = User.GetPermissions()
        };
        
        var result = await _broker.CreateSessionAsync(
            userId,
            req.WorkflowName,
            backendContext
        );
        
        return Ok(result);
    }
    
    /// <summary>
    /// Frontend calls this to list existing sessions.
    /// </summary>
    [HttpGet("sessions")]
    public async Task<IActionResult> GetSessions()
    {
        var userId = User.GetUserId();
        var sessions = await _broker.GetUserSessionsAsync(userId);
        return Ok(sessions);
    }
}
```

### Configuration

```csharp
public class MozaiksConfig
{
    public string ApiUrl { get; set; }   // http://mozaiks-runtime:8000
    public string WsUrl { get; set; }    // ws://mozaiks-runtime:8000
    public string AppId { get; set; }    // Your registered app ID
}
```

### Dependency Injection Setup

```csharp
// In Program.cs or Startup.cs
services.Configure<MozaiksConfig>(configuration.GetSection("Mozaiks"));
services.AddHttpClient<MozaiksSessionBroker>();
```

---

## 3. Backend Context Injection

When creating sessions, inject data the frontend shouldn't have:

```csharp
var backendContext = new Dictionary<string, object>
{
    // User info agents might need
    ["user_tier"] = user.SubscriptionTier,        // "free", "pro", "enterprise"
    ["user_permissions"] = user.Permissions,       // ["read", "write", "admin"]
    
    // Business data for personalization
    ["account_age_days"] = (DateTime.UtcNow - user.CreatedAt).Days,
    ["support_priority"] = CalculatePriority(user),
    
    // Internal IDs (not exposed to frontend)
    ["internal_customer_id"] = user.InternalId
};
```

Agents receive this as context variables (no `ui_` prefix since it's from backend).

---

## 4. Request/Response Models

```csharp
// Request from frontend
public class CreateSessionRequest
{
    public string WorkflowName { get; set; }
}

// Response to frontend
public class SessionResult
{
    public string ChatId { get; set; }
    public string WebSocketUrl { get; set; }
}

// From MozaiksAI API
public class CreateSessionResponse
{
    [JsonPropertyName("chat_id")]
    public string ChatId { get; set; }
    
    [JsonPropertyName("status")]
    public string Status { get; set; }
}

public class ChatSession
{
    [JsonPropertyName("chat_id")]
    public string ChatId { get; set; }
    
    [JsonPropertyName("workflow_name")]
    public string WorkflowName { get; set; }
    
    [JsonPropertyName("status")]
    public string Status { get; set; }
    
    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

public class MostRecentSessionResponse
{
    [JsonPropertyName("found")]
    public bool Found { get; set; }

    [JsonPropertyName("chat_id")]
    public string ChatId { get; set; }

    [JsonPropertyName("workflow_name")]
    public string WorkflowName { get; set; }
}
```

---

## 5. Error Handling

```csharp
public async Task<SessionResult> CreateSessionAsync(...)
{
    try
    {
        var response = await _client.PostAsJsonAsync("/api/chat/start", payload);
        
        if (!response.IsSuccessStatusCode)
        {
            var error = await response.Content.ReadAsStringAsync();
            _logger.LogError("MozaiksAI session creation failed: {Error}", error);
            throw new MozaiksException($"Failed to create session: {response.StatusCode}");
        }
        
        // ... success path
    }
    catch (HttpRequestException ex)
    {
        _logger.LogError(ex, "MozaiksAI connection failed");
        throw new MozaiksException("AI service unavailable", ex);
    }
}
```

---

## 6. Health Check

```csharp
// Add to health checks
services.AddHealthChecks()
    .AddUrlGroup(
        new Uri($"{mozaiksConfig.ApiUrl}/health"),
        name: "mozaiks-runtime",
        failureStatus: HealthStatus.Degraded
    );
```

---

## 7. Environment Variables

```bash
Mozaiks__ApiUrl=http://mozaiks-runtime:8000
Mozaiks__WsUrl=ws://mozaiks-runtime:8000
Mozaiks__AppId=your-app-id
```

---

## 8. Checklist

- [ ] `MozaiksSessionBroker` service implemented
- [ ] `POST /api/mozaiks/session` endpoint works
- [ ] `GET /api/mozaiks/sessions` endpoint works
- [ ] Backend context injection includes user tier/permissions
- [ ] Health check configured
- [ ] Error logging in place

---

## 9. What You Don't Do

- Don't implement WebSocket proxying (frontend connects directly)
- Don't store chat messages (MozaiksAI handles persistence)
- Don't implement workflow logic (that's in MozaiksAI workflows)
- Don't manage MongoDB (Database Agent handles that)
- Don't configure infrastructure (Deployment Agent handles that)

Your job is just: **validate user, create session, return WebSocket URL**.
