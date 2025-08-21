# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code
COPY . .

# Expose port
EXPOSE 8000

# OTEL/OpenLIT envs can be set at runtime; default no-op
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 \
    OPENLIT_ENABLED=false \
    LOGS_BASE_DIR=/app/logs/logs

# Run the app
CMD ["python", "run_server.py"]
