# Troubleshooting Guide

**Purpose:** Diagnostic guide for common MozaiksAI issues, error messages, debugging workflows, and log analysis strategies.

---

## Quick Diagnostic Checklist

When encountering issues, run through this checklist first:

- [ ] **Backend is running**: `curl http://localhost:8000/health/active-runs`
- [ ] **MongoDB is accessible**: Check `MONGO_URI` in `.env` and test connection
- [ ] **Environment variables set**: Verify `OPENAI_API_KEY`, `ENVIRONMENT`, `MONGO_URI`
- [ ] **Logs are being written**: Check `logs/logs/` directory for recent entries
- [ ] **Docker containers healthy**: `docker compose ps` (if using Docker)
- [ ] **Ports not blocked**: Verify firewall allows 8000 (backend), 3000 (frontend)
- [ ] **Frontend can reach backend**: Check browser console for WebSocket errors
- [ ] **No version mismatches**: Frontend `cache_seed` matches backend workflow versions

---

## Common Error Categories

### 1. Startup & Configuration Errors
### 2. MongoDB Connection Issues
### 3. WebSocket & Transport Failures
### 4. Workflow Execution Errors
### 5. UI Tool & Component Issues
### 6. Performance & Timeout Problems
### 7. Authentication & Secrets Errors

---

## 1. Startup & Configuration Errors

### Error: "MONGODB_CONNECTION_FAILED: Failed to connect to MongoDB"

**Symptoms:**
```
ERROR - MONGODB_CONNECTION_FAILED: Failed to connect to MongoDB
ServerSelectionTimeoutError: localhost:27017: [Errno 111] Connection refused
```

**Causes:**
1. MongoDB not running
2. Incorrect `MONGO_URI` in `.env`
3. Network connectivity issue
4. MongoDB authentication failure

**Solutions:**

**Check MongoDB Status (Docker):**
```bash
docker compose -f infra/compose/docker-compose.yml ps mongo

# If not running:
docker compose -f infra/compose/docker-compose.yml up -d mongo
```

**Check MongoDB Status (systemd):**
```bash
sudo systemctl status mongod

# If not running:
sudo systemctl start mongod
```

**Test Connection Manually:**
```bash
# MongoDB shell
mongosh "mongodb://localhost:27017"

# Python test
python -c "
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def test():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    result = await client.admin.command('ping')
    print('Connected:', result)

asyncio.run(test())
"
```

**Verify `.env` Configuration:**
```bash
# Check MONGO_URI format
grep MONGO_URI .env

# Should be one of:
# MONGO_URI=mongodb://localhost:27017/mozaiks
# MONGO_URI=mongodb://user:password@localhost:27017/mozaiks?authSource=admin
# MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/mozaiks
```

**Fix Authentication Issues:**
```bash
# If using authentication, ensure credentials match
# MongoDB Atlas: Whitelist IP address in Atlas UI
# Local MongoDB: Create user with proper permissions

# Create user in MongoDB shell:
use admin
db.createUser({
  user: "mozaiks_user",
  pwd: "secure_password",
  roles: [{ role: "readWrite", db: "mozaiks" }]
})

# Update .env:
MONGO_URI=mongodb://mozaiks_user:secure_password@localhost:27017/mozaiks?authSource=admin
```

---

### Error: "Secret 'OPENAI_API_KEY' not found in environment or Key Vault"

**Symptoms:**
```
ValueError: Secret 'OPENAI_API_KEY' not found in environment or Key Vault
```

**Causes:**
1. `.env` file not loaded
2. Environment variable not set
3. Azure Key Vault misconfigured (if using)

**Solutions:**

**Verify `.env` File:**
```bash
# Check .env exists in repository root
ls -la .env

# Verify OPENAI_API_KEY is set
grep OPENAI_API_KEY .env

# Should output:
# OPENAI_API_KEY=sk-proj-...
```

**Set Environment Variable Manually:**
```bash
# Linux/macOS
export OPENAI_API_KEY="sk-proj-abc123..."

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-proj-abc123..."
```

**Docker: Restart After .env Changes:**
```bash
# Changes to .env require container restart
docker compose -f infra/compose/docker-compose.yml restart app
```

**Verify Variable is Loaded:**
```bash
# Inside container
docker exec mozaiksai-app env | grep OPENAI_API_KEY

# Should show: OPENAI_API_KEY=sk-proj-...
```

---

### Error: "Port 8000 already in use"

**Symptoms:**
```
ERROR - [Errno 98] Address already in use
OSError: [WinError 10048] Only one usage of each socket address is normally permitted
```

**Solutions:**

**Find Process Using Port:**
```bash
# Linux/macOS
sudo lsof -i :8000

# Windows PowerShell
netstat -aon | findstr :8000
```

**Kill Process:**
```bash
# Linux/macOS
sudo kill -9 <PID>

# Windows PowerShell
Stop-Process -Id <PID> -Force
```

**Or Change Port:**
```yaml
# docker-compose.yml
services:
  app:
    ports:
      - "8001:8000"  # Map host 8001 to container 8000
```

```bash
# Update frontend to use new port
# ChatUI/.env.production
REACT_APP_API_URL=http://localhost:8001
```

---

### Error: "TOOL_CACHE_CLEAR_FAILED" or "LLM_CACHE_CLEAR_FAILED"

**Symptoms:**
```
ERROR - TOOL_CACHE_CLEAR_FAILED: Failed to clear tool cache on startup
PermissionError: [Errno 13] Permission denied
```

**Causes:**
1. File permission issues in workflow directories
2. Module import errors during cache clearing

**Solutions:**

**Fix Permissions:**
```bash
# Ensure workflow directories are writable
chmod -R 755 workflows/

# Docker: Ensure volume mounts have correct ownership
chown -R $(id -u):$(id -g) workflows/
```

**Disable Cache Clearing:**
```bash
# In .env (if cache clearing is problematic)
CLEAR_TOOL_CACHE_ON_START=false
CLEAR_LLM_CACHES_ON_START=false
```

**Check Logs for Specific Error:**
```bash
# View full stack trace
docker compose -f infra/compose/docker-compose.yml logs app | grep -A 20 "TOOL_CACHE_CLEAR_FAILED"
```

---

## 2. MongoDB Connection Issues

### Error: "ServerSelectionTimeoutError"

**Symptoms:**
```
ServerSelectionTimeoutError: localhost:27017: [Errno 111] Connection refused, Timeout: 30s
```

**Causes:**
1. MongoDB not running
2. Wrong hostname in `MONGO_URI`
3. Network isolation (Docker networks)

**Solutions:**

**Docker: Use Service Name as Hostname:**
```bash
# If MongoDB is in docker-compose.yml, use service name:
MONGO_URI=mongodb://mongo:27017/mozaiks

# NOT:
# MONGO_URI=mongodb://localhost:27017/mozaiks
```

**Verify Docker Network:**
```bash
# Check containers are on same network
docker network inspect mozaiks-network

# Both 'app' and 'mongo' should be listed
```

**Test Connection from Container:**
```bash
# Shell into app container
docker exec -it mozaiksai-app bash

# Test MongoDB connection
nc -zv mongo 27017
# Or
curl http://mongo:27017
```

---

### Error: "Authentication failed"

**Symptoms:**
```
OperationFailure: Authentication failed.
```

**Solutions:**

**Check Credentials in MONGO_URI:**
```bash
# Format: mongodb://username:password@host:port/database?authSource=admin
MONGO_URI=mongodb://mozaiks_user:correct_password@localhost:27017/mozaiks?authSource=admin
```

**Verify User Exists in MongoDB:**
```bash
mongosh "mongodb://localhost:27017"

use admin
db.getUsers()

# Should list mozaiks_user
```

**Create User if Missing:**
```javascript
// In mongosh
use admin
db.createUser({
  user: "mozaiks_user",
  pwd: "secure_password",
  roles: [
    { role: "readWrite", db: "mozaiks" },
    { role: "dbAdmin", db: "mozaiks" }
  ]
})
```

---

### Error: "Index creation failed" or "E11000 duplicate key error"

**Symptoms:**
```
DuplicateKeyError: E11000 duplicate key error collection: mozaiks.chat_sessions index: chat_id_1 dup key: { chat_id: "chat_abc123" }
```

**Causes:**
1. Duplicate `chat_id` in database
2. Index constraints violated

**Solutions:**

**Find Duplicate Records:**
```javascript
// In mongosh
use mozaiks

// Find duplicates
db.chat_sessions.aggregate([
  { $group: { _id: "$chat_id", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }
])
```

**Remove Duplicates (Keep Latest):**
```javascript
// For each duplicate chat_id, keep only the most recent
db.chat_sessions.aggregate([
  { $sort: { created_at: -1 } },
  { $group: { _id: "$chat_id", docs: { $push: "$$ROOT" } } },
  { $match: { "docs.1": { $exists: true } } }
]).forEach(function(doc) {
  var toDelete = doc.docs.slice(1).map(d => d._id);
  db.chat_sessions.deleteMany({ _id: { $in: toDelete } });
});
```

**Rebuild Indexes:**
```javascript
// Drop and recreate index
db.chat_sessions.dropIndex("chat_id_1")
db.chat_sessions.createIndex({ chat_id: 1 }, { unique: true })
```

---

## 3. WebSocket & Transport Failures

### Error: "WebSocket connection failed"

**Symptoms:**
```
WebSocket connection to 'ws://localhost:8000/ws/chat' failed: Error during WebSocket handshake
```

**Causes:**
1. Backend not running
2. CORS issues
3. Proxy misconfiguration (nginx)
4. WebSocket timeout

**Solutions:**

**Test WebSocket Manually:**
```bash
# Install wscat
npm install -g wscat

# Test connection
wscat -c ws://localhost:8000/ws/chat
```

**Check CORS Settings:**
```python
# In shared_app.py, verify origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**nginx: Ensure WebSocket Proxy Headers:**
```nginx
location /ws/ {
    proxy_pass http://localhost:8000/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;  # Increase timeout
    proxy_send_timeout 300s;
}
```

**Reload nginx:**
```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

### Error: "WS_SESSION_DETERMINATION_FAILED"

**Symptoms:**
```
ERROR - WS_SESSION_DETERMINATION_FAILED: Missing chat_id or workflow_name in connection params
```

**Causes:**
1. Frontend not sending required WebSocket connection parameters
2. URL query string malformed

**Solutions:**

**Verify Frontend Connection Code:**
```javascript
// ChatUI/src/adapters/api.js
const ws = new WebSocket(
  `ws://localhost:8000/ws/chat?chat_id=${chatId}&workflow_name=${workflowName}`
);
```

**Check Browser Console:**
```
// Look for WebSocket URL in network tab
// Should be: ws://localhost:8000/ws/chat?chat_id=chat_abc123&workflow_name=Generator
```

**Backend: Log Connection Params:**
```python
# In shared_app.py WebSocket handler
logger.info(f"WebSocket connection params: {dict(websocket.query_params)}")
```

---

### Error: "Transport unavailable" (UI Tools)

**Symptoms:**
```
ERROR - ❌ [UI_TOOLS] Transport unavailable: SimpleTransport not initialized
```

**Causes:**
1. `SimpleTransport` not initialized during startup
2. WebSocket disconnected during workflow execution

**Solutions:**

**Check Startup Logs:**
```bash
# Search for transport initialization
docker compose logs app | grep "SimpleTransport\|streaming_config"

# Should see:
# ✅ APP_STARTUP: Performance manager initialized
# streaming_config_init_duration: 150ms
```

**Verify Transport Singleton:**
```python
# Test in Python REPL
from core.transport.simple_transport import SimpleTransport
import asyncio

async def test():
    transport = await SimpleTransport.get_instance()
    print("Transport:", transport)
    
asyncio.run(test())
```

**Check WebSocket Connection Status:**
```javascript
// In browser console (ChatUI)
console.log("WebSocket state:", websocket.readyState);
// 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED
```

---

## 4. Workflow Execution Errors

### Error: "Workflow not found"

**Symptoms:**
```
HTTPException: 404 - Workflow 'MyWorkflow' not found
```

**Causes:**
1. Workflow directory doesn't exist
2. Workflow not registered in `workflow_manager`
3. Typo in workflow name

**Solutions:**

**List Available Workflows:**
```bash
# Check workflows/ directory
ls -la workflows/

# Should see:
# workflows/Generator/
# workflows/MyWorkflow/
```

**Test Workflow Discovery:**
```bash
curl http://localhost:8000/api/workflows | jq

# Should list all workflows with metadata
```

**Check Workflow Structure:**
```bash
# Verify required files
workflows/MyWorkflow/
├── agents.json              # Required
├── orchestrator.json        # Required
├── handoffs.json            # Required
├── structured_outputs.json  # Required
├── context_variables.json   # Optional but recommended
├── tools.json               # Optional but recommended
└── tools/                   # Optional tool implementations
```

**Verify orchestrator.json:**
```json
{
  "workflow_name": "MyWorkflow",
  "max_turns": 20,
  "human_in_the_loop": true,
  "startup_mode": "UserDriven",
  "orchestration_pattern": "DefaultPattern",
  "initial_agent": "<AgentName>"
}
```

---

### Error: "Agent turn timeout"

**Symptoms:**
```
WARNING - Agent turn exceeded timeout (30s)
ERROR - Workflow execution failed: Agent did not respond
```

**Causes:**
1. LLM API timeout
2. Slow tool execution
3. Deadlock in agent communication
4. Network latency to OpenAI

**Solutions:**

**Increase Agent Turn Timeout:**
```json
// In workflow's orchestrator.json
{
  "max_turns": 20
}
```

**Check LLM API Response Time:**
```bash
# Monitor performance logs
tail -f logs/logs/performance.log | grep "agent_turn"

# Look for high duration_sec values
```

**Increase OpenAI Timeout:**
```python
# In core/workflow/llm_config.py or workflow's agents.json
{
  "model": "gpt-4",
  "timeout": 120  // Increase from default 60s
}
```

**Enable Debug Logging:**
```bash
# Set LOG_LEVEL in .env
LOG_LEVEL=DEBUG

# Restart backend
docker compose restart app

# Check logs for agent communication
tail -f logs/logs/autogen_file.log
```

---

### Error: "Tool not found" or "Tool execution failed"

**Symptoms:**
```
ERROR - Tool 'my_tool' not found in workflow 'MyWorkflow'
ERROR - ❌ Tool execution failed: ModuleNotFoundError: No module named 'my_module'
```

**Causes:**
1. Tool not registered in `tools.json`
2. Tool file missing or import error
3. Incorrect function signature

**Solutions:**

**Verify tools.json:**
```json
// workflows/MyWorkflow/tools.json
{
  "tools": [
    {
      "file": "my_tool",
      "function": "my_tool_function",
      "type": "Agent_Tool",
      "description": "..."
    }
  ]
}
```

**Check Tool File Exists:**
```bash
ls workflows/MyWorkflow/tools/my_tool.py

# Should exist and contain my_tool_function
```

**Test Tool Import:**
```python
# Python REPL
import sys
sys.path.append('workflows/MyWorkflow/tools')

from my_tool import my_tool_function
print(my_tool_function)
```

**Verify Function Signature:**
```python
# Tool functions should accept specific parameters
from typing import Annotated
from autogen import ConversableAgent

def my_tool_function(
    param1: Annotated[str, "Description"],
    context_variables: dict,  # Required for runtime context
    agent: ConversableAgent   # Required for agent access
) -> str:
    return "result"
```

**Clear Tool Cache:**
```bash
# Force reload of tool modules
# In .env:
CLEAR_TOOL_CACHE_ON_START=true

# Restart
docker compose restart app
```

---

## 5. UI Tool & Component Issues

### Error: "UI component not found"

**Symptoms:**
```
WARNING - Component 'MyComponent' not found for workflow 'MyWorkflow'
// Frontend shows: "Component not found" error message
```

**Causes:**
1. Component not exported in workflow's `components/index.js`
2. Component file missing
3. Frontend cache stale (cache_seed mismatch)

**Solutions:**

**Check Component Export:**
```javascript
// workflows/MyWorkflow/components/index.js
import MyComponent from './MyComponent';

export default {
  MyComponent,
  // ... other components
};

export { MyComponent };
```

**Verify Component File:**
```bash
ls workflows/MyWorkflow/components/MyComponent.js

# Should exist with valid React component
```

**Clear Frontend Cache:**
```javascript
// In browser console (ChatUI)
localStorage.clear();
sessionStorage.clear();
location.reload();
```

**Check cache_seed Synchronization:**
```bash
# Backend: Check workflow's cache_seed
curl http://localhost:8000/api/workflows | jq '.[] | select(.name=="MyWorkflow") | .cache_seed'

# Frontend: Check localStorage cache
// In browser console:
const cache = JSON.parse(localStorage.getItem('mozaiks_workflows_cache_v1'));
console.log(cache.workflows.MyWorkflow.cache_seed);

# If mismatch, reload frontend
```

---

### Error: "UI tool response timeout"

**Symptoms:**
```
ERROR - ❌ UI tool 'user_input' timed out waiting for user response
```

**Causes:**
1. User didn't respond within timeout period
2. Frontend component failed to send response
3. WebSocket disconnected during interaction

**Solutions:**

**Increase UI Tool Timeout:**
```python
# In workflow's tool implementation
from core.workflow.ui_tools import use_ui_tool

response = await use_ui_tool(
    tool_id="my_tool",
    payload={"key": "value"},
    chat_id=chat_id,
    workflow_name=workflow_name,
    timeout_sec=120  # Increase from default 60s
)
```

**Check WebSocket Connection:**
```javascript
// In browser console
console.log("WebSocket state:", api.ws?.readyState);
// Should be 1 (OPEN)
```

**Verify Component onResponse Called:**
```javascript
// In component (e.g., MyComponent.js)
const handleSubmit = () => {
  onResponse({
    ui_tool_id: props.ui_tool_id,
    event_id: props.eventId,
    payload: { result: "user_input" }
  });
};

// Ensure handleSubmit is called on button click
```

**Check Backend Logs for Response Receipt:**
```bash
tail -f logs/logs/workflow_execution.log | grep "UI_TOOL_RESPONSE_RECEIVED"

# Should see log when frontend sends response
```

---

### Error: "Auto-tool execution failed"

**Symptoms:**
```
ERROR - ❌ Auto-tool 'ActionPlan' failed: Binding resolution error
```

**Causes:**
1. Structured output schema mismatch
2. Missing binding in `structured_outputs.json`
3. Tool registration incorrect

**Solutions:**

**Verify Structured Output Registration:**
```json
// workflows/MyWorkflow/structured_outputs.json
{
  "ActionPlan": {
    "ui_tool": "action_plan",
    "auto_execute": true,
    "display": "artifact"
  }
}
```

**Check Pydantic Schema:**
```python
# In workflow tool file
from pydantic import BaseModel, Field

class ActionPlan(BaseModel):
    """Auto-tool schema"""
    workflow: dict = Field(description="...")
    
    class Config:
        title = "ActionPlan"  # Must match structured_outputs.json key
```

**Test Binding Resolution:**
```bash
# Check logs for binding process
docker compose logs app | grep "AUTO_TOOL\|BINDING_RESOLVED"
```

**Verify Tool in tools.json:**
```json
{
  "tools": [
    {
      "file": "action_plan",
      "function": "action_plan",
      "type": "UI_Tool",
      "description": "..."
    }
  ]
}
```

---

## 6. Performance & Timeout Problems

### Error: "High memory usage" or "Container OOM killed"

**Symptoms:**
```
docker compose logs app
# Shows: Killed (exit code 137)
# Or: MemoryError
```

**Causes:**
1. Too many concurrent workflows
2. Large context windows in LLM calls
3. Memory leak in long-running sessions
4. Insufficient Docker memory limit

**Solutions:**

**Increase Docker Memory Limit:**
```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 8G  # Increase from 4G
```

**Reduce Concurrent Workflows:**
```bash
# Monitor active chats
curl http://localhost:8000/health/active-runs

# Limit concurrent sessions in code (future feature)
```

**Clear Old Chat Sessions:**
```javascript
// In MongoDB
use mozaiks
db.chat_sessions.deleteMany({
  ended_at: { $lt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000) }
})
```

**Monitor Memory Usage:**
```bash
# Docker stats
docker stats mozaiksai-app

# Look for memory usage approaching limit
```

**Flush Metrics More Frequently:**
```python
# In core/observability/performance_manager.py
# Reduce flush_interval_sec from 300 to 60
```

---

### Error: "Database query slow" or "Timeout"

**Symptoms:**
```
WARNING - MongoDB query exceeded 5000ms
OperationFailure: operation exceeded time limit
```

**Solutions:**

**Add Missing Indexes:**
```javascript
// In mongosh
use mozaiks

// Check existing indexes
db.chat_sessions.getIndexes()

// Add indexes for common queries
db.chat_sessions.createIndex({ app_id: 1, user_id: 1 })
db.chat_messages.createIndex({ chat_id: 1, timestamp: 1 })
db.context_store.createIndex({ chat_id: 1, key: 1 }, { unique: true })
```

**Increase Query Timeout:**
```python
# In persistence manager
await collection.find_one(
    {"chat_id": chat_id},
    max_time_ms=10000  # Increase from 5000ms
)
```

**Optimize Queries:**
```python
# Use projections to limit returned fields
await collection.find_one(
    {"chat_id": chat_id},
    {"_id": 0, "metadata": 1, "status": 1}
)
```

---

## 7. Authentication & Secrets Errors

### Error: "Azure Key Vault authentication failed"

**Symptoms:**
```
ERROR - Failed to authenticate with Azure Key Vault
ClientAuthenticationError: authentication failed
```

**Causes:**
1. Invalid Azure credentials
2. Service Principal expired
3. Key Vault access policy not configured

**Solutions:**

**Verify Azure Credentials:**
```bash
# Check .env for Azure variables
grep AZURE_ .env

# Should have:
# AZURE_CLIENT_ID=...
# AZURE_TENANT_ID=...
# AZURE_CLIENT_SECRET=...
# AZURE_KEY_VAULT_NAME=...
```

**Test Azure Authentication:**
```python
from azure.identity import DefaultAzureCredential

try:
    credential = DefaultAzureCredential()
    token = credential.get_token("https://vault.azure.net/.default")
    print("Authentication successful")
except Exception as e:
    print(f"Auth failed: {e}")
```

**Fallback to Environment Variables:**
```bash
# If Key Vault unavailable, set secrets directly
OPENAI_API_KEY=sk-proj-...
MONGO_URI=mongodb://...

# Restart backend
docker compose restart app
```

---

### Error: "API key invalid or expired"

**Symptoms:**
```
OpenAIError: Incorrect API key provided
AuthenticationError: The api_key client option must be set
```

**Solutions:**

**Verify API Key Format:**
```bash
# OpenAI keys start with sk-proj-
echo $OPENAI_API_KEY | grep "^sk-"

# If empty or wrong format, update .env
OPENAI_API_KEY=sk-proj-abc123...
```

**Test API Key:**
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Should return list of models
# If error, key is invalid
```

**Rotate API Key:**
1. Visit https://platform.openai.com/api-keys
2. Create new secret key
3. Update `.env` or Azure Key Vault
4. Restart backend

---

## Log Analysis Strategies

### Viewing Logs by Category

**Workflow Execution Logs:**
```bash
tail -f logs/logs/workflow_execution.log | jq 'select(.logger == "workflow_execution")'
```

**Performance Metrics:**
```bash
tail -f logs/logs/performance.log | jq 'select(.msg | contains("agent_turn"))'
```

**Error Logs Only:**
```bash
tail -f logs/logs/*.log | jq 'select(.level == "ERROR")'
```

**Specific Chat Session:**
```bash
# Filter by chat_id
tail -f logs/logs/workflow_execution.log | jq 'select(.extra.chat_id == "chat_abc123")'
```

---

### Common Log Patterns

**Successful Workflow Start:**
```json
{
  "msg": "WORKFLOW_STARTED",
  "level": "INFO",
  "extra": {
    "chat_id": "chat_abc123",
    "workflow_name": "Generator",
    "app_id": "acme_corp"
  }
}
```

**Agent Turn Completion:**
```json
{
  "msg": "agent_turn",
  "level": "INFO",
  "extra": {
    "agent_name": "planner",
    "duration_sec": 2.5,
    "prompt_tokens": 1500,
    "completion_tokens": 800
  }
}
```

**UI Tool Invocation:**
```json
{
  "msg": "UI_TOOL_INVOKED",
  "level": "INFO",
  "extra": {
    "tool_id": "user_input",
    "ui_tool_id": "ui_123",
    "chat_id": "chat_abc123"
  }
}
```

**Error Pattern:**
```json
{
  "msg": "WORKFLOW_EXECUTION_FAILED",
  "level": "ERROR",
  "extra": {
    "chat_id": "chat_abc123",
    "error": "TimeoutError: Agent did not respond"
  },
  "exception": {
    "type": "TimeoutError",
    "message": "...",
    "trace": ["..."]
  }
}
```

---

## Debugging Workflows Step-by-Step

### 1. Enable Debug Logging

```bash
# In .env
LOG_LEVEL=DEBUG

# Restart
docker compose restart app
```

### 2. Monitor AG2 Agent Logs

```bash
# Real-time agent communication
tail -f logs/logs/autogen_file.log

# Or with jq filtering
tail -f logs/logs/autogen_file.log | jq 'select(.msg | contains("AGENT_MESSAGE"))'
```

### 3. Track Specific Chat Session

```bash
# Set chat_id variable
CHAT_ID="chat_abc123"

# Follow all logs for this chat
tail -f logs/logs/*.log | jq "select(.extra.chat_id == \"$CHAT_ID\")"
```

### 4. Inspect Context Variables

```python
# In Python REPL or tool function
from core.data.persistence_manager import AG2PersistenceManager

async def inspect_context(chat_id):
    pm = AG2PersistenceManager.get_instance()
    context = await pm.get_all_context(chat_id)
    print(json.dumps(context, indent=2))
    
import asyncio
asyncio.run(inspect_context("chat_abc123"))
```

### 5. Check MongoDB State

```javascript
// In mongosh
use mozaiks

// Get chat session
db.chat_sessions.findOne({ chat_id: "chat_abc123" })

// Get last 10 messages
db.chat_messages.find({ chat_id: "chat_abc123" })
  .sort({ timestamp: -1 })
  .limit(10)

// Get context variables
db.context_store.find({ chat_id: "chat_abc123" })
```

---

## Health Check Script

**Create Diagnostic Script (`scripts/health_check.sh`):**

```bash
#!/bin/bash
# MozaiksAI Health Check Script

echo "=== MozaiksAI Health Check ==="

# 1. Backend API
echo -n "Backend API: "
if curl -s http://localhost:8000/health/active-runs > /dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED"
fi

# 2. MongoDB
echo -n "MongoDB: "
if docker exec mozaiksai-app python -c "from motor.motor_asyncio import AsyncIOMotorClient; import asyncio; asyncio.run(AsyncIOMotorClient('mongodb://mongo:27017').admin.command('ping'))" &> /dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED"
fi

# 3. Disk Space
echo -n "Disk Space: "
USAGE=$(df -h /opt/mozaiksai | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$USAGE" -lt 80 ]; then
    echo "✅ OK ($USAGE%)"
else
    echo "⚠️  WARNING ($USAGE%)"
fi

# 4. Memory Usage
echo -n "Memory Usage: "
MEM=$(docker stats mozaiksai-app --no-stream --format "{{.MemPerc}}" | sed 's/%//')
if [ "$MEM" -lt 80 ]; then
    echo "✅ OK ($MEM%)"
else
    echo "⚠️  WARNING ($MEM%)"
fi

# 5. Log Size
echo -n "Log Size: "
LOG_SIZE=$(du -sh logs/logs/ | awk '{print $1}')
echo "📊 $LOG_SIZE"

# 6. Active Chats
echo -n "Active Chats: "
ACTIVE=$(curl -s http://localhost:8000/health/active-runs | jq '.active_runs')
echo "🔢 $ACTIVE"

echo "=== Health Check Complete ==="
```

**Run Health Check:**
```bash
chmod +x scripts/health_check.sh
./scripts/health_check.sh
```

---

## When to Escalate

**Contact Support If:**

1. **Data Loss**: Chat sessions or messages missing from database
2. **Security Breach**: Unauthorized access or API key exposure
3. **Persistent Crashes**: Backend crashes repeatedly despite troubleshooting
4. **Performance Degradation**: Response times consistently > 30s
5. **Billing Issues**: Unexpected OpenAI costs or token consumption
6. **Integration Failures**: Azure Key Vault, MongoDB Atlas, or external services fail

**Gather Before Escalating:**

- [ ] Last 500 lines of logs: `docker compose logs --tail=500 app > logs_export.txt`
- [ ] Environment config (sanitized): `.env` with secrets redacted
- [ ] Error messages with full stack traces
- [ ] Steps to reproduce the issue
- [ ] MongoDB collection sizes: `db.stats()` output
- [ ] Docker/system resource stats: `docker stats` and `free -h`

---

## Next Steps

- **[Performance Tuning](performance_tuning.md)** - Optimize for scale and efficiency
- **[Monitoring Guide](monitoring.md)** - Set up observability and alerting
- **[Deployment Guide](deployment.md)** - Production deployment best practices
- **[Configuration Reference](../runtime/configuration_reference.md)** - All environment variables
- **[Database Schema](../reference/database_schema.md)** - MongoDB collections and indexes
