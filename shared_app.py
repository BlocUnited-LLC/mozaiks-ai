# ==============================================================================
# FILE: shared_app.py
# DESCRIPTION: FastAPI app - workflow agnostic, tools handled by workflows
# ==============================================================================
import logging
import os
import sys
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
# Ensure project root is on Python path for workflow imports
sys.path.insert(0, str(Path(__file__).parent))
import json
import asyncio
from fastapi import FastAPI, HTTPException, Request, WebSocket, Response
from starlette.middleware.cors import CORSMiddleware
from bson.objectid import ObjectId
from uuid import uuid4
import autogen
from pydantic import BaseModel


from core.core_config import get_mongo_client
from core.transport.simple_transport import SimpleTransport
from core.workflow.init_registry import  workflow_status_summary, get_workflow_transport, get_workflow_tools
from core.data.persistence_manager import AG2PersistenceManager
from core.data.chat_sessions_data import ChatSessionsRepository

# Initialize persistence manager
persistence_manager = AG2PersistenceManager()
chat_sessions_repo = ChatSessionsRepository()

# Request model for starting a chat session
class StartChatRequest(BaseModel):
    user_id: str

# Import our custom logging setup
from logs.logging_config import (
    setup_development_logging, 
    setup_production_logging, 
    get_workflow_logger, 
    get_chat_logger,
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
chat_logger = get_chat_logger("shared_app")
performance_logger = get_workflow_logger("performance.shared_app")
logger = logging.getLogger(__name__)

# Log AG2 version for debugging
wf_logger.info(f"🔍 autogen version: {getattr(autogen, '__version__', 'unknown')}")

# Emit an explicit startup log line so file logging can be verified quickly
wf_logger.info(f"SERVER_STARTUP_INIT: Starting MozaiksAI in {env} mode")

# Initialize unified event dispatcher
from core.events import get_event_dispatcher
event_dispatcher = get_event_dispatcher()
wf_logger.info("🎯 Unified Event Dispatcher initialized")

# Initialize OpenLit Observability
from core.observability.performance_manager import get_performance_manager

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
    """Initialize application on startup"""
    global simple_transport
    startup_start = datetime.utcnow()

    try:
        # Initialize performance / observability
        perf_mgr = await get_performance_manager()
        await perf_mgr.initialize()

        # Initialize simple transport
        streaming_start = datetime.utcnow()
        simple_transport = await SimpleTransport.get_instance()
        
        streaming_time = (datetime.utcnow() - streaming_start).total_seconds() * 1000
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
        mongo_start = datetime.utcnow()
        try:
            await mongo_client.admin.command("ping")
            mongo_time = (datetime.utcnow() - mongo_start).total_seconds() * 1000
            
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
        import_start = datetime.utcnow()
        await _import_workflow_modules()
        import_time = (datetime.utcnow() - import_start).total_seconds() * 1000
        
        performance_logger.info(
            "workflow_import_duration",
            metric_name="workflow_import_duration",
            value=float(import_time),
            unit="ms",
        )

        # Component system is event-driven, no upfront initialization needed.
        registry_start = datetime.utcnow()
        
        registry_time = (datetime.utcnow() - registry_start).total_seconds() * 1000
        performance_logger.info(
            "unified_registry_init_duration",
            metric_name="unified_registry_init_duration",
            value=float(registry_time),
            unit="ms",
        )
        
        # Log workflow and tool summary
        status = workflow_status_summary()
        
        # Calculate total startup time
        total_startup_time = (datetime.utcnow() - startup_start).total_seconds() * 1000
        performance_logger.info(
            "total_startup_duration",
            metric_name="total_startup_duration",
            value=float(total_startup_time),
            unit="ms",
            workflows_count=status.get("total_workflows", 0),
            tools_count=status.get("total_tools", 0),
        )

        # Use unified event dispatcher for this important startup event
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
        startup_time = (datetime.utcnow() - startup_start).total_seconds() * 1000
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
    shutdown_start = datetime.utcnow()
    
    wf_logger.info("🛑 Shutting down server...")
    
    try:
        if simple_transport:
            # No explicit disconnect needed for websockets with this transport design
            pass
        
        if mongo_client:
            mongo_client.close()
        
        # Calculate shutdown time and log metrics
        shutdown_time = (datetime.utcnow() - shutdown_start).total_seconds() * 1000
        
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
        shutdown_time = (datetime.utcnow() - shutdown_start).total_seconds() * 1000
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
    scan_start = datetime.utcnow()
    
    # Runtime auto-discovery means no upfront imports needed
    # Workflows will be discovered when requested via WebSocket
    
    scan_time = (datetime.utcnow() - scan_start).total_seconds() * 1000
    
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
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get event metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve event metrics")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    health_start = datetime.utcnow()
    
    try:
        # Test MongoDB
        mongo_ping_start = datetime.utcnow()
        if mongo_client is None:
            raise HTTPException(status_code=503, detail="MongoDB client not initialized")
        await mongo_client.admin.command("ping")
        mongo_ping_time = (datetime.utcnow() - mongo_ping_start).total_seconds() * 1000
        
        # Get workflow status
        status = workflow_status_summary()
        
        # Get active connections from simple transport
        connection_info = {
            "websocket_connections": len(simple_transport.connections) if simple_transport else 0,
            "total_connections": len(simple_transport.connections) if simple_transport else 0
        }

        # Calculate health check time
        health_time = (datetime.utcnow() - health_start).total_seconds() * 1000
        
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
        logger.error(f"? Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")

# ============================================================================
# Chat Management Endpoints
# ============================================================================

@app.post("/api/chats/{enterprise_id}/{workflow_name}/start")
async def start_chat(enterprise_id: str, workflow_name: str, request: Request):
    """Start a new chat session for a workflow"""
    try:
        data = await request.json()
        user_id = data.get("user_id")
        required_min_tokens = int(data.get("required_min_tokens", 0))
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        # Ensure wallet exists and get balance
        await persistence_manager.ensure_wallet(user_id, enterprise_id, initial_balance=0)
        balance = await persistence_manager.get_wallet_balance(user_id, enterprise_id)
        if required_min_tokens and balance < required_min_tokens:
            raise HTTPException(status_code=402, detail="Insufficient tokens to start workflow")

        # Generate a new chat ID (session will be created on conversation start)
        chat_id = str(uuid4())
        # NOTE: Do not create the session here to avoid duplicates with termination_handler.on_conversation_start
        # await persistence_manager.create_chat_session(chat_id, enterprise_id, workflow_name, user_id)

        # Initialize performance tracking early (in-memory state) so first turn deltas are clean
        try:
            perf_mgr = await get_performance_manager()
            # We only create in-memory state here; session DB row still created by termination handler later
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
        )

        return {
            "success": True,
            "chat_id": chat_id,
            "workflow_name": workflow_name,
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "remaining_balance": balance,
            "websocket_url": f"/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}",
            "message": "Chat session initialized; connect to websocket to start."
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
        # Query chat sessions collection with the refactored schema
        coll = await chat_sessions_repo._coll()
        cursor = coll.find({"enterprise_id": eid, "workflow_name": workflow_name}).sort("created_at", -1)
        docs = await cursor.to_list(length=20)
        chat_ids = [doc.get("chat_id") for doc in docs]
        return {"chat_ids": chat_ids}
    except Exception as e:
        logger.error(f"❌ Failed to list chats for enterprise {enterprise_id}, workflow {workflow_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chats")
    

@app.websocket("/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workflow_name: str,
    enterprise_id: str,
    chat_id: str,
    user_id: str,
):
    """WebSocket endpoint for real-time agent communication."""
    if not simple_transport:
        await websocket.close(code=1000, reason="Transport service not available")
        return

    wf_logger.info(f"🔌 New WebSocket connection for workflow '{workflow_name}'")

    # Auto-start AgentDriven workflows once the socket is accepted and registered
    async def _auto_start_if_needed():
        try:
            from core.workflow.workflow_config import workflow_config
            cfg = workflow_config.get_config(workflow_name)
            if cfg.get("startup_mode", "AgentDriven") == "AgentDriven":
                # Wait briefly until SimpleTransport registers the websocket
                local_transport = simple_transport
                if not local_transport:
                    return
                for _ in range(20):  # up to ~2s
                    if (
                        chat_id in local_transport.connections
                        and local_transport.connections[chat_id].get("websocket") is not None
                    ):
                        break
                    await asyncio.sleep(0.1)
                await local_transport.handle_user_input_from_api(
                    chat_id=chat_id,
                    user_id=user_id,
                    workflow_name=workflow_name,
                    message=None,
                    enterprise_id=enterprise_id,
                )
        except Exception as e:
            logger.error(f"Auto-start failed for {workflow_name}/{chat_id}: {e}")

    asyncio.create_task(_auto_start_if_needed())
    
    await simple_transport.handle_websocket(
        websocket=websocket,
        chat_id=chat_id,
        user_id=user_id,
        workflow_name=workflow_name,
        enterprise_id=enterprise_id
    )

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

    # Token usage is tracked via UsageSummaryEvent; no manual cumulative capture here
        
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
            "input": f"/chat/{{enterprise_id}}/{{chat_id}}/{{user_id}}/input"
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
        # Get UI-specific tools (look for workflow_name + "_ui")
        ui_workflow_name = f"{workflow_name}_ui"
        ui_tools = get_workflow_tools(ui_workflow_name)
        
        manifest = []
        
        # Extract UI tool registry from discovered tools
        for tool_class in ui_tools:
            # Check for module-level registry first
            if hasattr(tool_class, '__module__'):
                try:
                    import importlib
                    module = importlib.import_module(tool_class.__module__)
                    if hasattr(module, 'get_ui_tool_registry'):
                        registry = module.get_ui_tool_registry()
                        for ui_tool_id, tool_info in registry.items():
                            # Avoid duplicates
                            if not any(item["ui_tool_id"] == ui_tool_id for item in manifest):
                                manifest.append({
                                    "ui_tool_id": ui_tool_id,
                                    "description": tool_info.get("description", ""),
                                    "payloadSchema": tool_info.get("payloadSchema", {}),
                                    "workflow": workflow_name
                                })
                except Exception as e:
                    logger.debug(f"Could not extract module-level UI tool registry: {e}")
        
        return {
            "workflow_name": workflow_name,
            "ui_tools_count": len(manifest),
            "ui_tools": manifest,
            "documentation": f"Each ui_tool_id must have a corresponding React component in the frontend. "
                           f"Use the payloadSchema to implement the component's props interface.",
            "usage": f"Backend emits: await channel.send_ui_tool(ui_tool_id, payload)"
        }
        
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
async def get_user_token_balance(user_id: str, appid: str = "default", enterprise_id: Optional[str] = None):
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
        from core.workflow.workflow_config import workflow_config
        
        configs = {}
        for workflow_name in workflow_config.get_all_workflow_names():
            configs[workflow_name] = workflow_config.get_config(workflow_name)
        
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
        from core.workflow.workflow_config import workflow_config
        
        configs = {}
        for workflow_name in workflow_config.get_all_workflow_names():
            configs[workflow_name] = workflow_config.get_config(workflow_name)
        
        get_workflow_logger("shared_app").info(
            "WORKFLOW_CONFIGS_REQUESTED: Workflow configurations requested by frontend",
            workflow_count=len(configs)
        )
        
        return configs
        
    except Exception as e:
        logger.error(f"? Failed to get workflow configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workflow configurations")

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

        logger.info(f"?? Received component action via HTTP: {component_id} -> {action_type}")

        try:
            # This endpoint receives user interactions from UI components.
            # The correct action is to submit this data as a response to a waiting agent tool,
            # not to send a new UI event. We use submit_ui_tool_response for this.
            # The 'component_id' from the frontend corresponds to the 'event_id' that the agent is waiting for.
            event_id = component_id

            # Package the rest of the data into the response_data dictionary.
            response_data = {
                "action_type": action_type,
                "action_data": action_data,
                "source": "http_endpoint"
            }

            success = await simple_transport.submit_ui_tool_response(
                event_id=event_id,
                response_data=response_data
            )

            if not success:
                # The event_id might not be found if the agent is no longer waiting
                # or if the frontend sent a stale/incorrect ID.
                logger.warning(f"UI tool event '{event_id}' not found or already completed for chat {chat_id}.")
                raise HTTPException(status_code=404, detail=f"UI tool event '{event_id}' not found or already completed.")
            
            logger.info(f"? Component action for event '{event_id}' submitted successfully.")
            
            get_workflow_logger("shared_app").info(
                "COMPONENT_ACTION_PROCESSED: Component action processed successfully",
                chat_id=chat_id,
                event_id=event_id,
                submitted_to_workflow=True
            )
            
            return {
                "status": "success",
                "message": "Component action submitted to workflow",
                "timestamp": datetime.utcnow().isoformat()
            }
                
        except Exception as action_error:
            logger.error(f"? Component action submission failed (HTTP): {action_error}")
            raise HTTPException(status_code=500, detail=f"Component action submission failed: {action_error}")

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
