"""Centralized OpenTelemetry / OpenLIT instrumentation helpers.

Refactor summary:
 - Telemetry & OpenLIT init logic relocated here (was in PerformanceManager.initialize)
 - Removed the hard-coded "mozaiks" prefix in span & metric names per organizational cleanup
 - Provided idempotent initialization via ensure_telemetry_initialized()
 - Exposed generic helpers: timed_span(), record_duration(), get_duration_hist()

Naming conventions now:
 - Span name: <key> (no prefix). If you want namespacing, pass dotted keys (e.g. "workflow.run").
 - Histogram name: <key>_duration_seconds (created lazily). Keys should be stable identifiers.
 - Span attribute for measured wall time always: duration_sec

This keeps PerformanceManager and orchestration code free of setup details.
"""
from __future__ import annotations
from contextlib import contextmanager
from time import perf_counter
from typing import Dict, Optional, Any
import os, socket, urllib.parse
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from opentelemetry.trace import Status, StatusCode

_tracer = trace.get_tracer("telemetry")
_meter = get_meter("telemetry")
_hist_cache: Dict[str, Any] = {}
_telemetry_initialized = False
_DEF_UNIT = "s"

def ensure_telemetry_initialized(*, endpoint: Optional[str] = None, service_name: str = "app-service", environment: str = "production", service_version: str = "1.0.0", auto_disable_on_failure: bool = True, connection_test_timeout_sec: float = 0.6, enabled: bool = True) -> bool:
    """Idempotent initialization for OpenTelemetry + OpenLIT.

    Returns True if initialized (or already initialized), False if disabled.
    """
    global _telemetry_initialized
    if _telemetry_initialized:
        return True
    if not enabled:
        return False
    # Determine endpoint precedence: explicit argument > env > default
    env_ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    final_endpoint = endpoint or env_ep or "http://localhost:4318"
    # Basic connectivity check to optionally disable noisy stack traces
    if auto_disable_on_failure:
        try:
            parsed = urllib.parse.urlparse(final_endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port or (4318 if parsed.scheme.startswith("http") else 4317)
            with socket.create_connection((host, port), timeout=connection_test_timeout_sec):
                pass
        except Exception:
            # Disable gracefully
            os.environ["OTEL_TRACES_EXPORTER"] = "none"
            return False
    # Environment variables (only set if not already provided)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", final_endpoint)
    if ":4318" in final_endpoint or final_endpoint.startswith("http://") or final_endpoint.startswith("https://"):
        os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
        os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
        os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "http/protobuf")
        os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "http/protobuf")
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    os.environ.setdefault("OTEL_RESOURCE_ATTRIBUTES", f"deployment.environment={environment},service.version={service_version}")
    # Initialize OpenLIT if available
    try:
        import openlit  # type: ignore
        openlit.init()
    except Exception:
        # Silent fail – instrumentation degrades gracefully
        pass
    _telemetry_initialized = True
    return True

def _get_hist(key: str, description: Optional[str] = None):
    name = f"{key}_duration_seconds" if not key.endswith("_duration_seconds") else key
    if name in _hist_cache:
        return _hist_cache[name]
    try:
        hist = _meter.create_histogram(name, description=description or f"Duration for {key}", unit=_DEF_UNIT)
    except Exception:
        hist = None
    _hist_cache[name] = hist
    return hist

def get_duration_hist(key: str, description: Optional[str] = None):
    """Public accessor for (lazily) creating/retrieving a duration histogram."""
    return _get_hist(key, description)

@contextmanager
def timed_span(key: str, *, attributes: Optional[Dict[str, Any]] = None, record_metric: bool = True):
    """Create a span + optional histogram duration metric.

    key: logical operation key (e.g., 'workflow.run', 'agent.factory')
    attributes: span + metric attributes
    record_metric: disable if only span desired
    """
    span_name = key  # cleaned (no vendor/app prefix)
    start = perf_counter()
    with _tracer.start_as_current_span(span_name) as span:
        if attributes:
            safe_attrs = {k: v for k, v in attributes.items() if isinstance(v, (str, bool, int, float))}
            try:
                span.set_attributes(safe_attrs)
            except Exception:
                pass
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        finally:
            dur = perf_counter() - start
            try:
                span.set_attribute("duration_sec", dur)
            except Exception:
                pass
            if record_metric:
                hist = _get_hist(key)
                if hist:
                    try:
                        safe_attrs = {k: v for k, v in (attributes or {}).items() if isinstance(v, (str, bool, int, float))}
                        hist.record(dur, safe_attrs)
                    except Exception:
                        pass

@contextmanager
def record_duration(key: str, attributes: Optional[Dict[str, Any]] = None):
    """Metric-only duration (no span)."""
    start = perf_counter()
    try:
        yield
    finally:
        dur = perf_counter() - start
        hist = _get_hist(key)
        if hist:
            try:
                safe_attrs = {k: v for k, v in (attributes or {}).items() if isinstance(v, (str, bool, int, float))}
                hist.record(dur, safe_attrs)
            except Exception:
                pass
