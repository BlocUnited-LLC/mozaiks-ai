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
import os, socket, urllib.parse, logging
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from opentelemetry.trace import Status, StatusCode

try:
    from core.observability.performance_store import persist_span_summary, performance_persistence_enabled
except Exception:  # pragma: no cover
    def persist_span_summary(*_args, **_kwargs):  # type: ignore
        """Fallback no-op when performance_store import fails."""
        return None
    def performance_persistence_enabled() -> bool:  # type: ignore
        return False

_tracer = trace.get_tracer("telemetry")
_meter = get_meter("telemetry")
_hist_cache: Dict[str, Any] = {}
_telemetry_initialized = False
_DEF_UNIT = "s"

# Get logger for telemetry initialization
logger = logging.getLogger(__name__)

def ensure_telemetry_initialized(*, endpoint: Optional[str] = None, service_name: str = "app-service", environment: str = "production", service_version: str = "1.0.0", auto_disable_on_failure: bool = True, connection_test_timeout_sec: float = 0.6, enabled: bool = True) -> bool:
    """Idempotent initialization for OpenTelemetry + OpenLIT.

    Returns True if initialized (or already initialized), False if disabled.
    """
    global _telemetry_initialized
    
    logger.info("🔧 TELEMETRY_INIT: Starting telemetry initialization")
    
    if _telemetry_initialized:
        logger.info("✅ TELEMETRY_INIT: Already initialized, skipping")
        return True
        
    # Check OPENLIT_ENABLED environment variable first
    openlit_enabled_env = os.getenv("OPENLIT_ENABLED", "false").lower()
    logger.info(f"🔧 TELEMETRY_INIT: OPENLIT_ENABLED env var = '{openlit_enabled_env}'")
    
    # If OPENLIT_ENABLED is explicitly false, disable telemetry
    if openlit_enabled_env in ("false", "0", "no", "off"):
        logger.info("❌ TELEMETRY_INIT: OPENLIT_ENABLED is disabled, skipping telemetry initialization")
        enabled = False
        
    if not enabled:
        logger.info("❌ TELEMETRY_INIT: Telemetry disabled via enabled=False parameter")
        return False
    # Determine endpoint precedence: explicit argument > env > default
    env_ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    # Allow custom override via MOZAIKS_OTEL_ENDPOINT first
    final_endpoint = endpoint or os.getenv("MOZAIKS_OTEL_ENDPOINT") or env_ep or "http://localhost:4318"
    
    logger.info(f"🔧 TELEMETRY_INIT: Final endpoint = {final_endpoint}")
    logger.info(f"🔧 TELEMETRY_INIT: Service name = {service_name}")
    logger.info(f"🔧 TELEMETRY_INIT: Environment = {environment}")
    
    # Basic connectivity check to optionally disable noisy stack traces
    if auto_disable_on_failure:
        logger.info("🔧 TELEMETRY_INIT: Testing connectivity to OTEL endpoint...")
        try:
            parsed = urllib.parse.urlparse(final_endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port or (4318 if parsed.scheme.startswith("http") else 4317)
            logger.info(f"🔧 TELEMETRY_INIT: Connecting to {host}:{port} (timeout={connection_test_timeout_sec}s)")
            with socket.create_connection((host, port), timeout=connection_test_timeout_sec):
                pass
            logger.info("✅ TELEMETRY_INIT: Connectivity test passed")
        except Exception as e:
            logger.warning(f"❌ TELEMETRY_INIT: Connectivity test failed: {e}")
            logger.info("🔧 TELEMETRY_INIT: Disabling telemetry gracefully due to connectivity failure")
            # Disable gracefully
            os.environ["OTEL_TRACES_EXPORTER"] = "none"
            os.environ["OTEL_METRICS_EXPORTER"] = "none"
            os.environ["OTEL_LOGS_EXPORTER"] = "none"
            return False
    # Environment variables (only set if not already provided)
    logger.info("🔧 TELEMETRY_INIT: Setting OTEL environment variables")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", final_endpoint)
    # Decide protocol hints based on port if not already defined
    try:
        parsed = urllib.parse.urlparse(final_endpoint)
        port = parsed.port or (4318 if parsed.scheme.startswith("http") else 4317)
    except Exception:
        port = 4318
    # Only set defaults if caller has NOT explicitly set protocol envs already
    if not os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") and not os.getenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"):
        protocol = "grpc" if port == 4317 else "http/protobuf"
        logger.info(f"🔧 TELEMETRY_INIT: Auto-detected protocol = {protocol} (port={port})")
        if port == 4317:
            # gRPC default (do NOT force http/protobuf)
            os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
            os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "grpc")
            os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "grpc")
            os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "grpc")
        else:
            os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
            os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
            os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "http/protobuf")
            os.environ.setdefault("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "http/protobuf")
    else:
        logger.info("🔧 TELEMETRY_INIT: Using existing OTEL protocol environment variables")
    
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    os.environ.setdefault("OTEL_RESOURCE_ATTRIBUTES", f"deployment.environment={environment},service.version={service_version}")
    
    logger.info(f"🔧 TELEMETRY_INIT: OTEL_SERVICE_NAME = {os.environ.get('OTEL_SERVICE_NAME')}")
    logger.info(f"🔧 TELEMETRY_INIT: OTEL_RESOURCE_ATTRIBUTES = {os.environ.get('OTEL_RESOURCE_ATTRIBUTES')}")
    logger.info(f"🔧 TELEMETRY_INIT: OTEL_EXPORTER_OTLP_PROTOCOL = {os.environ.get('OTEL_EXPORTER_OTLP_PROTOCOL')}")
    # Initialize OpenLIT if available
    logger.info("🔧 TELEMETRY_INIT: Attempting to initialize OpenLIT...")
    try:
        import openlit  # type: ignore
        logger.info("✅ TELEMETRY_INIT: OpenLIT module imported successfully")
        openlit.init()
        logger.info("✅ TELEMETRY_INIT: OpenLIT initialized successfully")
    except ImportError as e:
        logger.warning(f"❌ TELEMETRY_INIT: OpenLIT not available (import failed): {e}")
    except Exception as e:
        logger.warning(f"❌ TELEMETRY_INIT: OpenLIT initialization failed: {e}")
        # Silent fail – instrumentation degrades gracefully
        pass
    
    _telemetry_initialized = True
    logger.info("✅ TELEMETRY_INIT: Telemetry initialization completed successfully")
    return True

def telemetry_status() -> Dict[str, Any]:  # type: ignore[name-defined]
    """Return a lightweight view of telemetry configuration without importing heavy exporters.

    This avoids raising if OTLP endpoint is absent. Values are sourced from environment so
    they reflect dynamic overrides performed in ensure_telemetry_initialized.
    """
    return {
        "initialized": _telemetry_initialized,
        "endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
        "service_name": os.getenv("OTEL_SERVICE_NAME"),
        "resource_attrs": os.getenv("OTEL_RESOURCE_ATTRIBUTES"),
        "protocol": os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL"),
        "traces_protocol": os.getenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"),
        "metrics_protocol": os.getenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL"),
        "logs_protocol": os.getenv("OTEL_EXPORTER_OTLP_LOGS_PROTOCOL"),
        "disabled": os.getenv("OTEL_TRACES_EXPORTER") == "none",
    }

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
            # Optional persistence of summary document
            try:
                if performance_persistence_enabled():
                    persist_span_summary(key, dur, attributes)
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
