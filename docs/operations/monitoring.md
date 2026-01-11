# Monitoring & Observability Guide

**Purpose:** Configure comprehensive monitoring, alerting, and observability for production MozaiksAI deployments. Covers metrics collection, log aggregation, performance dashboards, and alerting strategies.

---

## Overview

MozaiksAI provides multi-layer observability:

- **Performance Metrics**: Real-time agent turns, token usage, cost tracking via PerformanceManager
- **Structured Logging**: Unified JSON logging with secret redaction and emoji-enhanced console output
- **Health Endpoints**: HTTP APIs for liveness, readiness, and performance aggregation
- **AG2 Runtime Logs**: Native Autogen file/SQLite logging for agent interactions
- **External Integration**: Custom metrics endpoints, log aggregation, monitoring dashboards

```mermaid
graph TB
    subgraph "MozaiksAI Runtime"
        APP[FastAPI App<br/>shared_app.py]
        PERF[PerformanceManager<br/>In-Memory Metrics]
        LOGS[LoggingConfig<br/>Structured Logs]
        AG2[AG2RuntimeLogger<br/>Agent Interactions]
    end
    
    subgraph "Metrics Endpoints"
        HEALTH[/health/active-runs]
        METRICS[/metrics/perf/aggregate]
    end
    
    subgraph "External Monitoring"
        UPTIME[Uptime Monitoring<br/>UptimeRobot/Pingdom]
        GRAFANA[Grafana<br/>Dashboards]
        ELK[ELK Stack<br/>Log Aggregation]
    end
    
    APP --> PERF
    APP --> LOGS
    APP --> AG2
    PERF --> HEALTH
    PERF --> METRICS
    
    HEALTH --> UPTIME
    METRICS --> GRAFANA
    LOGS --> ELK
    
    style PERF fill:#4a90e2
    style GRAFANA fill:#f39c12
    style ELK fill:#47a047
```

---

## Built-in Metrics & Endpoints

### PerformanceManager Overview

**Module:** `core/observability/performance_manager.py`

**Tracks Per-Chat Session:**
- Agent turns, tool calls, errors
- Token usage (prompt + completion)
- Cost (USD based on model pricing)
- Runtime duration, last turn performance

**Global Aggregates:**
- Active chats (currently running)
- Total tracked chats (lifetime)
- Cumulative tokens, cost, turns

---

### Health Check Endpoints

#### 1. Active Runs

**Endpoint:** `GET /health/active-runs`

**Purpose:** Liveness check showing current active chat sessions.

**Response:**
```json
{
  "active_runs": 2,
  "chats": [
    {
      "chat_id": "chat_abc123",
      "workflow": "Generator",
      "status": "running",
      "started_at": "2025-10-02T10:00:00Z"
    },
    {
      "chat_id": "chat_def456",
      "workflow": "DataAnalysis",
      "status": "running",
      "started_at": "2025-10-02T10:05:00Z"
    }
  ]
}
```

**Use Cases:**
- External uptime monitors (UptimeRobot, Pingdom)
- Load balancer health checks
- Kubernetes liveness probes

**Example (curl):**
```bash
curl http://localhost:8000/health/active-runs
```

---

#### 2. Generic Health Ping

**Endpoint:** `GET /api/health`

**Purpose:** Simple OK/NOT_OK response for basic availability checks.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-10-02T10:30:00Z"
}
```

**Use Cases:**
- Simple uptime monitors
- Quick sanity checks
- Minimal overhead health probe

---

### Performance Metrics Endpoints

#### 1. Aggregate Metrics

**Endpoint:** `GET /metrics/perf/aggregate`

**Purpose:** Snapshot of global performance metrics across all chats.

**Response:**
```json
{
  "active_chats": 3,
  "tracked_chats": 25,
  "total_agent_turns": 380,
  "total_tool_calls": 150,
  "total_errors": 2,
  "total_prompt_tokens": 560000,
  "total_completion_tokens": 280000,
  "total_cost": 15.75,
  "chats": [
    {
      "chat_id": "chat_abc123",
      "app_id": "acme_corp",
      "workflow_name": "Generator",
      "user_id": "user_456",
      "runtime_sec": 1200.5,
      "agent_turns": 18,
      "tool_calls": 9,
      "errors": 0,
      "prompt_tokens": 28000,
      "completion_tokens": 14000,
      "cost": 0.85,
      "status": "completed"
    }
  ]
}
```

**Use Cases:**
- Real-time dashboards (Grafana, internal monitoring UI)
- Cost tracking and budget alerts
- Performance trend analysis

**Example (curl):**
```bash
curl http://localhost:8000/metrics/perf/aggregate | jq
```

---

#### 2. All Chat Snapshots

**Endpoint:** `GET /metrics/perf/chats`

**Purpose:** Detailed list of all tracked chat sessions.

**Response:** Array of chat snapshot objects (same structure as `aggregate.chats`)

---

#### 3. Single Chat Snapshot

**Endpoint:** `GET /metrics/perf/chats/{chat_id}`

**Purpose:** Performance metrics for a specific chat session.

**Response:**
```json
{
  "chat_id": "chat_abc123",
  "app_id": "acme_corp",
  "workflow_name": "Generator",
  "user_id": "user_456",
  "started_at": "2025-10-02T10:00:00Z",
  "ended_at": "2025-10-02T10:20:00Z",
  "runtime_sec": 1200.5,
  "agent_turns": 18,
  "tool_calls": 9,
  "errors": 0,
  "last_turn_duration_sec": 2.5,
  "prompt_tokens": 28000,
  "completion_tokens": 14000,
  "cost": 0.85
}
```

**Example:**
```bash
curl http://localhost:8000/metrics/perf/chats/chat_abc123 | jq
```

---

## Log Aggregation

### Structured Logging Overview

**Logger Types:**

1. **workflow_execution**: Workflow lifecycle events (start, end, agent turns)
2. **performance**: Metrics and timing data
3. **autogen_file**: AG2 agent interactions (via patched file logger)
4. **tools**: Tool invocations and responses
5. **core**: Core runtime events (startup, shutdown, config)

**Log Formats:**

- **Development**: Pretty-printed console with emoji prefixes
- **Production**: JSON Lines (JSONL) for log aggregation tools

**Environment Control:**

```bash
# Enable JSON logging
LOGS_AS_JSON=true

# Set log directory
LOGS_BASE_DIR=/var/log/mozaiksai
```

---

### Log File Locations

**Docker Deployment:**
```
logs/logs/
├── workflow_execution.log   # Workflow events
├── performance.log           # Metrics
├── autogen_file.log         # AG2 agent logs
└── tools.log                # Tool execution
```

**Systemd Deployment:**
```
/var/log/mozaiksai/
├── app.log                  # Combined stdout
├── app-error.log            # stderr only
└── logs/                    # Structured logs (same as Docker)
    ├── workflow_execution.log
    ├── performance.log
    └── ...
```

---

### ELK Stack Integration

**Architecture:**

```
MozaiksAI Logs (JSONL) → Filebeat → Logstash → Elasticsearch → Kibana
```

---

#### 1. Install Elasticsearch

```bash
# Ubuntu/Debian
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
sudo sh -c 'echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" > /etc/apt/sources.list.d/elastic-8.x.list'
sudo apt-get update
sudo apt-get install elasticsearch

# Start Elasticsearch
sudo systemctl enable elasticsearch
sudo systemctl start elasticsearch

# Verify
curl -X GET "localhost:9200"
```

---

#### 2. Install Filebeat

```bash
# Install
sudo apt-get install filebeat

# Configure Filebeat (/etc/filebeat/filebeat.yml)
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /opt/mozaiksai/logs/logs/*.log
    json.keys_under_root: true
    json.add_error_key: true
    fields:
      app: mozaiksai
      env: production

output.elasticsearch:
  hosts: ["localhost:9200"]
  index: "mozaiksai-%{+yyyy.MM.dd}"

setup.template.name: "mozaiksai"
setup.template.pattern: "mozaiksai-*"

# Start Filebeat
sudo systemctl enable filebeat
sudo systemctl start filebeat
```

---

#### 3. Install Kibana

```bash
# Install
sudo apt-get install kibana

# Configure (/etc/kibana/kibana.yml)
server.host: "0.0.0.0"
elasticsearch.hosts: ["http://localhost:9200"]

# Start Kibana
sudo systemctl enable kibana
sudo systemctl start kibana

# Access: http://localhost:5601
```

---

#### 4. Create Kibana Index Pattern

1. Navigate to Kibana UI → Stack Management → Index Patterns
2. Create pattern: `mozaiksai-*`
3. Select timestamp field: `ts` (or `@timestamp` if using Filebeat default)
4. Discover logs: Kibana → Discover → Select `mozaiksai-*`

---

#### 5. Kibana Visualizations

**Example: Agent Turns Over Time**

- Visualization Type: Line Chart
- X-Axis: Date Histogram (`ts`, 1-minute intervals)
- Y-Axis: Count of documents where `msg` contains "agent_turn"

**Example: Error Rate Dashboard**

- Visualization Type: Metric
- Aggregation: Count
- Filter: `level: ERROR`
- Time Range: Last 1 hour

---

### Fluentd Alternative

**docker-compose.yml with Fluentd:**

```yaml
services:
  app:
    logging:
      driver: "fluentd"
      options:
        fluentd-address: localhost:24224
        fluentd-async: "true"
        tag: mozaiksai.app

  fluentd:
    image: fluent/fluentd:v1.16
    ports:
      - "24224:24224"
    volumes:
      - ./fluentd/fluent.conf:/fluentd/etc/fluent.conf
      - /var/log/fluentd:/var/log/fluentd
```

**fluentd.conf:**

```ruby
<source>
  @type forward
  port 24224
</source>

<filter mozaiksai.**>
  @type parser
  key_name log
  <parse>
    @type json
  </parse>
</filter>

<match mozaiksai.**>
  @type elasticsearch
  host elasticsearch
  port 9200
  index_name mozaiksai
  type_name _doc
  logstash_format true
  logstash_prefix mozaiksai
</match>
```

---

## Alerting Strategies

### Prometheus Alertmanager

**1. Install Alertmanager:**

```bash
wget https://github.com/prometheus/alertmanager/releases/download/v0.26.0/alertmanager-0.26.0.linux-amd64.tar.gz
tar xvfz alertmanager-0.26.0.linux-amd64.tar.gz
sudo cp alertmanager-0.26.0.linux-amd64/alertmanager /usr/local/bin/
```

**2. Configure Alertmanager (`/etc/prometheus/alertmanager.yml`):**

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@mozaiks.com'
  smtp_auth_username: 'alerts@mozaiks.com'
  smtp_auth_password: 'your_password'

route:
  receiver: 'email-admin'
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: 'email-admin'
    email_configs:
      - to: 'admin@mozaiks.com'
        headers:
          Subject: '[MozaiksAI] {{ .GroupLabels.alertname }}'

  - name: 'slack-ops'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
        channel: '#ops-alerts'
        title: 'MozaiksAI Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
```

**3. Define Alert Rules (`/etc/prometheus/alerts.yml`):**

```yaml
groups:
  - name: mozaiksai_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: (sum(rate(mozaiks_chat_errors_total[5m])) / sum(rate(mozaiks_chat_agent_turns_total[5m]))) * 100 > 5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }}% (threshold: 5%)"

      # Cost budget exceeded
      - alert: DailyCostExceeded
        expr: increase(mozaiks_chat_cost_usd_total[24h]) > 100
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Daily cost budget exceeded"
          description: "24h cost is ${{ $value }} (budget: $100)"

      # Service down
      - alert: ServiceDown
        expr: up{job="mozaiksai"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "MozaiksAI service is down"
          description: "Prometheus cannot scrape metrics endpoint"

      # High active chats (capacity)
      - alert: HighConcurrency
        expr: mozaiks_active_chats > 50
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High concurrent chat sessions"
          description: "{{ $value }} active chats (threshold: 50)"

      # Slow agent turns
      - alert: SlowAgentTurns
        expr: avg(mozaiks_chat_last_turn_duration_sec) > 10
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "Slow agent turn performance"
          description: "Average turn duration: {{ $value }}s (threshold: 10s)"
```

**4. Link Alerts to Prometheus:**

**Update `/etc/prometheus/prometheus.yml`:**

```yaml
rule_files:
  - "/etc/prometheus/alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']
```

**5. Start Alertmanager:**

```bash
# Systemd service (/etc/systemd/system/alertmanager.service)
[Unit]
Description=Prometheus Alertmanager
After=network.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/alertmanager \
  --config.file=/etc/prometheus/alertmanager.yml \
  --storage.path=/var/lib/alertmanager

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable alertmanager
sudo systemctl start alertmanager

# Access: http://localhost:9093
```

---

### Uptime Monitoring (External)

**UptimeRobot:**

1. Create account at https://uptimerobot.com
2. Add HTTP(s) monitor: `https://mozaiks.yourdomain.com/health/active-runs`
3. Configure alert contacts (email, SMS, Slack)
4. Set check interval: 1 minute
5. Enable notifications on downtime

**Pingdom:**

1. Create account at https://www.pingdom.com
2. Add Uptime Check: `https://mozaiks.yourdomain.com/api/health`
3. Set check interval: 1 minute
4. Configure integrations (Slack, PagerDuty)

---

## Performance Monitoring Best Practices

### 1. Define SLOs (Service Level Objectives)

**Availability:**
- Target: 99.9% uptime (8.76 hours downtime/year)
- Measured: `up{job="mozaiksai"}` metric

**Latency:**
- Target: 95% of agent turns complete < 5 seconds
- Measured: `histogram_quantile(0.95, mozaiks_chat_last_turn_duration_sec)`

**Error Rate:**
- Target: < 1% errors per agent turn
- Measured: `(sum(rate(mozaiks_chat_errors_total[5m])) / sum(rate(mozaiks_chat_agent_turns_total[5m]))) * 100 < 1`

**Cost:**
- Target: < $500/day
- Measured: `increase(mozaiks_chat_cost_usd_total[24h]) < 500`

---

### 2. Set Up Alerts for SLO Violations

```yaml
# Alert when SLO violated for 5+ minutes
- alert: SLOAvailabilityViolation
  expr: avg_over_time(up{job="mozaiksai"}[5m]) < 0.999
  for: 5m
  labels:
    severity: critical
```

---

### 3. Monitor Resource Utilization

**CPU Usage:**
```promql
rate(process_cpu_seconds_total{job="mozaiksai"}[5m]) * 100
```

**Memory Usage:**
```promql
process_resident_memory_bytes{job="mozaiksai"} / 1024 / 1024
```

**Disk I/O:**
```bash
# Monitor MongoDB disk usage
docker exec mozaiksai-mongo du -sh /data/db
```

---

### 4. Track Business Metrics

**Metrics to Track:**
- Chats per user
- Workflows per app
- Average session duration
- Token consumption by workflow
- Cost per user/app

**Custom Prometheus Metrics (Future):**

```python
from prometheus_client import Counter, Histogram, Gauge

# Custom metrics
workflow_starts = Counter('mozaiksai_workflow_starts_total', 'Workflow starts', ['workflow', 'app'])
session_duration = Histogram('mozaiksai_session_duration_seconds', 'Session duration', ['workflow'])
concurrent_users = Gauge('mozaiksai_concurrent_users', 'Concurrent users')

# Increment
workflow_starts.labels(workflow='Generator', app='acme_corp').inc()
```

---

## Troubleshooting Monitoring Issues

### Prometheus Not Scraping

**Check Target Status:**

```bash
# Visit Prometheus UI
http://localhost:9090/targets

# Look for "UP" status for mozaiksai job
# If "DOWN", check:
```

**1. Backend is running:**
```bash
curl http://localhost:8000/metrics/prometheus
```

**2. Firewall allows scraping:**
```bash
sudo ufw allow 8000/tcp
```

**3. Prometheus config correct:**
```yaml
# Verify scrape_configs in /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'mozaiksai'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics/prometheus'
```

---

### Logs Not Appearing in Kibana

**Check Filebeat Status:**

```bash
sudo systemctl status filebeat
sudo journalctl -u filebeat -f
```

**Verify Log Format:**

```bash
# Ensure logs are JSON
cat /opt/mozaiksai/logs/logs/workflow_execution.log | head -1 | jq

# If not JSON, set env var:
LOGS_AS_JSON=true
```

**Check Elasticsearch Index:**

```bash
# List indices
curl -X GET "localhost:9200/_cat/indices?v"

# Should see: mozaiksai-2025.10.02
```

---

### High Memory Usage (PerformanceManager)

**Flush Metrics More Frequently:**

```python
# In core/observability/performance_manager.py
# Change flush_interval_sec from 300 to 60
perf_mgr = PerformanceManager(flush_interval_sec=60)
```

**Clear Completed Chats:**

```python
# Add periodic cleanup in PerformanceManager
async def _cleanup_old_chats(self):
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    to_remove = [
        chat_id for chat_id, state in self._states.items()
        if state.ended_at and state.ended_at < cutoff
    ]
    for chat_id in to_remove:
        del self._states[chat_id]
```

---

## Monitoring Checklist

### Initial Setup

- [ ] PerformanceManager initialized in shared_app.py startup
- [ ] Health endpoints accessible (`/health/active-runs`, `/api/health`)
- [ ] Prometheus metrics endpoint responding (`/metrics/prometheus`)
- [ ] Structured logging enabled (`LOGS_AS_JSON=true`)
- [ ] Log directory writable and mounted (Docker volumes)

### Prometheus & Grafana

- [ ] Prometheus installed and scraping MozaiksAI
- [ ] Grafana installed with Prometheus data source
- [ ] MozaiksAI dashboard imported
- [ ] Alert rules defined (`alerts.yml`)
- [ ] Alertmanager configured (email/Slack)

### Log Aggregation

- [ ] Elasticsearch installed and running
- [ ] Filebeat configured to ship logs
- [ ] Kibana index pattern created (`mozaiksai-*`)
- [ ] Visualizations created (error rate, agent turns, cost)

### External Monitoring

- [ ] Uptime monitor configured (UptimeRobot/Pingdom)
- [ ] Alerting contacts configured (email, SMS, Slack)
- [ ] SSL certificate monitoring enabled (expiry alerts)

### Ongoing Maintenance

- [ ] Review dashboards weekly for anomalies
- [ ] Rotate logs monthly (logrotate)
- [ ] Archive old Elasticsearch indices (>30 days)
- [ ] Test alert delivery quarterly
- [ ] Update SLO targets based on actual performance

---

## Next Steps

- **[Troubleshooting Guide](troubleshooting.md)** - Debug common issues with logs and metrics
- **[Performance Tuning](performance_tuning.md)** - Optimize for scale and efficiency
- **[Deployment Guide](deployment.md)** - Production deployment patterns
- **[Observability Deep Dive](../runtime/observability.md)** - Technical implementation details
- **[Configuration Reference](../runtime/configuration_reference.md)** - All environment variables
