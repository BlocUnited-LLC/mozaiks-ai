# ==============================================================================
# FILE: shared_app.py
# DESCRIPTION: FastAPI app - workflow agnostic, tools handled by workflows
# ==============================================================================
import logging
import os
import sys
from typing import Optional, Any, List, Dict
from datetime import datetime, timedelta, UTC
from pathlib import Path
# Ensure project root is on Python path for workflow imports
sys.path.insert(0, str(Path(__file__).parent))
import json
import asyncio
from fastapi import FastAPI, HTTPException, Request, WebSocket
from starlette.middleware.cors import CORSMiddleware
from bson.objectid import ObjectId
from uuid import uuid4
import autogen
from core.core_config import get_mongo_client
from core.transport.simple_transport import SimpleTransport
from core.workflow.workflow_manager import workflow_status_summary, get_workflow_transport, get_workflow_tools
from core.data.persistence.persistence_manager import AG2PersistenceManager, InvalidEnterpriseIdError
from core.data.themes.theme_manager import ThemeManager, ThemeResponse
from core.workflow.dependencies import dependency_manager

# Initialize persistence manager (handles lean chat session storage internally)
persistence_manager = AG2PersistenceManager()
theme_manager = ThemeManager(persistence_manager.persistence)

async def _chat_coll():
    """Return the new lean chat_sessions collection (lowercase)."""
    # Delegate to the persistence manager's internal helper (ensures client)
    return await persistence_manager._coll()

# Import our custom logging setup
from logs.logging_config import (
    setup_development_logging, 
    setup_production_logging, 
    get_workflow_logger,
)

# Setup logging based on environment ASAP (before any KV/DB work)
env = os.getenv("ENVIRONMENT", "development").lower()

if env == "production":
    setup_production_logging()
    get_workflow_logger("shared_app_setup").info(
        "LOGGING_CONFIGURED: Production logging configuration applied"
    )
else:
    setup_development_logging()
    get_workflow_logger("shared_app_setup").info(
        "LOGGING_CONFIGURED: Development logging configuration applied"
    )

# (Startup log moved below after business_logger is defined)

# Set autogen library logging to DEBUG for detailed output
logging.getLogger('autogen').setLevel(logging.DEBUG)

# Get specialized loggers
wf_logger = get_workflow_logger("shared_app")
performance_logger = get_workflow_logger("performance.shared_app")
logger = logging.getLogger(__name__)

# Log AG2 version for debugging
wf_logger.info(f"🔍 autogen version: {getattr(autogen, '__version__', 'unknown')}")

# Emit an explicit startup log line so file logging can be verified quickly
wf_logger.info(f"SERVER_STARTUP_INIT: Starting MozaiksAI in {env} mode")

# ---------------------------------------------------------------------------
# Patch Autogen file logger to tolerate non-serializable objects
# ---------------------------------------------------------------------------
def _patch_autogen_file_logger() -> None:
    try:
        from autogen.logger import file_logger as _file_logger
        from autogen.logger.logger_utils import get_current_ts as _logger_ts
    except Exception as patch_err:  # pragma: no cover - defensive safeguard
        wf_logger.debug(f"Skipped Autogen file_logger patch: {patch_err}")
        return

    # Use an Any-typed alias to avoid static type errors on dynamic attributes
    FL: Any = _file_logger.FileLogger

    if getattr(FL, "_mozaiks_safe_json", False):
        return

    import json as _json
    import threading as _threading

    safe_serialize = _file_logger.safe_serialize

    def _serialize_wrapper_payload(wrapper, session_id, thread_id, init_args):
        return _json.dumps({
            "wrapper_id": id(wrapper),
            "session_id": session_id,
            "json_state": safe_serialize(init_args or {}),
            "timestamp": _logger_ts(),
            "thread_id": thread_id,
        })

    def _serialize_client_payload(client, wrapper, session_id, thread_id, init_args):
        return _json.dumps({
            "client_id": id(client),
            "wrapper_id": id(wrapper),
            "session_id": session_id,
            "class": type(client).__name__,
            "json_state": safe_serialize(init_args or {}),
            "timestamp": _logger_ts(),
            "thread_id": thread_id,
        })

    def _patched_log_new_wrapper(self, wrapper, init_args=None):
        thread_id = _threading.get_ident()
        try:
            payload = _serialize_wrapper_payload(wrapper, self.session_id, thread_id, init_args)
            self.logger.info(payload)
        except Exception as exc:  # pragma: no cover - logging fallback
            self.logger.error(f"[file_logger] Failed to log event {exc}")

    def _patched_log_new_client(self, client, wrapper, init_args):
        thread_id = _threading.get_ident()
        try:
            payload = _serialize_client_payload(client, wrapper, self.session_id, thread_id, init_args)
            self.logger.info(payload)
        except Exception as exc:  # pragma: no cover - logging fallback
            self.logger.error(f"[file_logger] Failed to log event {exc}")

    # Monkey patch methods and set a marker attribute
    FL.log_new_wrapper = _patched_log_new_wrapper  # type: ignore[attr-defined]
    FL.log_new_client = _patched_log_new_client  # type: ignore[attr-defined]
    setattr(FL, "_mozaiks_safe_json", True)
    wf_logger.info("Patched Autogen FileLogger for safe JSON serialization")


_patch_autogen_file_logger()

# Initialize unified event dispatcher
from core.events import get_event_dispatcher
event_dispatcher = get_event_dispatcher()
wf_logger.info("🎯 Unified Event Dispatcher initialized")

from core.observability.performance_manager import get_performance_manager
from core.workflow.orchestration_patterns import get_run_registry_summary

# FastAPI app
app = FastAPI(
    title="MozaiksAI Runtime",
    description="Production-ready AG2 runtime with workflow-specific tools",
    version="5.0.0",
)

# Allow CORS for all origins (e.g., test_client.html local file)
app.add_middleware(
    CORSMiddleware,
    # Allow all origins, including file:// (null); using regex for full coverage
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mongo_client = None  # delay until startup so logging is definitely initialized
simple_transport: Optional[SimpleTransport] = None


@app.get("/api/themes/{enterprise_id}", response_model=ThemeResponse)
async def get_enterprise_theme(enterprise_id: str):
    try:
        return await theme_manager.get_theme(enterprise_id)
    except InvalidEnterpriseIdError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("THEME_FETCH_FAILED")
        raise HTTPException(status_code=500, detail="Failed to load theme") from exc


@app.get("/health/active-runs")
async def health_active_runs():
    """Return summary of active runs (in-memory registry)."""
    try:
        return get_run_registry_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/perf/aggregate")
async def metrics_perf_aggregate():
    """Return aggregate in-memory performance counters (no DB hits)."""
    try:
        perf_mgr = await get_performance_manager()
        return await perf_mgr.aggregate()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect aggregate metrics: {e}")

@app.get("/metrics/perf/chats")
async def metrics_perf_chats():
    """Return per-chat in-memory performance snapshots."""
    try:
        perf_mgr = await get_performance_manager()
        return await perf_mgr.snapshot_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect chat metrics: {e}")

@app.get("/metrics/perf/chats/{chat_id}")
async def metrics_perf_chat(chat_id: str):
    try:
        perf_mgr = await get_performance_manager()
        snap = await perf_mgr.snapshot_chat(chat_id)
        if not snap:
            raise HTTPException(status_code=404, detail="Chat not tracked")
        return snap
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect chat metric: {e}")


# # ------------------------------------------------------------------------------
# # SERVICE REGISTRY (backend-agnostic routing for artifact modules)
# # Map logical service names -> base URLs. Change via env vars per environment.
# # ------------------------------------------------------------------------------
# import httpx  # HTTP client for proxying requests
# SERVICE_REGISTRY = {
#     # Most of your app is .NET — point this to your .NET gateway/base URL.
#     # e.g., "http://localhost:5000" or "https://api.mycorp.internal"
#     "dotnet": os.getenv("DOTNET_BASE", "http://localhost:5000"),

#     # Your FastAPI (this app) can also be targeted by name if you want:
#     "fastapi": os.getenv("FASTAPI_BASE", "http://localhost:8000"),
#     # Add more services as needed:
#     # "java": os.getenv("JAVA_BASE", "http://java-service:8080"),
# }


@app.on_event("startup")
async def startup():
    """Initialize application on startup."""
    global simple_transport
    startup_start = datetime.now(UTC)
    
    wf_logger.info("🚀 APP_STARTUP: FastAPI startup event triggered")
    wf_logger.info(f"🔧 APP_STARTUP: Environment = {env}")
    
    # -----------------------------
    # Cache behavior controls (expert defaults)
    # - Tools: clear on start in development by default so tool edits take effect
    # - LLM: do NOT clear by default; allow opt-in via env
    #   Use LLM_CONFIG_CACHE_TTL env to tighten dev TTL (e.g., 0) if desired
    # -----------------------------
    def _env_bool(name: str, default: bool = False) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return str(val).lower() in ("1", "true", "yes", "y", "on")

    # Clear workflow tool module cache on startup (default ON in dev)
    try:
        clear_tools = _env_bool("CLEAR_TOOL_CACHE_ON_START", default=(env != "production"))
        if clear_tools:
            from core.workflow.agents.tools import clear_tool_cache
            cleared = clear_tool_cache()  # clear all workflow tool modules
            wf_logger.info(f"🧹 TOOL_CACHE: Cleared {cleared} cached tool modules on startup")
        else:
            wf_logger.info("🧹 TOOL_CACHE: Preserve cached tool modules (CLEAR_TOOL_CACHE_ON_START=0)")
    except Exception as e:
        wf_logger.error("TOOL_CACHE_CLEAR_FAILED: Failed to clear tool cache on startup", error=str(e))

    # Optional: clear LLM caches on startup (default OFF)
    try:
        if _env_bool("CLEAR_LLM_CACHES_ON_START", default=False):
            from core.workflow.validation.llm_config import clear_llm_caches
            clear_llm_caches(raw=True, built=True)
            wf_logger.info("🧹 LLM_CACHE: Cleared raw and built llm_config caches on startup")
        # Log effective TTL to aid ops visibility
        ttl = os.getenv("LLM_CONFIG_CACHE_TTL", "300")
        wf_logger.info(f"⏱️ LLM_CACHE: Effective TTL (secs) = {ttl}")
    except Exception as e:
        wf_logger.error("LLM_CACHE_CLEAR_FAILED: Failed LLM cache management on startup", error=str(e))
    
    try:
        # Initialize performance / observability
        wf_logger.info("🔧 APP_STARTUP: Initializing performance manager...")
        perf_mgr = await get_performance_manager()
        await perf_mgr.initialize()
        wf_logger.info("✅ APP_STARTUP: Performance manager initialized")

        # Initialize simple transport
        streaming_start = datetime.now(UTC)
        simple_transport = await SimpleTransport.get_instance()
        streaming_time = (datetime.now(UTC) - streaming_start).total_seconds() * 1000
        performance_logger.info(
            "streaming_config_init_duration",
            metric_name="streaming_config_init_duration",
            value=float(streaming_time),
            config_keys=[],
            streaming_enabled=True,
        )

        # Build Mongo client now (after logging configured)
        global mongo_client
        if mongo_client is None:
            mongo_client = get_mongo_client()

        # Test MongoDB connection
        mongo_start = datetime.now(UTC)
        try:
            await mongo_client.admin.command("ping")
            mongo_time = (datetime.now(UTC) - mongo_start).total_seconds() * 1000
            performance_logger.info(
                "mongodb_ping_duration",
                metric_name="mongodb_ping_duration",
                value=float(mongo_time),
                unit="ms",
            )
        except Exception as e:
            get_workflow_logger("shared_app").error(
                "MONGODB_CONNECTION_FAILED: Failed to connect to MongoDB",
                error=str(e)
            )
            raise

        # Import workflow modules
        import_start = datetime.now(UTC)
        await _import_workflow_modules()
        import_time = (datetime.now(UTC) - import_start).total_seconds() * 1000
        performance_logger.info(
            "workflow_import_duration",
            metric_name="workflow_import_duration",
            value=float(import_time),
            unit="ms",
        )

        # Component system is event-driven, no upfront initialization needed.
        registry_start = datetime.now(UTC)
        registry_time = (datetime.now(UTC) - registry_start).total_seconds() * 1000
        performance_logger.info(
            "unified_registry_init_duration",
            metric_name="unified_registry_init_duration",
            value=float(registry_time),
            unit="ms",
        )

        # Log workflow and tool summary
        status = workflow_status_summary()

        # Total startup time
        total_startup_time = (datetime.now(UTC) - startup_start).total_seconds() * 1000
        performance_logger.info(
            "total_startup_duration",
            metric_name="total_startup_duration",
            value=float(total_startup_time),
            unit="ms",
            workflows_count=status.get("total_workflows", 0),
            tools_count=status.get("total_tools", 0),
        )

        # Business event
        await event_dispatcher.emit_business_event(
            log_event_type="SERVER_STARTUP_COMPLETED",
            description="Server startup completed successfully with unified event dispatcher",
            context={
                "environment": env,
                "startup_time_ms": total_startup_time,
                "workflows_registered": status.get("total_workflows", 0),
                "tools_available": status.get("total_tools", 0),
                "summary": status.get("summary", "Unknown")
            }
        )
        wf_logger.info(f"✅ Server ready - {status['summary']} (Startup: {total_startup_time:.1f}ms)")
    except Exception as e:
        startup_time = (datetime.now(UTC) - startup_start).total_seconds() * 1000
        get_workflow_logger("shared_app").error(
            "SERVER_STARTUP_FAILED: Server startup failed",
            environment=env,
            error=str(e),
            startup_time_ms=startup_time
        )
        raise

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global simple_transport
    shutdown_start = datetime.now(UTC)
    
    wf_logger.info("🛑 Shutting down server...")
    
    try:
        if simple_transport:
            # No explicit disconnect needed for websockets with this transport design
            pass
        
        if mongo_client:
            mongo_client.close()
        
        # Calculate shutdown time and log metrics
        shutdown_time = (datetime.now(UTC) - shutdown_start).total_seconds() * 1000
        
        performance_logger.info(
            "shutdown_duration",
            extra={
                "metric_name": "shutdown_duration",
                "value": float(shutdown_time),
                "unit": "ms",
            },
        )
        
        get_workflow_logger("shared_app").info(
            "SERVER_SHUTDOWN_COMPLETED: Server shutdown completed successfully",
            shutdown_time_ms=shutdown_time,
        )
        
        wf_logger.info(f"✅ Shutdown complete ({shutdown_time:.1f}ms)")
        
    except Exception as e:
        shutdown_time = (datetime.now(UTC) - shutdown_start).total_seconds() * 1000
        get_workflow_logger("shared_app").error(
            "SERVER_SHUTDOWN_FAILED: Error during server shutdown",
            error=str(e),
            shutdown_time_ms=shutdown_time
        )

async def _import_workflow_modules():
    """
    Workflow system startup - using runtime auto-discovery.
    No more scanning for initializer.py files - workflows are discovered on-demand.
    """
    scan_start = datetime.now(UTC)
    
    # Runtime auto-discovery means no upfront imports needed
    # Workflows will be discovered when requested via WebSocket
    
    scan_time = (datetime.now(UTC) - scan_start).total_seconds() * 1000
    
    performance_logger.info(
        "workflow_discovery_duration",
        extra={
            "metric_name": "workflow_discovery_duration",
            "value": float(scan_time),
            "unit": "ms",
            "discovery_mode": "runtime_auto_discovery",
            "upfront_imports": 0,
        },
    )

    get_workflow_logger("shared_app").info(
        "WORKFLOW_SYSTEM_READY: Workflow system initialized with runtime auto-discovery",
        scan_duration_ms=scan_time,
        discovery_mode="runtime_on_demand"
    )

# ============================================================================
# API ENDPOINTS (WebSocket and workflow handling)
# ============================================================================
# # ============================================================================
# # Artifact Proxy: Backend-agnostic proxy for artifact modules
# # ============================================================================

# @app.post("/api/proxy")
# async def artifact_proxy(request: Request):
#     """
#     Backend-agnostic PROXY for the artifact host/modules.
#     Modules call POST /api/proxy with JSON: { service, path, init? }
#       - service: logical name from SERVICE_REGISTRY (e.g., "dotnet", "fastapi")
#       - path:    the path on that service (e.g., "/users/current")
#       - init:    { method, headers, body } similar to fetch()
#     We forward to the real backend and stream the response back.

#     IMPORTANT: If `service == "dotnet"`, this is where we call your .NET backend.
#     """
#     body = await request.json()
#     service = body.get("service")
#     path = body.get("path", "/")
#     init = body.get("init") or {}

#     if not service or service not in SERVICE_REGISTRY:
#         raise HTTPException(status_code=400, detail=f"Unknown or missing service: {service}")

#     target_base = SERVICE_REGISTRY[service]
#     target_url = f"{target_base}{path}"

#     method  = (init.get("method") or "GET").upper()
#     headers = init.get("headers") or {}
#     data    = init.get("body")

#     # Optionally forward the Authorization header from the original request
#     # so your downstream services can do auth consistently.
#     auth = request.headers.get("Authorization")
#     if auth and "authorization" not in {k.lower(): v for k, v in headers.items()}:
#         headers["Authorization"] = auth

#     # ---------------------------- .NET ROUTING HAPPENS HERE --------------------
#     # If service == "dotnet", target_url points at your .NET API (see SERVICE_REGISTRY).
#     # --------------------------------------------------------------------------
#     try:
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             resp = await client.request(method, target_url, headers=headers, content=data)
#         return Response(
#             content=resp.content,
#             status_code=resp.status_code,
#             media_type=resp.headers.get("content-type", "application/json"),
#         )
#     except httpx.RequestError as e:
#         # Central place to log/observe failed downstream calls
#         logger.error(f"Proxy error -> {service} {target_url}: {e}")
#         raise HTTPException(status_code=502, detail=f"Proxy to {service} failed")


# ============================================================================
# Metrics and Health Check
# ============================================================================

@app.get("/api/events/metrics")
async def get_event_metrics():
    """Get unified event dispatcher metrics"""
    try:
        metrics = event_dispatcher.get_metrics()
        
        return {
            "status": "success",
            "data": metrics,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get event metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve event metrics")

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    health_start = datetime.now(UTC)
    try:
        mongo_ping_start = datetime.now(UTC)
        if mongo_client is None:
            raise HTTPException(status_code=503, detail="MongoDB client not initialized")
        await mongo_client.admin.command("ping")
        mongo_ping_time = (datetime.now(UTC) - mongo_ping_start).total_seconds() * 1000
        status = workflow_status_summary()
        connection_info = {
            "websocket_connections": len(simple_transport.connections) if simple_transport else 0,
            "total_connections": len(simple_transport.connections) if simple_transport else 0
        }
        health_time = (datetime.now(UTC) - health_start).total_seconds() * 1000
        performance_logger.info(
            "health_check_duration",
            extra={
                "metric_name": "health_check_duration",
                "value": float(health_time),
                "unit": "ms",
                "mongodb_ping_ms": float(mongo_ping_time),
                "active_connections": connection_info["total_connections"],
                "workflows_count": len(status["registered_workflows"]),
            },
        )
        health_data = {
            "status": "healthy",
            "mongodb": "connected",
            "mongodb_ping_ms": round(mongo_ping_time, 2),
            "simple_transport": "initialized" if simple_transport else "not_initialized",
            "active_connections": connection_info,
            "workflows": status["registered_workflows"],
            "transport_groups": status.get("transport_groups", {}),
            "tools_available": status["total_tools"] > 0,
            "total_tools": status["total_tools"],
            "health_check_time_ms": round(health_time, 2)
        }
        wf_logger.debug(f"✅ Health check passed - Response time: {health_time:.1f}ms")
        return health_data
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")

# ============================================================================
# Chat Management Endpoints
# ============================================================================

@app.post("/api/chats/{enterprise_id}/{workflow_name}/start")
async def start_chat(enterprise_id: str, workflow_name: str, request: Request):
    """Start a new chat session for a workflow.

    Idempotency / duplicate suppression strategy:
      - If an in-progress chat for (enterprise_id, user_id, workflow_name) was created within the last N seconds
        (default 15) AND client did not set force_new=true, we *reuse* that chat_id instead of creating a new one.
      - Optional client-supplied "client_request_id" can further collapse rapid replays (e.g. browser double-submit).
    This prevents multiple empty ChatSessions docs when the frontend issues parallel start attempts during
    React StrictMode double-mount or network retries.
    """
    IDEMPOTENCY_WINDOW_SEC = int(os.getenv("CHAT_START_IDEMPOTENCY_SEC", "15"))
    now = datetime.now(UTC)
    reuse_cutoff = now - timedelta(seconds=IDEMPOTENCY_WINDOW_SEC)
    try:
            data = await request.json()
            user_id = data.get("user_id")
            required_min_tokens = int(data.get("required_min_tokens", 0))
            client_request_id = data.get("client_request_id")
            force_new = str(data.get("force_new", "false")).lower() in ("1", "true", "yes")
            if not user_id:
                raise HTTPException(status_code=400, detail="user_id is required")

            # Ensure wallet exists
            await persistence_manager.ensure_wallet(user_id, enterprise_id, initial_balance=0)
            
            # TokenManager check
            from core.tokens.manager import TokenManager, InsufficientTokensError
            try:
                await TokenManager.ensure_can_start_chat(user_id, enterprise_id, workflow_name, persistence_manager)
            except InsufficientTokensError:
                raise HTTPException(status_code=402, detail="Insufficient tokens to start workflow")
            
            balance = await persistence_manager.get_wallet_balance(user_id, enterprise_id)

            # Obtain underlying lean chat sessions collection
            coll = await _chat_coll()

            # Reuse recent in-progress session if present (idempotent start)
            reused_doc = None
            if not force_new:
                query = {
                    "enterprise_id": enterprise_id,
                    "user_id": user_id,
                    "workflow_name": workflow_name,
                    "status": 0,
                    "created_at": {"$gte": reuse_cutoff},
                }
                if client_request_id:
                    # If client_request_id stored, include it
                    query["client_request_id"] = client_request_id
                reused_doc = await coll.find_one(query, projection={"chat_id": 1, "created_at": 1})

            if reused_doc:
                chat_id = reused_doc["chat_id"]
                get_workflow_logger("shared_app").info(
                    "CHAT_SESSION_REUSED: Existing recent chat reused",
                    enterprise_id=enterprise_id,
                    workflow_name=workflow_name,
                    user_id=user_id,
                    chat_id=chat_id,
                    reuse_window_sec=IDEMPOTENCY_WINDOW_SEC,
                )
                # Ensure a cache_seed exists for this chat (persist if newly assigned)
                try:
                    cache_seed = await persistence_manager.get_or_assign_cache_seed(chat_id, enterprise_id)
                except Exception as se:
                    cache_seed = None
                    logger.debug(f"cache_seed assignment failed (reused chat {chat_id}): {se}")
                # Return existing without touching performance manager again
                return {
                    "success": True,
                    "chat_id": chat_id,
                    "workflow_name": workflow_name,
                    "enterprise_id": enterprise_id,
                    "user_id": user_id,
                    "remaining_balance": balance,
                    "websocket_url": f"/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}",
                    "message": "Existing recent chat reused.",
                    "reused": True,
                    "cache_seed": cache_seed,
                }

            # Generate a new chat ID
            chat_id = str(uuid4())

            # Create session doc immediately (idempotent); attach client_request_id for future reuse
            try:
                base_fields = {"client_request_id": client_request_id} if client_request_id else {}
                await persistence_manager.create_chat_session(chat_id, enterprise_id, workflow_name, user_id)
                if base_fields:
                    await coll.update_one({"_id": chat_id, "enterprise_id": enterprise_id}, {"$set": base_fields})
            except Exception as ce:
                logger.debug(f"chat_session pre-create skipped {chat_id}: {ce}")

            # Initialize performance tracking early
            try:
                perf_mgr = await get_performance_manager()
                await perf_mgr.record_workflow_start(chat_id, enterprise_id, workflow_name, user_id)
            except Exception as perf_e:
                logger.debug(f"perf_start skipped {chat_id}: {perf_e}")

            get_workflow_logger("shared_app").info(
                "CHAT_SESSION_STARTED: New chat session initiated",
                enterprise_id=enterprise_id,
                workflow_name=workflow_name,
                user_id=user_id,
                chat_id=chat_id,
                starting_balance=balance,
                idempotency_window_sec=IDEMPOTENCY_WINDOW_SEC,
            )

            # Assign per-chat cache seed (deterministic) and include in response
            try:
                cache_seed = await persistence_manager.get_or_assign_cache_seed(chat_id, enterprise_id)
            except Exception as se:
                cache_seed = None
                logger.debug(f"cache_seed assignment failed (new chat {chat_id}): {se}")

            return {
                "success": True,
                "chat_id": chat_id,
                "workflow_name": workflow_name,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "remaining_balance": balance,
                "websocket_url": f"/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}",
                "message": "Chat session initialized; connect to websocket to start.",
                "reused": False,
                "cache_seed": cache_seed,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to start chat session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start chat: {e}")

@app.get("/api/chats/{enterprise_id}/{workflow_name}")
async def list_chats(enterprise_id: str, workflow_name: str):
    """List recent chat IDs for a given enterprise and workflow"""
    try:
        # Convert to ObjectId if possible
        try:
            eid = ObjectId(enterprise_id)
        except Exception:
            eid = enterprise_id
        # Query chat sessions collection with the refactored schema (lowercase)
        coll = await _chat_coll()
        cursor = coll.find({"enterprise_id": eid, "workflow_name": workflow_name}).sort("created_at", -1)
        docs = await cursor.to_list(length=20)
        chat_ids = [doc.get("_id") for doc in docs]
        return {"chat_ids": chat_ids}
    except Exception as e:
        logger.error(f"❌ Failed to list chats for enterprise {enterprise_id}, workflow {workflow_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chats")

@app.get("/api/chats/exists/{enterprise_id}/{workflow_name}/{chat_id}")
async def chat_exists(enterprise_id: str, workflow_name: str, chat_id: str):
    """Lightweight existence check for a chat session.

    Frontend uses this to decide whether to clear any cached artifact UI state
    before attempting restoration. We do NOT load the full transcript; only a
    projection on _id to keep this fast.
    """
    try:
        # Accept either raw string or 24-char hex as enterprise id (we store as provided)
        try:
            eid = ObjectId(enterprise_id)
        except Exception:
            eid = enterprise_id

        coll = await _chat_coll()
        doc = await coll.find_one({"_id": chat_id, "enterprise_id": eid, "workflow_name": workflow_name}, {"_id": 1})
        return {"exists": doc is not None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check chat existence: {e}")

@app.get("/api/sessions/list/{enterprise_id}/{user_id}")
async def list_user_sessions(enterprise_id: str, user_id: str):
    """
    List all active/paused workflow sessions for a user.
    
    Used by frontend to render session tabs (like browser tabs).
    Returns sessions across all workflows so UI can show which ones are IN_PROGRESS.
    """
    try:
        from core.data.models import WorkflowStatus
        coll = await _chat_coll()
        
        # Find all IN_PROGRESS sessions for this user
        sessions = await coll.find({
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "status": int(WorkflowStatus.IN_PROGRESS)
        }).sort("last_updated_at", -1).to_list(length=100)
        
        result = []
        for session in sessions:
            result.append({
                "chat_id": session["_id"],
                "workflow_name": session.get("workflow_name"),
                "created_at": session.get("created_at").isoformat() if session.get("created_at") else None,
                "last_updated_at": session.get("last_updated_at").isoformat() if session.get("last_updated_at") else None,
                "last_artifact": session.get("last_artifact"),  # Quick metadata
            })
        
        wf_logger.debug(f"[LIST_SESSIONS] Found {len(result)} IN_PROGRESS sessions for user {user_id}")
        
        return {
            "sessions": result,
            "count": len(result)
        }
    except Exception as e:
        wf_logger.error(f"[LIST_SESSIONS] Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {e}")


@app.get("/api/sessions/oldest/{enterprise_id}/{user_id}")
async def get_oldest_workflow_session(enterprise_id: str, user_id: str):
    """
    Return the oldest IN_PROGRESS workflow session for a user.
    
    Used when toggling from Ask Mozaiks back to workflow mode—routes user
    to the earliest active workflow (chronologically first). If multiple
    workflows are running, this ensures predictable navigation order.
    
    Future: can filter by dependency prerequisites once dependency graph is wired.
    """
    try:
        from core.data.models import WorkflowStatus
        coll = await _chat_coll()
        
        # Find all IN_PROGRESS sessions, sorted by created_at ascending (oldest first)
        sessions = await coll.find({
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "status": int(WorkflowStatus.IN_PROGRESS)
        }).sort("created_at", 1).to_list(length=100)
        
        if not sessions:
            wf_logger.debug(f"[OLDEST_SESSION] No IN_PROGRESS workflows for user {user_id}")
            return {
                "found": False,
                "chat_id": None,
                "workflow_name": None
            }
        
        # TODO: Apply dependency filtering here once workflow registry exposes prerequisite graph
        # For now, return the chronologically oldest session
        oldest = sessions[0]
        
        wf_logger.debug(
            f"[OLDEST_SESSION] Returning oldest workflow {oldest.get('workflow_name')} "
            f"chat_id={oldest['_id']} for user {user_id}"
        )
        
        return {
            "found": True,
            "chat_id": oldest["_id"],
            "workflow_name": oldest.get("workflow_name"),
            "created_at": oldest.get("created_at").isoformat() if oldest.get("created_at") else None,
            "last_artifact": oldest.get("last_artifact")
        }
    except Exception as e:
        wf_logger.error(f"[OLDEST_SESSION] Failed to fetch oldest session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch oldest session: {e}")


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if isinstance(dt, datetime):
        try:
            return dt.isoformat()
        except Exception:
            return str(dt)
    return dt  # type: ignore[return-value]


@app.get("/api/general_chats/list/{enterprise_id}/{user_id}")
async def list_general_chats(enterprise_id: str, user_id: str, limit: int = 50):
    """Return Ask Mozaiks general chat sessions for a user."""

    try:
        sanitized_limit = max(1, min(int(limit or 1), 200))
        sessions = await persistence_manager.list_general_chats(
            enterprise_id=enterprise_id,
            user_id=user_id,
            limit=sanitized_limit,
        )
        normalized: List[Dict[str, Any]] = []
        for sess in sessions:
            normalized.append(
                {
                    "chat_id": sess.get("chat_id"),
                    "label": sess.get("label"),
                    "sequence": sess.get("sequence"),
                    "status": sess.get("status"),
                    "created_at": _iso(sess.get("created_at")),
                    "last_updated_at": _iso(sess.get("last_updated_at")),
                    "last_sequence": sess.get("last_sequence"),
                }
            )
        return {"sessions": normalized, "count": len(normalized)}
    except Exception as e:
        wf_logger.error(f"[LIST_GENERAL_CHATS] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list general chats: {e}")


@app.get("/api/general_chats/transcript/{enterprise_id}/{general_chat_id}")
async def general_chat_transcript(
    enterprise_id: str,
    general_chat_id: str,
    after_sequence: int = -1,
    limit: int = 200,
):
    """Return a general chat transcript slice for Ask Mozaiks tabs."""

    try:
        transcript = await persistence_manager.fetch_general_chat_transcript(
            general_chat_id=general_chat_id,
            enterprise_id=enterprise_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        if not transcript:
            raise HTTPException(status_code=404, detail="General chat not found")

        def _serialize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
            m = dict(msg)
            ts = m.get("timestamp")
            if isinstance(ts, datetime):
                m["timestamp"] = ts.isoformat()
            return m

        payload = {
            "chat_id": transcript.get("chat_id"),
            "label": transcript.get("label"),
            "sequence": transcript.get("sequence"),
            "status": transcript.get("status"),
            "enterprise_id": transcript.get("enterprise_id"),
            "user_id": transcript.get("user_id"),
            "created_at": _iso(transcript.get("created_at")),
            "last_updated_at": _iso(transcript.get("last_updated_at")),
            "last_sequence": transcript.get("last_sequence"),
            "messages": [_serialize_message(m) for m in transcript.get("messages", [])],
        }
        return payload
    except HTTPException:
        raise
    except Exception as e:
        wf_logger.error(f"[GENERAL_CHAT_TRANSCRIPT] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load general chat transcript: {e}")


@app.get("/api/chats/meta/{enterprise_id}/{workflow_name}/{chat_id}")
async def chat_meta(enterprise_id: str, workflow_name: str, chat_id: str):
    """Return lightweight chat metadata including cache_seed, last_artifact, and artifact_instance.

    This allows a second user/browser to restore artifact UI state even if local
    storage is empty. Includes both UI tool artifacts (last_artifact) and
    WorkflowSession artifacts (artifact_instance_id + state) for multi-workflow navigation.
    
    Does not return full transcript.
    """
    try:
        try:
            eid = ObjectId(enterprise_id)
        except Exception:
            eid = enterprise_id
        coll = await _chat_coll()
        projection = {"cache_seed": 1, "last_artifact": 1, "_id": 1, "workflow_name": 1}
        doc = await coll.find_one({"_id": chat_id, "enterprise_id": eid, "workflow_name": workflow_name}, projection)
        if not doc:
            return {"exists": False}
        
        # Also fetch artifact instance from WorkflowSessions (for multi-workflow navigation)
        artifact_instance_id = None
        artifact_state = None
        try:
            from core.workflow import session_manager
            workflow_session = await session_manager.get_workflow_session(chat_id, str(eid))
            if workflow_session and workflow_session.get("artifact_instance_id"):
                artifact_instance_id = workflow_session["artifact_instance_id"]
                # Fetch full artifact state for restoration
                artifact_doc = await session_manager.get_artifact_instance(artifact_instance_id, str(eid))
                if artifact_doc:
                    artifact_state = artifact_doc.get("state")
                    wf_logger.debug(
                        f"[CHAT_META] Retrieved artifact instance {artifact_instance_id} for chat {chat_id}"
                    )
        except Exception as artifact_err:
            wf_logger.warning(f"[CHAT_META] Failed to retrieve artifact instance for chat {chat_id}: {artifact_err}")
        
        return {
            "exists": True,
            "chat_id": chat_id,
            "workflow_name": workflow_name,
            "cache_seed": doc.get("cache_seed"),
            "last_artifact": doc.get("last_artifact"),  # UI tool artifacts (legacy/quick restore)
            "artifact_instance_id": artifact_instance_id,  # WorkflowSession artifact ID
            "artifact_state": artifact_state,  # Full artifact state for multi-workflow navigation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load chat meta: {e}")
    

@app.websocket("/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workflow_name: str,
    enterprise_id: str,
    chat_id: str,
    user_id: str,
):
    """WebSocket endpoint for real-time agent communication with multi-workflow session support."""
    if not simple_transport:
        await websocket.close(code=1000, reason="Transport service not available")
        return

    # Register this WebSocket connection in session registry
    from core.transport.session_registry import session_registry
    ws_id = id(websocket)

    wf_logger.info(f"🔌 New WebSocket connection for workflow '{workflow_name}' (incoming chat_id={chat_id}, ws_id={ws_id})")

    # Auto resume vs new session selection
    active_chat_id = chat_id
    try:
        coll = await _chat_coll()
        latest = await coll.find({
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "user_id": user_id
        }).sort("created_at", -1).limit(1).to_list(length=1)
        if latest:
            latest_doc = latest[0]
            latest_status = int(latest_doc.get("status", -1))
            latest_id = latest_doc.get("_id")
            if latest_status == 0:
                active_chat_id = latest_id
                wf_logger.info("WS_AUTO_RESUME", extra={"chat_id": active_chat_id, "incoming_chat_id": chat_id})
            else:
                # Ensure provided chat id exists (create minimal doc if missing)
                if not await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}):
                    await persistence_manager.create_chat_session(chat_id, enterprise_id, workflow_name, user_id)
                    wf_logger.info("WS_NEW_SESSION_CREATED", extra={"chat_id": chat_id})
        else:
            if not await coll.find_one({"_id": chat_id, "enterprise_id": enterprise_id}):
                await persistence_manager.create_chat_session(chat_id, enterprise_id, workflow_name, user_id)
                wf_logger.info("WS_FIRST_SESSION_CREATED", extra={"chat_id": chat_id})
    except Exception as pre_err:
        wf_logger.error(f"WS_SESSION_DETERMINATION_FAILED: {pre_err}")

    # Auto-start AgentDriven workflows once the socket is accepted and registered
    async def _auto_start_if_needed():
        try:
            from core.workflow.workflow_manager import workflow_manager
            cfg = workflow_manager.get_config(workflow_name)
            if cfg.get("startup_mode", "AgentDriven") == "AgentDriven":
                local_transport = simple_transport
                if not local_transport:
                    return
                # wait until the connection is registered
                for _ in range(20):  # poll for registration using active_chat_id
                    conn = local_transport.connections.get(active_chat_id)
                    if conn and conn.get("websocket") is not None:
                        # idempotency guard so auto-start runs at most once per socket
                        if conn.get("autostarted"):
                            return
                        conn["autostarted"] = True
                        break
                    await asyncio.sleep(0.1)

                await local_transport.handle_user_input_from_api(
                    chat_id=active_chat_id,
                    user_id=user_id,
                    workflow_name=workflow_name,
                    message=None,
                    enterprise_id=enterprise_id,
                )
        except Exception as e:
            logger.error(f"Auto-start failed for {workflow_name}/{active_chat_id}: {e}")

    asyncio.create_task(_auto_start_if_needed())

    # Emit an initial metadata event (chat_meta) with cache_seed for frontend cache alignment
    try:
        chat_exists = False
        coll = None
        try:
            coll = await _chat_coll()
            existing_doc = await coll.find_one({"_id": active_chat_id, "enterprise_id": enterprise_id}, {"_id": 1})
            chat_exists = existing_doc is not None
        except Exception as ce:
            wf_logger.debug(f"chat existence check failed for {active_chat_id}: {ce}")

        # If chat does not exist, create a minimal session doc BEFORE assigning seed
        if not chat_exists:
            try:
                await persistence_manager.create_chat_session(active_chat_id, enterprise_id, workflow_name, user_id)
                chat_exists = True
                wf_logger.info("WS_BACKFILL_SESSION_CREATED", extra={"chat_id": active_chat_id})
            except Exception as ce:
                wf_logger.debug(f"Failed to backfill chat session for {active_chat_id}: {ce}")

        try:
            cache_seed = await persistence_manager.get_or_assign_cache_seed(active_chat_id, enterprise_id)
        except Exception as ce:
            cache_seed = None
            wf_logger.debug(f"cache_seed retrieval failed for WS {active_chat_id}: {ce}")

        if simple_transport:
            # Attempt to include last_artifact for immediate restore (avoid separate HTTP roundtrip)
            last_artifact = None
            created_at_iso = None
            try:
                if coll is not None:
                    doc = await coll.find_one(
                        {"_id": active_chat_id, "enterprise_id": enterprise_id},
                        {"last_artifact": 1, "created_at": 1}
                    )
                    if doc:
                        last_artifact = doc.get("last_artifact")
                        ca = doc.get("created_at")
                        if ca:
                            try:
                                created_at_iso = ca.isoformat()
                            except Exception:
                                created_at_iso = str(ca)
            except Exception as la_err:
                wf_logger.debug(f"last_artifact fetch failed for chat_meta {active_chat_id}: {la_err}")

            await simple_transport.send_event_to_ui({
                'kind': 'chat_meta',
                'chat_id': active_chat_id,
                'workflow_name': workflow_name,
                'enterprise_id': enterprise_id,
                'user_id': user_id,
                'cache_seed': cache_seed,
                'chat_exists': chat_exists,
                'last_artifact': last_artifact,
                'created_at': created_at_iso,
            }, active_chat_id)
            wf_logger.info(
                "CHAT_META_EMITTED",
                extra={
                    "chat_id": active_chat_id,
                    "workflow_name": workflow_name,
                    "enterprise_id": enterprise_id,
                    "cache_seed": cache_seed,
                    "chat_exists": chat_exists,
                    "has_last_artifact": bool(last_artifact),
                    "created_at": created_at_iso,
                },
            )
    except Exception as meta_e:
        wf_logger.debug(f"Failed to emit chat_meta for {active_chat_id}: {meta_e}")
    
    # Validate workflow dependencies before accepting connection
    try:
        is_valid, error_msg = await dependency_manager.validate_workflow_dependencies(
            workflow_name=workflow_name,
            enterprise_id=enterprise_id,
            user_id=user_id
        )
        
        if not is_valid:
            wf_logger.warning(
                "WS_DEPENDENCIES_NOT_MET",
                extra={
                    "workflow_name": workflow_name,
                    "enterprise_id": enterprise_id,
                    "user_id": user_id,
                    "error": error_msg,
                    "chat_id": active_chat_id
                }
            )
            # Send error event to client before closing
            if simple_transport:
                await simple_transport.send_event_to_ui({
                    'kind': 'error',
                    'error_message': error_msg,
                    'error_code': 'WORKFLOW_DEPENDENCIES_NOT_MET',
                    'chat_id': active_chat_id,
                    'workflow_name': workflow_name
                }, active_chat_id)
            
            # Close WebSocket with policy violation code
            await websocket.close(code=1008, reason="Dependencies not met")
            return
    except Exception as dep_err:
        wf_logger.error(f"WS_DEPENDENCY_VALIDATION_FAILED: {dep_err}", exc_info=True)
        # On validation error, fail closed to prevent bypassing prerequisites
        try:
            await websocket.send_json({
                "type": "chat.error",
                "data": {
                    "message": "Failed to validate workflow dependencies. Please try again.",
                    "error_code": "DEPENDENCY_VALIDATION_ERROR"
                }
            })
        except Exception as send_err:
            wf_logger.error(f"Failed to send validation error to client: {send_err}")
        
        await websocket.close(code=1011, reason="Dependency validation failed")
        return
    
    # Register initial workflow in session registry
    session_registry.add_workflow(
        ws_id=ws_id,
        chat_id=active_chat_id,
        workflow_name=workflow_name,
        enterprise_id=enterprise_id,
        user_id=user_id,
        auto_activate=True
    )

    try:
        await simple_transport.handle_websocket(
            websocket=websocket,
            chat_id=active_chat_id,
            user_id=user_id,
            workflow_name=workflow_name,
            enterprise_id=enterprise_id,
            ws_id=ws_id  # Pass ws_id for session switching
        )
    finally:
        # Clean up session registry on disconnect
        session_registry.remove_session(ws_id)
        wf_logger.info(f"🔌 Cleaned up session registry for ws_id={ws_id}")

@app.post("/chat/{enterprise_id}/{chat_id}/{user_id}/input")
async def handle_user_input(
    request: Request,
    enterprise_id: str,
    chat_id: str,
    user_id: str,
):
    """Endpoint to receive user input and trigger the workflow."""
    if not simple_transport:
        raise HTTPException(status_code=503, detail="Transport service is not available.")

    try:
        data = await request.json()
        message = data.get("message")
        workflow_name = data.get("workflow_name")  # No default, must be provided
        
        get_workflow_logger("shared_app").info(
            "USER_INPUT_ENDPOINT_CALLED: User input endpoint called",
            enterprise_id=enterprise_id,
            chat_id=chat_id,
            user_id=user_id,
            workflow_name=workflow_name,
            message_length=(len(message) if message else 0)
        )
        
        if not message:
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

        result = await simple_transport.handle_user_input_from_api(
            chat_id=chat_id,
            user_id=user_id,
            workflow_name=workflow_name,
            message=message,
            enterprise_id=enterprise_id
        )

        
        get_workflow_logger("shared_app").info(
            "USER_INPUT_PROCESSED: User input processed successfully",
            chat_id=chat_id,
            transport=result.get("transport")
        )
        
        return {"status": "Message received and is being processed.", "transport": result.get("transport")}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"? Error handling user input for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process input: {e}")

@app.post("/api/user-input/submit")
async def submit_user_input_response(request: Request):
    """
    API endpoint for submitting user input responses.
    
    This endpoint is called by the frontend when a user responds to a user input request
    sent via WebSocket from AG2 agents.
    """
    if not simple_transport:
        raise HTTPException(status_code=503, detail="Transport service is not available.")

    try:
        data = await request.json()
        input_request_id = data.get("input_request_id")
        user_input = data.get("user_input")
        
        if not input_request_id:
            raise HTTPException(status_code=400, detail="'input_request_id' field is required.")
        if not user_input:
            raise HTTPException(status_code=400, detail="'user_input' field is required.")
        
        # Submit the user input to the transport layer
        success = await simple_transport.submit_user_input(input_request_id, user_input)
        
        if success:
            get_workflow_logger("shared_app").info(
                "USER_INPUT_RESPONSE_SUBMITTED: User input response submitted",
                input_request_id=input_request_id,
                input_length=len(user_input)
            )
            return {"status": "success", "message": "User input submitted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Input request not found or already completed")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"? Error submitting user input response: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit user input: {e}")

@app.get("/api/workflows/{workflow_name}/transport")
async def get_workflow_transport_info(workflow_name: str):
    """Get transport information for a specific workflow."""
    transport = get_workflow_transport(workflow_name)
    
    return {
        "workflow_name": workflow_name,
        "transport": transport,
        "endpoints": {
            "websocket": f"/ws/{workflow_name}/{{enterprise_id}}/{{chat_id}}/{{user_id}}",
            "input": "/chat/{{enterprise_id}}/{{chat_id}}/{{user_id}}/input"
        }
    }

@app.get("/api/workflows/{workflow_name}/tools")
async def get_workflow_tools_info(workflow_name: str):
    """Get UI tools manifest for a specific workflow."""
    tools = get_workflow_tools(workflow_name)
    
    return {
        "workflow_name": workflow_name,
        "tools": tools
    }

@app.get("/api/workflows/{workflow_name}/ui-tools")
async def get_workflow_ui_tools_manifest(workflow_name: str):
    """Get UI tools manifest with schemas for frontend development."""
    try:
        from core.workflow.workflow_manager import workflow_manager
        ui_tools = workflow_manager.get_workflow_tools(workflow_name)
        manifest = []
        for rec in ui_tools:
            manifest.append({
                "ui_tool_id": rec.get("tool_id"),
                "component": rec.get("component"),
                "mode": rec.get("mode"),
                "agent": rec.get("agent"),
                "workflow": workflow_name
            })
        return {"workflow_name": workflow_name, "ui_tools_count": len(manifest), "ui_tools": manifest}
        
    except Exception as e:
        logger.error(f"Error getting UI tools manifest for {workflow_name}: {e}")
        return {
            "workflow_name": workflow_name,
            "ui_tools_count": 0,
            "ui_tools": [],
            "error": str(e)
        }

# ==============================================================================
# TOKEN API ENDPOINTS
# ==============================================================================

@app.get("/api/tokens/{user_id}/balance")
async def get_user_token_balance(user_id: str, enterprise_id: Optional[str] = None):
    """Get user token balance from wallets collection"""
    try:
        if not enterprise_id:
            raise HTTPException(status_code=400, detail="enterprise_id is required")
        balance = await persistence_manager.get_wallet_balance(user_id, enterprise_id)
        wf_logger.info(f"Token balance retrieved for user {user_id}: {balance} tokens")
        return {"balance": balance, "remaining": balance, "user_id": user_id, "enterprise_id": enterprise_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting token balance for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tokens/{user_id}/consume")
async def consume_user_tokens(user_id: str, request: Request):
    """Consume user tokens from wallets collection (atomic debit)."""
    try:
        body = await request.json()
        amount = int(body.get("amount", 0))
        enterprise_id = body.get("enterprise_id")
        reason = body.get("reason", "manual_consume")
        if not enterprise_id:
            raise HTTPException(status_code=400, detail="enterprise_id is required")
        new_bal = await persistence_manager.debit_tokens(user_id, enterprise_id, amount, reason=reason, strict=True)
        wf_logger.info(f"Consumed {amount} tokens for user {user_id}. Remaining: {new_bal}")
        return {"success": True, "remaining": new_bal}
    except ValueError as ve:
        if str(ve) == "INSUFFICIENT_TOKENS":
            raise HTTPException(status_code=402, detail="Insufficient tokens")
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error consuming tokens for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workflows")
async def get_workflows():
    """Get all workflows for frontend (alias for /api/workflows/config)"""
    try:
        from core.workflow.workflow_manager import workflow_manager
        
        configs = {}
        for workflow_name in workflow_manager.get_all_workflow_names():
            configs[workflow_name] = workflow_manager.get_config(workflow_name)
        
        get_workflow_logger("shared_app").info(
            "WORKFLOWS_REQUESTED: Workflows requested by frontend",
            workflow_count=len(configs)
        )
        
        return configs
        
    except Exception as e:
        logger.error(f"? Failed to get workflows: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workflows")

@app.get("/api/workflows/config")
async def get_workflow_configs():
    """Get all workflow configurations for frontend"""
    try:
        from core.workflow.workflow_manager import workflow_manager
        
        configs = {}
        for workflow_name in workflow_manager.get_all_workflow_names():
            configs[workflow_name] = workflow_manager.get_config(workflow_name)
        
        get_workflow_logger("shared_app").info(
            "WORKFLOW_CONFIGS_REQUESTED: Workflow configurations requested by frontend",
            workflow_count=len(configs)
        )
        
        return configs
        
    except Exception as e:
        logger.error(f"? Failed to get workflow configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workflow configurations")

@app.get("/api/workflows/{enterprise_id}/available")
async def get_available_workflows(
    enterprise_id: str,
    user_id: str,
):
    """
    Get workflows with availability status based on dependencies.
    
    Returns a list of workflows indicating which are available for the user to start
    based on their dependency prerequisites.
    
    Args:
        enterprise_id: Enterprise identifier
        user_id: User identifier
        
    Returns:
        Dict with 'workflows' array containing workflow metadata and availability status
    """
    try:
        workflows = await dependency_manager.list_available_workflows(
            enterprise_id=enterprise_id,
            user_id=user_id
        )
        
        get_workflow_logger("shared_app").info(
            "AVAILABLE_WORKFLOWS_REQUESTED",
            extra={
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "workflow_count": len(workflows)
            }
        )
        
        return {"workflows": workflows}
        
    except Exception as e:
        logger.error(f"Failed to get available workflows for enterprise {enterprise_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve available workflows: {str(e)}")

@app.post("/chat/{enterprise_id}/{chat_id}/component_action")
async def handle_component_action(
    request: Request,
    enterprise_id: str,
    chat_id: str,
):
    """Endpoint to receive component actions for AG2 ContextVariables (WebSocket support)."""
    if not simple_transport:
        raise HTTPException(status_code=503, detail="Transport service is not available.")

    try:
        data = await request.json()
        component_id = data.get("component_id")
        action_type = data.get("action_type")
        action_data = data.get("action_data", {})
        
        get_workflow_logger("shared_app").info(
            "COMPONENT_ACTION_ENDPOINT_CALLED: Component action endpoint called",
            enterprise_id=enterprise_id,
            chat_id=chat_id,
            component_id=component_id,
            action_type=action_type
        )
        
        if not component_id or not action_type:
            raise HTTPException(status_code=400, detail="'component_id' and 'action_type' fields are required.")

        logger.info(f"🧩 Component action via HTTP: {component_id} -> {action_type}")

        try:
            result = await simple_transport.process_component_action(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                component_id=component_id,
                action_type=action_type,
                action_data=action_data or {}
            )
            get_workflow_logger("shared_app").info(
                "COMPONENT_ACTION_PROCESSED: Component action processed successfully",
                chat_id=chat_id,
                component_id=component_id,
                action_type=action_type,
                applied_keys=list((result.get('applied') or {}).keys())
            )
            return {
                "status": "success",
                "message": "Component action applied",
                "applied": result.get('applied'),
                "timestamp": datetime.now(UTC).isoformat()
            }
        except Exception as action_error:
            logger.error(f"❌ Component action failed: {action_error}")
            raise HTTPException(status_code=500, detail=f"Component action failed: {action_error}")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"? Error handling component action for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process component action: {e}")

@app.post("/api/ui-tool/submit")
async def submit_ui_tool_response(request: Request):
    """
    API endpoint for submitting UI tool responses.
    
    This endpoint is called by the frontend when a user interacts with UI tool components
    (like AgentAPIKeyInput or FileDownloadCenter) and submits responses.
    """
    if not simple_transport:
        raise HTTPException(status_code=503, detail="Transport service is not available.")

    try:
        data = await request.json()
        event_id = data.get("event_id")
        response_data = data.get("response_data")
        
        if not event_id:
            raise HTTPException(status_code=400, detail="'event_id' field is required.")
        if not response_data:
            raise HTTPException(status_code=400, detail="'response_data' field is required.")
        
        # Submit the UI tool response to the transport layer
        success = await simple_transport.submit_ui_tool_response(event_id, response_data)
        
        if success:
            get_workflow_logger("shared_app").info(
                "UI_TOOL_RESPONSE_SUBMITTED: UI tool response submitted",
                event_id=event_id,
                response_status=response_data.get("status", "unknown"),
                ui_tool_id=response_data.get("data", {}).get("ui_tool_id", "unknown")
            )
            return {"status": "success", "message": "UI tool response submitted successfully"}
        else:
            raise HTTPException(status_code=404, detail="UI tool event not found or already completed")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"? Error submitting UI tool response: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit UI tool response: {e}")

@app.get("/api/download/workflow-file")
async def download_workflow_file(file_path: str):
    """
    Download a single workflow file.
    
    Args:
        file_path: Absolute path to the file to download
    
    Returns:
        File content with proper download headers
    """
    from fastapi.responses import FileResponse
    import mimetypes
    
    try:
        if not file_path:
            raise HTTPException(status_code=400, detail="file_path query parameter is required")

        file = Path(file_path)
        workflows_base = Path(__file__).parent / "workflows"

        if not file.is_absolute():
            file = workflows_base / file
        
        try:
            file_resolved = file.resolve()
            workflows_base_resolved = workflows_base.resolve()
            if not str(file_resolved).startswith(str(workflows_base_resolved)):
                raise HTTPException(status_code=403, detail="Access denied: File outside workflow directories")
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid file path")
        
        if not file.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not file.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        
        # Determine proper MIME type based on file extension
        mime_type, _ = mimetypes.guess_type(file.name)
        if not mime_type:
            # Default MIME types for common workflow files
            if file.suffix == '.json':
                mime_type = 'application/json'
            elif file.suffix == '.env':
                mime_type = 'text/plain'
            elif file.suffix == '.py':
                mime_type = 'text/x-python'
            elif file.suffix == '.js':
                mime_type = 'text/javascript'
            elif file.suffix == '.jsx':
                mime_type = 'text/javascript'
            else:
                mime_type = 'application/octet-stream'
        
        # Return file with download headers
        return FileResponse(
            path=str(file_resolved),
            filename=file.name,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file.name}"',
                "X-Content-Type-Options": "nosniff"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ File download failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download file: {e}")

@app.post("/api/chats/{chat_id}/resume")
async def resume_chat_after_topup(chat_id: str, request: Request):
    """Resume a chat that was paused due to token exhaustion or limits."""
    data = await request.json()
    enterprise_id = data.get("enterprise_id")
    if not enterprise_id:
        raise HTTPException(status_code=400, detail="enterprise_id is required")
        
    from core.tokens.manager import TokenManager
    await TokenManager.resume_after_topup(chat_id, enterprise_id, persistence_manager)
    return {"success": True}
