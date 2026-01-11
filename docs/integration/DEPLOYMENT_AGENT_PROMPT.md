# Deployment Agent Prompt — MozaiksAI Integration

**Role**: You deploy and configure infrastructure for apps using MozaiksAI.

**Your Job**: Run MozaiksAI Runtime alongside your app. Configure networking and environment variables.

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Infrastructure                                             │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  ┌─────────────┐    ┌─────────────────┐    ┌────────────────┐   │
│  │ Your App    │───►│ MozaiksAI       │───►│ MongoDB        │   │
│  │ (backend)   │    │ Runtime         │    │                │   │
│  └─────────────┘    └─────────────────┘    └────────────────┘   │
│        │                    │                                    │
│        │                    │                                    │
│        ▼                    ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Load Balancer (WebSocket sticky sessions)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│                        Frontend                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Docker Compose (Development)

```yaml
version: '3.8'

services:
  # Your backend app
  backend:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      - Mozaiks__ApiUrl=http://mozaiks:8000
      - Mozaiks__WsUrl=ws://mozaiks:8000
      - Mozaiks__AppId=${APP_ID}
    depends_on:
      - mozaiks

  # MozaiksAI Runtime
  mozaiks:
    image: mozaiksai/runtime:latest
    ports:
      - "8000:8000"
    environment:
      - MONGODB_URI=mongodb://mongo:27017/mozaiks
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - APP_ID=${APP_ID}
      - CONTEXT_AWARE=true
    depends_on:
      - mongo
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # MongoDB for MozaiksAI
  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

  # Your frontend
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:5000
      - REACT_APP_MOZAIKS_WS_URL=ws://localhost:8000

volumes:
  mongo_data:
```

---

## 3. Environment Variables

### Your Backend

```bash
# .env for your backend
Mozaiks__ApiUrl=http://mozaiks:8000
Mozaiks__WsUrl=ws://mozaiks:8000
Mozaiks__AppId=your-app-id
```

### MozaiksAI Runtime

```bash
# .env for MozaiksAI Runtime
# Required
MONGODB_URI=mongodb://mongo:27017/mozaiks
OPENAI_API_KEY=sk-...

# App identification
APP_ID=your-app-id

# Features
CONTEXT_AWARE=true
MONETIZATION_ENABLED=false

# Logging
LOG_LEVEL=INFO

# Performance
MAX_CONCURRENT_WORKFLOWS=50
WORKFLOW_TIMEOUT_SECONDS=300
```

### Frontend

```bash
# .env for frontend
REACT_APP_API_URL=http://localhost:5000
REACT_APP_MOZAIKS_WS_URL=ws://localhost:8000
```

---

## 4. Kubernetes (Production)

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mozaiks
```

### MozaiksAI Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mozaiks-runtime
  namespace: mozaiks
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mozaiks-runtime
  template:
    metadata:
      labels:
        app: mozaiks-runtime
    spec:
      containers:
      - name: mozaiks
        image: mozaiksai/runtime:latest
        ports:
        - containerPort: 8000
        env:
        - name: MONGODB_URI
          valueFrom:
            secretKeyRef:
              name: mozaiks-secrets
              key: mongodb-uri
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: mozaiks-secrets
              key: openai-api-key
        - name: APP_ID
          valueFrom:
            configMapKeyRef:
              name: mozaiks-config
              key: app-id
        - name: CONTEXT_AWARE
          value: "true"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Service (WebSocket-aware)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mozaiks-runtime
  namespace: mozaiks
spec:
  selector:
    app: mozaiks-runtime
  ports:
  - port: 8000
    targetPort: 8000
  sessionAffinity: ClientIP  # Sticky sessions for WebSocket
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 3600
```

### Ingress (with WebSocket support)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mozaiks-ingress
  namespace: mozaiks
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/upstream-hash-by: "$remote_addr"
spec:
  rules:
  - host: mozaiks.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mozaiks-runtime
            port:
              number: 8000
```

### Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mozaiks-secrets
  namespace: mozaiks
type: Opaque
stringData:
  mongodb-uri: "mongodb+srv://user:pass@cluster.mongodb.net/mozaiks"
  openai-api-key: "sk-..."
```

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mozaiks-config
  namespace: mozaiks
data:
  app-id: "your-app-id"
```

---

## 5. MongoDB (Production)

Use MongoDB Atlas or a managed MongoDB service.

### Atlas Connection String

```bash
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/mozaiks?retryWrites=true&w=majority
```

### Required Indexes (MozaiksAI creates these automatically)

```javascript
// These are created by MozaiksAI on startup - you don't need to create them
db.chat_sessions.createIndex({ app_id: 1, user_id: 1 })
db.chat_sessions.createIndex({ chat_id: 1 }, { unique: true })
db.chat_messages.createIndex({ chat_id: 1, timestamp: 1 })
```

---

## 6. Load Balancer Configuration

### WebSocket Requirements

- **Sticky sessions**: Required for WebSocket connections
- **Timeout**: Set to at least 3600 seconds (1 hour)
- **Upgrade headers**: Must pass `Upgrade` and `Connection` headers

### NGINX Example

```nginx
upstream mozaiks {
    ip_hash;  # Sticky sessions
    server mozaiks-1:8000;
    server mozaiks-2:8000;
}

server {
    listen 443 ssl;
    server_name mozaiks.yourdomain.com;

    location / {
        proxy_pass http://mozaiks;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

---

## 7. Health Checks

### MozaiksAI Runtime Endpoints

```
GET /health          → 200 OK if healthy
GET /health/ready    → 200 OK if ready to accept traffic
GET /health/live     → 200 OK if process is alive
```

### Your Backend Health Check

```csharp
services.AddHealthChecks()
    .AddUrlGroup(
        new Uri("http://mozaiks:8000/health"),
        name: "mozaiks-runtime",
        failureStatus: HealthStatus.Degraded,
        timeout: TimeSpan.FromSeconds(5)
    );
```

---

## 8. Scaling

### Horizontal Scaling Rules

| Metric | Scale Up When | Scale Down When |
|--------|---------------|-----------------|
| CPU | > 70% for 2 min | < 30% for 5 min |
| Memory | > 80% for 2 min | < 40% for 5 min |
| Active WebSockets | > 1000 per pod | < 200 per pod |

### HPA (Kubernetes)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: mozaiks-hpa
  namespace: mozaiks
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mozaiks-runtime
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## 9. Monitoring

### Prometheus Scrape Config

```yaml
scrape_configs:
  - job_name: 'mozaiks-runtime'
    static_configs:
      - targets: ['mozaiks:8000']
    metrics_path: /metrics
```

### Key Metrics to Monitor

| Metric | Alert Threshold |
|--------|-----------------|
| `mozaiks_active_connections` | > 5000 |
| `mozaiks_workflow_errors_total` | > 10/min |
| `mozaiks_llm_latency_seconds` | p95 > 10s |
| `mozaiks_mongodb_latency_seconds` | p95 > 1s |

---

## 10. Checklist

### Development

- [ ] Docker Compose file created
- [ ] All environment variables defined
- [ ] MongoDB container running
- [ ] Health check passing (`curl http://localhost:8000/health`)
- [ ] Frontend can connect via WebSocket

### Production

- [ ] Kubernetes manifests applied
- [ ] Secrets stored securely (not in git)
- [ ] MongoDB Atlas configured
- [ ] Ingress with WebSocket support
- [ ] Sticky sessions enabled
- [ ] HPA configured
- [ ] Health checks integrated
- [ ] Monitoring dashboards set up

---

## 11. What You Don't Do

- Don't modify MozaiksAI source code
- Don't create MongoDB schemas (MozaiksAI handles that)
- Don't configure workflows (that's generator output)
- Don't implement business logic (Backend Agent does that)

Your job is just: **run the containers, configure networking, set environment variables**.
