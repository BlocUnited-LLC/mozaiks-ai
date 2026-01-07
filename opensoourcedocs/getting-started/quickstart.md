# Quickstart

## Prerequisites

- Python 3.11+
- MongoDB
- OpenAI key (or your configured LLM provider via AG2)

## Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Create `.env`:

```env
MONGODB_URI=mongodb://localhost:27017
OPENAI_API_KEY=sk-...
JWT_SECRET=dev-only-secret
ALLOWED_ISSUERS=["your-platform"]
```

## Run

```bash
python run_server.py
```

## Verify

Your runtime should be reachable (depending on your config) at `http://localhost:8000` and WebSocket at `/ws`.
