# Installation

Detailed installation instructions for different environments.

## System Requirements

- **Python**: 3.11 or higher
- **MongoDB**: 4.4 or higher
- **Memory**: 2GB minimum (4GB recommended)
- **OS**: Linux, macOS, or Windows

## Development Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/MozaiksAI.git
cd MozaiksAI
```

### 2. Set Up Python Environment

=== "Linux/macOS"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

=== "Windows"

    ```powershell
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```

### 3. Install MongoDB

=== "Docker"

    ```bash
    docker run -d \
      --name mozaiks-mongo \
      -p 27017:27017 \
      -e MONGO_INITDB_ROOT_USERNAME=admin \
      -e MONGO_INITDB_ROOT_PASSWORD=password \
      mongo:7
    ```

=== "MongoDB Atlas"

    1. Create free cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
    2. Get connection string
    3. Add to `.env` as `MONGODB_URI`

=== "Local Install"

    ```bash
    # Ubuntu/Debian
    sudo apt-get install mongodb-org
    
    # macOS
    brew tap mongodb/brew
    brew install mongodb-community
    
    # Start service
    sudo systemctl start mongod  # Linux
    brew services start mongodb-community  # macOS
    ```

### 4. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=mozaiks_runtime

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# JWT Authentication
JWT_SECRET=generate-a-secure-random-string
ALLOWED_ISSUERS=["your-platform-domain"]

# Runtime Configuration
LOG_LEVEL=INFO
CONTEXT_AWARE=false
MONETIZATION_ENABLED=false
```

### 5. Verify Installation

```bash
python run_server.py
```

You should see startup logs without errors.

## Production Installation

See the [Deployment Guide](deployment.md) for production setup including:
- Container deployment (Docker/Kubernetes)
- Reverse proxy configuration (nginx)
- SSL/TLS setup
- Monitoring and observability
- High availability patterns

## Troubleshooting

### Import Errors

If you see module import errors:
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### MongoDB Connection Failed

- Check MongoDB is running: `mongosh` or `docker ps`
- Verify `MONGODB_URI` in `.env`
- Check firewall rules if using remote MongoDB

### Port Already in Use

Change the port in `run_server.py`:
```python
uvicorn.run(app, host="0.0.0.0", port=8001)  # Changed from 8000
```

## Optional Dependencies

### Documentation (for contributors)

```bash
pip install mkdocs-material
mkdocs serve  # Preview docs locally
```

### Development Tools

```bash
pip install black ruff pytest pytest-asyncio
```

## Next Steps

- [Quickstart Tutorial](quickstart.md)
- [Configure your first workflow](../guides/creating-workflows.md)
- [Deploy to production](deployment.md)
