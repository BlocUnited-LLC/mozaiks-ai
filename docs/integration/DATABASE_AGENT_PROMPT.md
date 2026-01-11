# Database Agent Prompt — MozaiksAI Integration

**Role**: You manage database schemas and data access for apps integrating MozaiksAI.

**Your Job**: Set up your app's session mapping table. MozaiksAI manages its own MongoDB — you don't touch that.

---

## 1. What MozaiksAI Owns (Don't Touch)

MozaiksAI Runtime uses its own MongoDB with these collections:

```
mozaiks_db/
├── chat_sessions      ← Session metadata
├── chat_messages      ← Message history  
├── context_variables  ← Workflow state
├── artifacts          ← Generated files
└── perf_metrics       ← Observability
```

**You do NOT create, migrate, or query these collections.** MozaiksAI manages them.

---

## 2. What You Create (Your App's Database)

Create ONE table in your app's database for session tracking:

### SQL Server / PostgreSQL

```sql
CREATE TABLE mozaiks_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    mozaiks_chat_id VARCHAR(255) NOT NULL,
    workflow_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB,
    
    CONSTRAINT uq_mozaiks_chat UNIQUE (mozaiks_chat_id)
);

-- Index for fast user lookups
CREATE INDEX idx_mozaiks_sessions_user_id ON mozaiks_sessions(user_id);

-- Index for finding active sessions
CREATE INDEX idx_mozaiks_sessions_status ON mozaiks_sessions(status) 
    WHERE status = 'active';
```

### Entity Framework Model

```csharp
public class MozaiksSession
{
    public Guid Id { get; set; }
    public Guid UserId { get; set; }
    public string MozaiksChatId { get; set; }
    public string WorkflowName { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime LastActivityAt { get; set; }
    public string Status { get; set; }  // "active", "completed", "abandoned"
    public JsonDocument? Metadata { get; set; }
    
    // Navigation
    public User User { get; set; }
}

public class MozaiksSessionConfiguration : IEntityTypeConfiguration<MozaiksSession>
{
    public void Configure(EntityTypeBuilder<MozaiksSession> builder)
    {
        builder.ToTable("mozaiks_sessions");
        
        builder.HasKey(x => x.Id);
        builder.Property(x => x.MozaiksChatId).IsRequired().HasMaxLength(255);
        builder.Property(x => x.WorkflowName).IsRequired().HasMaxLength(100);
        builder.Property(x => x.Status).HasMaxLength(50).HasDefaultValue("active");
        builder.Property(x => x.CreatedAt).HasDefaultValueSql("NOW()");
        builder.Property(x => x.LastActivityAt).HasDefaultValueSql("NOW()");
        
        builder.HasIndex(x => x.MozaiksChatId).IsUnique();
        builder.HasIndex(x => x.UserId);
        builder.HasIndex(x => x.Status).HasFilter("status = 'active'");
        
        builder.HasOne(x => x.User)
            .WithMany()
            .HasForeignKey(x => x.UserId);
    }
}
```

---

## 3. Repository Pattern

```csharp
public interface IMozaiksSessionRepository
{
    Task<MozaiksSession> CreateAsync(Guid userId, string chatId, string workflowName);
    Task<MozaiksSession?> GetByChatIdAsync(string chatId);
    Task<List<MozaiksSession>> GetByUserIdAsync(Guid userId, bool activeOnly = true);
    Task UpdateLastActivityAsync(string chatId);
    Task SetStatusAsync(string chatId, string status);
}

public class MozaiksSessionRepository : IMozaiksSessionRepository
{
    private readonly AppDbContext _db;
    
    public MozaiksSessionRepository(AppDbContext db) => _db = db;
    
    public async Task<MozaiksSession> CreateAsync(Guid userId, string chatId, string workflowName)
    {
        var session = new MozaiksSession
        {
            Id = Guid.NewGuid(),
            UserId = userId,
            MozaiksChatId = chatId,
            WorkflowName = workflowName,
            CreatedAt = DateTime.UtcNow,
            LastActivityAt = DateTime.UtcNow,
            Status = "active"
        };
        
        _db.MozaiksSessions.Add(session);
        await _db.SaveChangesAsync();
        return session;
    }
    
    public async Task<MozaiksSession?> GetByChatIdAsync(string chatId)
    {
        return await _db.MozaiksSessions
            .FirstOrDefaultAsync(x => x.MozaiksChatId == chatId);
    }
    
    public async Task<List<MozaiksSession>> GetByUserIdAsync(Guid userId, bool activeOnly = true)
    {
        var query = _db.MozaiksSessions.Where(x => x.UserId == userId);
        
        if (activeOnly)
            query = query.Where(x => x.Status == "active");
            
        return await query
            .OrderByDescending(x => x.LastActivityAt)
            .ToListAsync();
    }
    
    public async Task UpdateLastActivityAsync(string chatId)
    {
        await _db.MozaiksSessions
            .Where(x => x.MozaiksChatId == chatId)
            .ExecuteUpdateAsync(x => x.SetProperty(s => s.LastActivityAt, DateTime.UtcNow));
    }
    
    public async Task SetStatusAsync(string chatId, string status)
    {
        await _db.MozaiksSessions
            .Where(x => x.MozaiksChatId == chatId)
            .ExecuteUpdateAsync(x => x.SetProperty(s => s.Status, status));
    }
}
```

---

## 4. Integration with Session Broker

The Backend Agent's session broker uses your repository:

```csharp
public class MozaiksSessionBroker
{
    private readonly HttpClient _client;
    private readonly IMozaiksSessionRepository _sessionRepo;
    private readonly MozaiksConfig _config;
    
    public async Task<SessionResult> CreateSessionAsync(
        Guid userId,
        string workflowName,
        Dictionary<string, object>? backendContext = null)
    {
        // 1. Create session in MozaiksAI
        var response = await _client.PostAsJsonAsync("/api/chat/start", new
        {
            app_id = _config.AppId,
            user_id = userId.ToString(),
            workflow_name = workflowName,
            initial_context = backendContext
        });
        
        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<CreateSessionResponse>();
        
        // 2. Track in YOUR database (for audit, user history, etc.)
        await _sessionRepo.CreateAsync(userId, result.ChatId, workflowName);
        
        return new SessionResult
        {
            ChatId = result.ChatId,
            WebSocketUrl = BuildWebSocketUrl(workflowName, result.ChatId, userId)
        };
    }
}
```

---

## 5. Cleanup Job (Optional)

Mark abandoned sessions:

```csharp
public class MozaiksSessionCleanupJob : IHostedService
{
    private readonly IServiceProvider _services;
    private Timer? _timer;
    
    public Task StartAsync(CancellationToken ct)
    {
        _timer = new Timer(DoWork, null, TimeSpan.Zero, TimeSpan.FromHours(1));
        return Task.CompletedTask;
    }
    
    private async void DoWork(object? state)
    {
        using var scope = _services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        
        var threshold = DateTime.UtcNow.AddDays(-30);
        
        await db.MozaiksSessions
            .Where(x => x.Status == "active" && x.LastActivityAt < threshold)
            .ExecuteUpdateAsync(x => x.SetProperty(s => s.Status, "abandoned"));
    }
    
    public Task StopAsync(CancellationToken ct)
    {
        _timer?.Change(Timeout.Infinite, 0);
        return Task.CompletedTask;
    }
}
```

---

## 6. Migration

```csharp
public partial class AddMozaiksSessions : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "mozaiks_sessions",
            columns: table => new
            {
                id = table.Column<Guid>(nullable: false),
                user_id = table.Column<Guid>(nullable: false),
                mozaiks_chat_id = table.Column<string>(maxLength: 255, nullable: false),
                workflow_name = table.Column<string>(maxLength: 100, nullable: false),
                created_at = table.Column<DateTime>(nullable: false, defaultValueSql: "NOW()"),
                last_activity_at = table.Column<DateTime>(nullable: false, defaultValueSql: "NOW()"),
                status = table.Column<string>(maxLength: 50, nullable: false, defaultValue: "active"),
                metadata = table.Column<JsonDocument>(nullable: true)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_mozaiks_sessions", x => x.id);
                table.ForeignKey(
                    name: "FK_mozaiks_sessions_users_user_id",
                    column: x => x.user_id,
                    principalTable: "users",
                    principalColumn: "id",
                    onDelete: ReferentialAction.Cascade);
            });

        migrationBuilder.CreateIndex(
            name: "IX_mozaiks_sessions_mozaiks_chat_id",
            table: "mozaiks_sessions",
            column: "mozaiks_chat_id",
            unique: true);

        migrationBuilder.CreateIndex(
            name: "IX_mozaiks_sessions_user_id",
            table: "mozaiks_sessions",
            column: "user_id");
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropTable(name: "mozaiks_sessions");
    }
}
```

---

## 7. Checklist

- [ ] `mozaiks_sessions` table created
- [ ] `MozaiksSession` entity configured
- [ ] `IMozaiksSessionRepository` implemented
- [ ] Indexes on `user_id` and `mozaiks_chat_id`
- [ ] Migration generated and applied
- [ ] Repository registered in DI

---

## 8. What You Don't Do

- Don't create MongoDB collections (MozaiksAI owns those)
- Don't query MozaiksAI's MongoDB directly
- Don't store chat messages (MozaiksAI handles that)
- Don't implement business logic in the database layer

Your job is just: **track which users have which MozaiksAI sessions**.
