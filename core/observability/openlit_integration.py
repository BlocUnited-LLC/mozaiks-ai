"""
OpenLit Observability Integration for MozaiksAI
TECHNICAL MONITORING: APM-style observability for system performance, errors, and health.

Role in Architecture:
- PersistenceManager: Stores WHAT happened (messages, sessions, state)
- PerformanceManager: Tracks HOW MUCH it cost (tokens, $$$, efficiency)
- OpenLitObservability: Monitors HOW WELL it performed (speed, errors, health)

This provides APM-style monitoring with tracing, metrics, and error tracking
separate from business metrics and data persistence.
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

# OpenTelemetry imports for OpenLit integration
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from logs.logging_config import get_business_logger

logger = get_business_logger("openlit_observability")

@dataclass
class OpenLitConfig:
    """Configuration for OpenLit observability"""
    endpoint: str = "http://localhost:4317"  # OpenLit endpoint
    service_name: str = "mozaiks-ai"
    service_version: str = "1.0.0"
    environment: str = "production"
    enable_traces: bool = True
    enable_metrics: bool = True
    export_interval_seconds: int = 30


class OpenLitObservability:
    """
    OpenLit observability integration that exports telemetry data
    WITHOUT interfering with business persistence logic.
    """
    
    def __init__(self, config: Optional[OpenLitConfig] = None):
        self.config = config or OpenLitConfig()
        self.tracer = None
        self.meter = None
        self.initialized = False
        
        # Production span context tracking
        self.active_spans: Dict[str, Any] = {}
        self.span_contexts: Dict[str, Any] = {}
        
        # Metrics
        self.workflow_counter = None
        self.token_counter = None
        self.cost_histogram = None
        self.duration_histogram = None
        
        logger.info(f"🔭 OpenLit observability initialized: {self.config.service_name}")

    async def initialize(self):
        """Initialize OpenLit telemetry exporters"""
        try:
            if self.config.enable_traces:
                # Setup trace provider with OpenLit exporter
                trace_exporter = OTLPSpanExporter(
                    endpoint=self.config.endpoint,
                    headers={"service.name": self.config.service_name}
                )
                
                tracer_provider = TracerProvider()
                span_processor = BatchSpanProcessor(trace_exporter)
                tracer_provider.add_span_processor(span_processor)
                
                trace.set_tracer_provider(tracer_provider)
                self.tracer = trace.get_tracer(
                    self.config.service_name,
                    self.config.service_version
                )
            
            if self.config.enable_metrics:
                # Setup metrics provider with OpenLit exporter
                metric_exporter = OTLPMetricExporter(
                    endpoint=self.config.endpoint,
                    headers={"service.name": self.config.service_name}
                )
                
                metric_reader = PeriodicExportingMetricReader(
                    exporter=metric_exporter,
                    export_interval_millis=self.config.export_interval_seconds * 1000
                )
                
                meter_provider = MeterProvider(metric_readers=[metric_reader])
                metrics.set_meter_provider(meter_provider)
                
                self.meter = metrics.get_meter(
                    self.config.service_name,
                    self.config.service_version
                )
                
                # Create metrics
                self.workflow_counter = self.meter.create_counter(
                    name="mozaiks_workflows_total",
                    description="Total number of workflows executed",
                    unit="1"
                )
                
                self.token_counter = self.meter.create_counter(
                    name="mozaiks_tokens_total", 
                    description="Total tokens consumed",
                    unit="1"
                )
                
                self.cost_histogram = self.meter.create_histogram(
                    name="mozaiks_cost_usd",
                    description="Cost of workflow execution in USD",
                    unit="USD"
                )
                
                self.duration_histogram = self.meter.create_histogram(
                    name="mozaiks_duration_ms",
                    description="Duration of workflow execution in milliseconds", 
                    unit="ms"
                )
            
            self.initialized = True
            logger.info(f"✅ OpenLit observability ready: traces={self.config.enable_traces}, metrics={self.config.enable_metrics}")
            
        except Exception as e:
            logger.error(f"❌ OpenLit initialization failed: {e}")
            self.initialized = False

    async def trace_workflow_execution(self, workflow_name: str, chat_id: str, 
                                     enterprise_id: str, user_id: str) -> str:
        """Create OpenLit trace for workflow execution with proper span context management"""
        if not self.initialized or not self.tracer:
            return ""
        
        try:
            trace_id = str(uuid.uuid4())
            
            span = self.tracer.start_span(
                f"workflow.{workflow_name}",
                attributes={
                    "workflow.name": workflow_name,
                    "chat.id": chat_id,
                    "enterprise.id": enterprise_id,
                    "user.id": user_id,
                    "service.name": self.config.service_name,
                    "service.version": self.config.service_version,
                    "environment": self.config.environment,
                    "trace.id": trace_id
                }
            )
            
            # Store span and context for production management
            self.active_spans[trace_id] = span
            self.span_contexts[trace_id] = {
                "span": span,
                "workflow_name": workflow_name,
                "chat_id": chat_id,
                "start_time": datetime.utcnow(),
                "status": "active"
            }
            
            span.set_status(Status(StatusCode.OK))
            logger.debug(f"🔍 OpenLit trace started: {trace_id} for {workflow_name}")
            return trace_id
                
        except Exception as e:
            logger.error(f"❌ OpenLit trace creation failed: {e}")
            return ""

    async def export_session_metrics(self, session_data: Dict[str, Any]):
        """Export session performance metrics to OpenLit"""
        if not self.initialized or not self.meter:
            return
        
        try:
            workflow_name = session_data.get("workflow_name", "unknown")
            total_tokens = session_data.get("total_tokens", 0)
            total_cost = session_data.get("total_cost", 0.0)
            duration_ms = session_data.get("duration_ms", 0)
            success = session_data.get("success", True)
            
            # Common attributes
            attributes = {
                "workflow.name": workflow_name,
                "service.name": self.config.service_name,
                "environment": self.config.environment,
                "success": str(success).lower()
            }
            
            # Export metrics
            if self.workflow_counter:
                self.workflow_counter.add(1, attributes)
            
            if self.token_counter and total_tokens > 0:
                self.token_counter.add(total_tokens, attributes)
            
            if self.cost_histogram and total_cost > 0:
                self.cost_histogram.record(total_cost, attributes)
            
            if self.duration_histogram and duration_ms > 0:
                self.duration_histogram.record(duration_ms, attributes)
            
            logger.debug(f"📊 OpenLit metrics exported: {workflow_name} | {total_tokens} tokens | ${total_cost:.6f}")
            
        except Exception as e:
            logger.error(f"❌ OpenLit metrics export failed: {e}")

    async def update_observability_in_session(self, chat_id: str, enterprise_id: str, 
                                            trace_id: str, metrics_exported: bool = True):
        """Update observability data in ChatSessions for reference"""
        try:
            from core.data.persistence_manager import PersistenceManager
            persistence = PersistenceManager()
            
            observability_update = {
                "observability": {
                    "trace_id": trace_id,
                    "metrics_exported": metrics_exported,
                    "last_export": datetime.utcnow(),
                    "export_count": 1
                }
            }
            
            await persistence.update_real_time_tracking(
                chat_id,
                enterprise_id,
                observability_update
            )
            
            logger.debug(f"🔗 Updated observability reference in ChatSessions: {trace_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update observability reference: {e}")

    async def finalize_trace(self, trace_id: str, success: bool = True, 
                           error_message: Optional[str] = None):
        """Finalize OpenLit trace with proper span context management"""
        if not self.initialized or not self.tracer or trace_id not in self.span_contexts:
            return
        
        try:
            span_context = self.span_contexts[trace_id]
            span = span_context["span"]
            
            # Set final span status
            if success:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, error_message or "Workflow failed"))
                if error_message:
                    span.set_attribute("error.message", error_message)
            
            # Calculate duration
            duration = (datetime.utcnow() - span_context["start_time"]).total_seconds() * 1000
            span.set_attribute("duration.ms", duration)
            
            # End the span properly
            span.end()
            
            # Clean up tracking
            del self.active_spans[trace_id]
            del self.span_contexts[trace_id]
            
            logger.debug(f"🏁 OpenLit trace finalized: {trace_id} ({'success' if success else 'failed'}) in {duration:.2f}ms")
            
        except Exception as e:
            logger.error(f"❌ OpenLit trace finalization failed: {e}")
            
    async def add_span_event(self, trace_id: str, event_name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add event to active span for detailed tracing"""
        if trace_id in self.active_spans:
            try:
                span = self.active_spans[trace_id]
                span.add_event(event_name, attributes or {})
                logger.debug(f"📝 Added span event: {event_name} to trace {trace_id}")
            except Exception as e:
                logger.error(f"❌ Failed to add span event: {e}")


# Global observability instance
_openlit_instance: Optional[OpenLitObservability] = None

async def get_openlit_observability() -> OpenLitObservability:
    """Get or create global OpenLit observability instance"""
    global _openlit_instance
    
    if _openlit_instance is None:
        _openlit_instance = OpenLitObservability()
        await _openlit_instance.initialize()
    
    return _openlit_instance

async def export_workflow_observability(workflow_name: str, chat_id: str, 
                                       enterprise_id: str, user_id: str,
                                       session_data: Dict[str, Any]) -> str:
    """
    Export complete workflow observability data to OpenLit.
    Returns trace_id for reference.
    """
    try:
        observability = await get_openlit_observability()
        
        # Create trace
        trace_id = await observability.trace_workflow_execution(
            workflow_name, chat_id, enterprise_id, user_id
        )
        
        # Export metrics
        await observability.export_session_metrics(session_data)
        
        # Update reference in ChatSessions
        await observability.update_observability_in_session(
            chat_id, enterprise_id, trace_id, True
        )
        
        logger.info(f"🔭 Complete observability exported: {workflow_name} | trace: {trace_id}")
        return trace_id
        
    except Exception as e:
        logger.error(f"❌ Observability export failed: {e}")
        return ""
