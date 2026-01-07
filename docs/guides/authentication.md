# MozaiksAI Authentication

Provider-agnostic JWT authentication for the MozaiksAI runtime.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MozaiksAI Runtime                               │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      core/auth/                                   │  │
│  │  ┌────────────┐   ┌──────────────┐   ┌──────────────────────┐   │  │
│  │  │  config.py │──>│   jwks.py    │──>│  jwt_validator.py    │   │  │
│  │  │  (env vars)│   │  (caching)   │   │  (RS256 validation)  │   │  │
│  │  └────────────┘   └──────────────┘   └──────────────────────┘   │  │
│  │         │                                       │               │  │
│  │         v                                       v               │  │
│  │  ┌────────────────────────┐   ┌─────────────────────────────┐  │  │
│  │  │   dependencies.py      │   │   websocket_auth.py         │  │  │
│  │  │   (HTTP Depends)       │   │   (WS connection auth)      │  │  │
│  │  │   require_user()       │   │   authenticate_websocket()  │  │  │
│  │  └────────────────────────┘   └─────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Configuration

All settings via environment variables (provider-agnostic):

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | `true` | Set `false` for local dev bypass |
| `AUTH_ISSUER` | Mozaiks CIAM | JWT issuer to validate |
| `AUTH_JWKS_URL` | Mozaiks CIAM | JWKS endpoint for public keys |
| `AUTH_AUDIENCE` | `api://mozaiks-auth` | Expected `aud` claim |
| `AUTH_REQUIRED_SCOPE` | `access_as_user` | Required scope for user endpoints |
| `AUTH_USER_ID_CLAIM` | `sub` | Claim name for user ID |
| `AUTH_EMAIL_CLAIM` | `email` | Claim name for email |
| `AUTH_ROLES_CLAIM` | `roles` | Claim name for roles |
| `AUTH_JWKS_CACHE_TTL` | `3600` | JWKS cache TTL (seconds) |
| `AUTH_ALGORITHMS` | `RS256` | Comma-separated allowed algorithms |
| `AUTH_CLOCK_SKEW` | `120` | Clock skew tolerance (seconds) |

### Mozaiks CIAM Defaults

```bash
AUTH_ISSUER=https://9d0073d5-42e8-46f0-a325-5b4be7b1a38d.ciamlogin.com/9d0073d5-42e8-46f0-a325-5b4be7b1a38d/v2.0
AUTH_JWKS_URL=https://mozaiks.ciamlogin.com/9d0073d5-42e8-46f0-a325-5b4be7b1a38d/discovery/v2.0/keys
AUTH_AUDIENCE=api://mozaiks-auth
AUTH_REQUIRED_SCOPE=access_as_user
```

### Local Development

```bash
# Disable auth for local dev
AUTH_ENABLED=false
```

## Usage

### HTTP Routes

```python
from fastapi import FastAPI, Depends
from core.auth import require_user, require_role, UserPrincipal

app = FastAPI()

# Require authenticated user with access_as_user scope
@app.get("/api/me")
async def get_profile(user: UserPrincipal = Depends(require_user)):
    return {
        "user_id": user.user_id,
        "email": user.email,
        "roles": user.roles,
    }

# Require specific role
@app.get("/api/admin/stats")
async def admin_stats(user: UserPrincipal = Depends(require_role("admin"))):
    return {"stats": "..."}

# Optional auth (returns None if no token)
from core.auth import optional_user

@app.get("/api/public")
async def public_endpoint(user: UserPrincipal | None = Depends(optional_user)):
    if user:
        return {"message": f"Hello {user.email}"}
    return {"message": "Hello anonymous"}
```

### WebSocket Connections

```python
from fastapi import WebSocket
from core.auth import authenticate_websocket, require_resource_ownership

@app.websocket("/ws/chat/{chat_id}")
async def chat_websocket(websocket: WebSocket, chat_id: str):
    # 1) Authenticate (validates token from ?access_token query param)
    user = await authenticate_websocket(websocket)
    if user is None:
        return  # Connection already closed with 4001/4002

    # 2) Verify ownership (optional - if chat is user-owned)
    chat = await get_chat(chat_id)
    if chat and not await require_resource_ownership(websocket, chat.owner_id):
        return  # Connection closed with 4003

    # 3) Accept connection
    await websocket.accept()
    
    # user context is now bound:
    # - websocket.state.user_id
    # - websocket.state.email
    # - websocket.state.roles
    
    # ... handle messages
```

### WebSocket Close Codes

| Code | Constant | Meaning |
|------|----------|---------|
| 4001 | `WS_CLOSE_AUTH_REQUIRED` | Missing access_token |
| 4002 | `WS_CLOSE_AUTH_INVALID` | Token validation failed |
| 4003 | `WS_CLOSE_ACCESS_DENIED` | Insufficient permissions |

## ChatUI Integration

### Passing Token to WebSocket

The ChatUI must pass the access token when connecting to WebSocket:

```javascript
// src/hooks/useWebSocket.js (or similar)

import { useMsal } from '@azure/msal-react';

const useAuthenticatedWebSocket = (chatId) => {
  const { instance, accounts } = useMsal();
  const [socket, setSocket] = useState(null);

  useEffect(() => {
    const connect = async () => {
      // 1) Acquire access token silently
      const tokenRequest = {
        scopes: ['api://mozaiks-auth/access_as_user'],
        account: accounts[0],
      };
      
      let accessToken;
      try {
        const response = await instance.acquireTokenSilent(tokenRequest);
        accessToken = response.accessToken;
      } catch (error) {
        // Fallback to interactive if silent fails
        const response = await instance.acquireTokenPopup(tokenRequest);
        accessToken = response.accessToken;
      }

      // 2) Connect with token in query param
      const wsUrl = `${WS_BASE_URL}/ws/chat/${chatId}?access_token=${encodeURIComponent(accessToken)}`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => console.log('WebSocket connected');
      ws.onerror = (e) => console.error('WebSocket error:', e);
      ws.onclose = (e) => {
        console.log(`WebSocket closed: ${e.code} ${e.reason}`);
        // Handle auth-specific close codes
        if (e.code === 4001) {
          console.error('Auth required - redirecting to login');
        } else if (e.code === 4002) {
          console.error('Invalid token - refreshing...');
        } else if (e.code === 4003) {
          console.error('Access denied');
        }
      };

      setSocket(ws);
    };

    connect();
    
    return () => socket?.close();
  }, [chatId, instance, accounts]);

  return socket;
};
```

### HTTP Requests

```javascript
// src/services/api.js

import { useMsal } from '@azure/msal-react';

const useApi = () => {
  const { instance, accounts } = useMsal();

  const callApi = async (endpoint, options = {}) => {
    const tokenRequest = {
      scopes: ['api://mozaiks-auth/access_as_user'],
      account: accounts[0],
    };

    const response = await instance.acquireTokenSilent(tokenRequest);
    
    return fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${response.accessToken}`,
        'Content-Type': 'application/json',
      },
    });
  };

  return { callApi };
};
```

## Test Plan

### 1. Unit Tests

```bash
# Run auth unit tests
pytest tests/test_auth.py -v
```

### 2. Manual HTTP Testing

```bash
# Get a token (use browser dev tools after login, or az cli)
TOKEN="eyJ..."

# Test protected endpoint
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/me

# Expected: 200 with user info
# {"user_id": "...", "email": "..."}

# Test without token
curl http://localhost:8000/api/me

# Expected: 401
# {"detail": "Missing authorization token"}

# Test with invalid token
curl -H "Authorization: Bearer invalid" \
     http://localhost:8000/api/me

# Expected: 401
# {"detail": "Invalid token format"}
```

### 3. WebSocket Testing

```javascript
// Browser console test
const token = "eyJ..."; // Get from MSAL or network tab
const ws = new WebSocket(`ws://localhost:8000/ws/chat/test-chat?access_token=${token}`);

ws.onopen = () => console.log('Connected!');
ws.onclose = (e) => console.log(`Closed: ${e.code} ${e.reason}`);
ws.onerror = (e) => console.error('Error:', e);

// Test without token
const wsBad = new WebSocket('ws://localhost:8000/ws/chat/test-chat');
// Expected: Close with code 4001
```

### 4. Python WebSocket Test

```python
import asyncio
import websockets

async def test_ws():
    token = "eyJ..."  # Your access token
    uri = f"ws://localhost:8000/ws/chat/test-chat?access_token={token}"
    
    try:
        async with websockets.connect(uri) as ws:
            print("Connected!")
            await ws.send('{"type": "ping"}')
            response = await ws.recv()
            print(f"Received: {response}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e.code} {e.reason}")

asyncio.run(test_ws())
```

### 5. Auth Disabled (Local Dev)

```bash
# Set in .env
AUTH_ENABLED=false

# All requests work without token
curl http://localhost:8000/api/me
# Returns: {"user_id": "anonymous", "email": null, ...}
```

## Security Considerations

1. **Token in Query Param**: WebSocket tokens via query param are visible in server logs. 
   - Ensure logs redact `access_token` parameter
   - Use HTTPS in production

2. **Clock Skew**: 120 seconds tolerance for exp/nbf claims
   - Adjust via `AUTH_CLOCK_SKEW` if needed

3. **JWKS Caching**: Keys cached for 1 hour by default
   - On key rotation, unknown `kid` triggers immediate refresh

4. **Scope Enforcement**: `access_as_user` required for user endpoints
   - Service-to-service calls should use different scopes/credentials

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid token issuer` | Token from wrong tenant | Check `AUTH_ISSUER` matches token |
| `Invalid token audience` | Token has wrong `aud` | Ensure MSAL uses correct scope |
| `Missing required scope` | Token lacks `access_as_user` | Add scope to MSAL token request |
| `Signing key not found` | JWKS doesn't have `kid` | Check `AUTH_JWKS_URL`, force refresh |
| `Token has expired` | Token TTL exceeded | Refresh token in client |
