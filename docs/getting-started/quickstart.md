# Quickstart

Get MozaiksAI running in under 5 minutes.

## Prerequisites

- Python 3.11+
- MongoDB instance (local or cloud)
- OpenAI API key

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/MozaiksAI.git
cd MozaiksAI

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Runtime
JWT_SECRET=your-secret-key-for-development
ALLOWED_ISSUERS=["your-platform-issuer"]

# Optional features
CONTEXT_AWARE=false
MONETIZATION_ENABLED=false
```

## Start the Runtime

```bash
python run_server.py
```

You should see:

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Test with WebSocket

Use a WebSocket client or this Python snippet:

```python
import asyncio
import websockets
import json

async def test_runtime():
    uri = "ws://localhost:8000/ws"
    headers = {
        "Authorization": "Bearer YOUR_JWT_TOKEN"
    }
    
    async with websockets.connect(uri, extra_headers=headers) as ws:
        # Send a message
        await ws.send(json.dumps({
            "content": "Hello from MozaiksAI!",
            "workflow_name": "YourWorkflow",
            "app_id": "test-app",
            "user_id": "test-user",
            "chat_id": "test-session"
        }))
        
        # Receive events
        async for message in ws:
            event = json.loads(message)
            print(f"Event: {event['type']}")
            if event['type'] == 'workflow_complete':
                break

asyncio.run(test_runtime())
```

## Next Steps

- [Create your first workflow](../guides/creating-workflows.md)
- [Understand the architecture](../architecture/overview.md)
- [Deploy to production](deployment.md)
- [Integrate with your frontend](../guides/websocket-protocol.md)
