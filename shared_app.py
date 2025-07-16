# ==============================================================================
# FILE: shared_app.py
# DESCRIPTION: FastAPI app - workflow agnostic, tools handled by workflows
# ==============================================================================
import os
import sys
import json
import asyncio
import logging
import traceback
from typing import Optional
from datetime import datetime
from pathlib import Path
# Ensure project root is on Python path for workflow imports
sys.path.insert(0, str(Path(__file__).parent))
import importlib
from fastapi import FastAPI, HTTPException, Request, WebSocket
from starlette.middleware.cors import CORSMiddleware
from bson.objectid import ObjectId
from uuid import uuid4
from pydantic import BaseModel

from core.core_config import make_streaming_config, get_mongo_client
from core.transport.simple_transport import SimpleTransport
from core.workflow.init_registry import get_initialization_coroutines, get_registered_workflows, workflow_status_summary, get_workflow_transport, get_workflow_tools, workflow_human_loop
from core.data.persistence_manager import persistence_manager as mongodb_manager
from core.data.token_manager import _mock_get_remaining, _mock_consume_tokens

# Request model for starting a chat session
class StartChatRequest(BaseModel):
    user_id: str

# Import our custom logging setup
from logs.logging_config import (
    setup_development_logging, 
    setup_production_logging, 
    get_business_logger, 
    get_chat_logger,
    get_performance_logger,
    log_business_event,
    log_performance_metric
)

# Setup logging based on environment
env = os.getenv("ENVIRONMENT", "development").lower()
if env == "production":
    setup_production_logging()
    log_business_event(
        event_type="LOGGING_CONFIGURED",
        description="Production logging configuration applied"
    )
else:
    setup_development_logging()
    log_business_event(
        event_type="LOGGING_CONFIGURED", 
        description="Development logging configuration applied"
    )

# Get specialized loggers
business_logger = get_business_logger("shared_app")
chat_logger = get_chat_logger("shared_app")
performance_logger = get_performance_logger("shared_app")
logger = logging.getLogger(__name__)

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

mongo_client = get_mongo_client()
simple_transport: Optional[SimpleTransport] = None

@app.on_event("startup")
async def startup():
    """Initialize application on startup"""
    global simple_transport
    startup_start = datetime.utcnow()

    business_logger.info("🚀 Starting MozaiksAI Runtime...")

    try:
        # Initialize simple transport
        streaming_start = datetime.utcnow()
        _, streaming_llm_config = await make_streaming_config()
        simple_transport = SimpleTransport(streaming_llm_config)
        
        streaming_time = (datetime.utcnow() - streaming_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="streaming_config_init_duration",
            value=streaming_time,
            context={"config_keys": list(streaming_llm_config.keys()) if streaming_llm_config else []}
        )
        
        business_logger.info("🔌 Simple transport initialized")

        # Test MongoDB connection
        mongo_start = datetime.utcnow()
        try:
            await mongo_client.admin.command("ping")
            mongo_time = (datetime.utcnow() - mongo_start).total_seconds() * 1000
            
            log_performance_metric(
                metric_name="mongodb_ping_duration",
                value=mongo_time,
                unit="ms"
            )
            
            log_business_event(
                event_type="MONGODB_CONNECTED",
                description="MongoDB connection established successfully",
                context={"ping_time_ms": mongo_time}
            )
            
        except Exception as e:
            log_business_event(
                event_type="MONGODB_CONNECTION_FAILED",
                description="Failed to connect to MongoDB",
                context={"error": str(e)},
                level="ERROR"
            )
            raise

        # Import workflow modules
        import_start = datetime.utcnow()
        await _import_workflow_modules()
        import_time = (datetime.utcnow() - import_start).total_seconds() * 1000
        
        log_performance_metric(
            metric_name="workflow_import_duration",
            value=import_time,
            unit="ms"
        )

        # Initialize unified registry
        registry_start = datetime.utcnow()
        business_logger.info("🎯 Component registry initialization skipped (simplified system)")
        
        registry_time = (datetime.utcnow() - registry_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="unified_registry_init_duration",
            value=registry_time,
            unit="ms"
        )
        
        # Run initialization coroutines
        init_start = datetime.utcnow()
        business_logger.info("🔧 Running plugin initializers...")
        
        init_coroutines = get_initialization_coroutines()
        successful_inits = 0
        failed_inits = 0
        
        for init_coro in init_coroutines:
            coro_start = datetime.utcnow()
            try:
                await init_coro()
                coro_time = (datetime.utcnow() - coro_start).total_seconds() * 1000
                
                log_performance_metric(
                    metric_name="initializer_duration",
                    value=coro_time,
                    unit="ms",
                    context={"initializer": init_coro.__name__}
                )
                
                business_logger.debug(f"✅ Initialized: {init_coro.__name__} ({coro_time:.1f}ms)")
                successful_inits += 1
                
            except Exception as e:
                coro_time = (datetime.utcnow() - coro_start).total_seconds() * 1000
                
                log_business_event(
                    event_type="INITIALIZER_FAILED",
                    description=f"Plugin initializer failed: {init_coro.__name__}",
                    context={
                        "initializer": init_coro.__name__,
                        "error": str(e),
                        "duration_ms": coro_time
                    },
                    level="ERROR"
                )
                failed_inits += 1
        
        init_time = (datetime.utcnow() - init_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="total_initialization_duration",
            value=init_time,
            unit="ms",
            context={
                "successful_inits": successful_inits,
                "failed_inits": failed_inits,
                "total_inits": len(init_coroutines)
            }
        )

        # Log workflow and tool summary
        status = workflow_status_summary()
        
        # Calculate total startup time
        total_startup_time = (datetime.utcnow() - startup_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="total_startup_duration",
            value=total_startup_time,
            unit="ms",
            context={
                "workflows_count": status.get("registered_workflows", 0),
                "tools_count": status.get("total_tools", 0)
            }
        )
        
        log_business_event(
            event_type="SERVER_STARTUP_COMPLETED",
            description="Server startup completed successfully",
            context={
                "environment": env,
                "startup_time_ms": total_startup_time,
                "workflows_registered": status.get("registered_workflows", 0),
                "tools_available": status.get("total_tools", 0),
                "summary": status.get("summary", "Unknown")
            }
        )
        
        business_logger.info(f"✅ Server ready - {status['summary']} (Startup: {total_startup_time:.1f}ms)")

    except Exception as e:
        startup_time = (datetime.utcnow() - startup_start).total_seconds() * 1000
        log_business_event(
            event_type="SERVER_STARTUP_FAILED",
            description="Server startup failed",
            context={
                "environment": env,
                "error": str(e),
                "startup_time_ms": startup_time
            },
            level="ERROR"
        )
        raise

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global simple_transport
    shutdown_start = datetime.utcnow()
    
    business_logger.info("🛑 Shutting down server...")
    
    try:
        if simple_transport:
            simple_transport.disconnect()
            business_logger.info("🔌 Simple transport cleaned up")
        
        if mongo_client:
            mongo_client.close()
            business_logger.info("🔌 MongoDB client closed")
        
        # Calculate shutdown time and log metrics
        shutdown_time = (datetime.utcnow() - shutdown_start).total_seconds() * 1000
        
        log_performance_metric(
            metric_name="shutdown_duration",
            value=shutdown_time,
            unit="ms"
        )
        
        log_business_event(
            event_type="SERVER_SHUTDOWN_COMPLETED",
            description="Server shutdown completed successfully",
            context={
                "shutdown_time_ms": shutdown_time,
            }
        )
        
        business_logger.info(f"✅ Shutdown complete ({shutdown_time:.1f}ms)")
        
    except Exception as e:
        shutdown_time = (datetime.utcnow() - shutdown_start).total_seconds() * 1000
        log_business_event(
            event_type="SERVER_SHUTDOWN_FAILED",
            description="Error during server shutdown",
            context={
                "error": str(e),
                "shutdown_time_ms": shutdown_time
            },
            level="ERROR"
        )

async def _import_workflow_modules():
    """Import workflow modules from directories"""
    base_path = Path(__file__).parent
    business_logger.info(f"🔍 Scanning {base_path} for workflow plugins")

    discovered = []
    scan_start = datetime.utcnow()

    # Scan current directory
    current_dir_count = 0
    for d in base_path.iterdir():
        if d.is_dir() and not d.name.startswith((".", "__")) and (d / "initializer.py").exists():
            discovered.append(f"{d.name}.initializer")
            current_dir_count += 1

    # Scan additional directories
    extra_dirs = [p.strip() for p in os.getenv("PLUGIN_DIRS", "").split(",") if p.strip()]
    additional_dir_count = 0
    
    for name in extra_dirs or ["workflows", "modules", "apps", "plugins"]:
        p = base_path / name
        if not p.is_dir():
            continue
        for d in p.iterdir():
            if d.is_dir() and not d.name.startswith((".", "__")) and (d / "initializer.py").exists():
                discovered.append(f"{name}.{d.name}.initializer")
                additional_dir_count += 1

    scan_time = (datetime.utcnow() - scan_start).total_seconds() * 1000
    
    log_performance_metric(
        metric_name="plugin_discovery_duration",
        value=scan_time,
        unit="ms",
        context={
            "plugins_found": len(discovered),
            "current_dir_plugins": current_dir_count,
            "additional_dir_plugins": additional_dir_count
        }
    )
    
    business_logger.info(f"🔍 Found {len(discovered)} plugin(s) in {scan_time:.1f}ms")
    
    # Import modules
    import_start = datetime.utcnow()
    successful_imports = 0
    failed_imports = 0
    
    for module_name in discovered:
        module_start = datetime.utcnow()
        try:
            importlib.import_module(module_name)
            module_time = (datetime.utcnow() - module_start).total_seconds() * 1000
            
            log_performance_metric(
                metric_name="module_import_duration",
                value=module_time,
                unit="ms",
                context={"module": module_name}
            )
            
            business_logger.info(f"📦 Imported {module_name} ({module_time:.1f}ms)")
            successful_imports += 1
            
        except Exception as e:
            module_time = (datetime.utcnow() - module_start).total_seconds() * 1000
            
            log_business_event(
                event_type="MODULE_IMPORT_FAILED",
                description=f"Failed to import workflow module: {module_name}",
                context={
                    "module": module_name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "duration_ms": module_time
                },
                level="ERROR"
            )
            failed_imports += 1
    
    total_import_time = (datetime.utcnow() - import_start).total_seconds() * 1000
    
    log_business_event(
        event_type="WORKFLOW_MODULES_IMPORTED",
        description="Workflow module import process completed",
        context={
            "total_discovered": len(discovered),
            "successful_imports": successful_imports,
            "failed_imports": failed_imports,
            "total_import_time_ms": total_import_time
        },
        level="WARNING" if failed_imports > 0 else "INFO"
    )

# ============================================================================
# API ENDPOINTS (SSE and workflow handling)
# ============================================================================

@app.get("/api/workflows")
async def list_workflows():
    """List all registered workflows and their tools"""
    request_start = datetime.utcnow()
    
    try:
        registered = get_registered_workflows()
        
        # Convert workflow names to full workflow objects
        workflows = []
        for workflow_type in registered:
            workflows.append({
                "workflow_type": workflow_type,
                "transport": get_workflow_transport(workflow_type),
                "human_loop": workflow_human_loop(workflow_type)
            })
        
        response_time = (datetime.utcnow() - request_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="api_workflows_duration",
            value=response_time,
            unit="ms",
            context={"workflows_count": len(workflows)}
        )
        
        business_logger.debug(f"📋 Workflows API called - {len(workflows)} workflows returned")
        
        return {
            "workflows": workflows,
            "count": len(workflows),
            "message": f"Found {len(workflows)} registered workflows"
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workflows")

@app.get("/api/chat/{chat_id}/messages")
async def get_chat_messages(chat_id: str, enterprise_id: str):
    """Get messages from a chat for debugging"""
    request_start = datetime.utcnow()
    
    try:
        chat_data = await mongodb_manager.load_chat_state(chat_id, enterprise_id)
        if not chat_data:
            log_business_event(
                event_type="CHAT_NOT_FOUND",
                description="Chat not found for messages API",
                context={
                    "chat_id": chat_id,
                    "enterprise_id": enterprise_id
                },
                level="WARNING"
            )
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Use new primary schema instead of deprecated session_state
        chat_history = chat_data.get("chat_history", [])
        chat_state = chat_data.get("chat_state", {})
        workflow_type = chat_data.get("workflow_type", "unknown")
        
        response_time = (datetime.utcnow() - request_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="api_chat_messages_duration",
            value=response_time,
            unit="ms",
            context={
                "chat_id": chat_id,
                "message_count": len(chat_history),
                "workflow_type": workflow_type
            }
        )
        
        chat_logger.debug(
            f"📨 Chat messages API - Chat: {chat_id}, Messages: {len(chat_history)}, "
            f"Workflow: {workflow_type}"
        )
        
        return {
            "chat_id": chat_id,
            "message_count": len(chat_history),
            "messages": chat_history,
            "workflow_type": workflow_type,
            "chat_state": chat_state  # Include current chat state info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get chat messages for {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve messages")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    health_start = datetime.utcnow()
    
    try:
        # Test MongoDB
        mongo_ping_start = datetime.utcnow()
        await mongo_client.admin.command("ping")
        mongo_ping_time = (datetime.utcnow() - mongo_ping_start).total_seconds() * 1000
        
        # Get workflow status
        status = workflow_status_summary()
        
        # Get active connections from simple transport
        connection_info = simple_transport.get_connection_info() if simple_transport else {
            "sse_connections": 0, "websocket_connections": 0, "total_connections": 0
        }

        # Calculate health check time
        health_time = (datetime.utcnow() - health_start).total_seconds() * 1000
        
        log_performance_metric(
            metric_name="health_check_duration",
            value=health_time,
            unit="ms",
            context={
                "mongodb_ping_ms": mongo_ping_time,
                "active_connections": connection_info["total_connections"],
                "workflows_count": len(status["registered_workflows"])
            }
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
        
        business_logger.debug(f"💚 Health check passed - Response time: {health_time:.1f}ms")
        
        return health_data
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")

@app.get("/api/chats/{enterprise_id}/{workflow_type}")
async def list_chats(enterprise_id: str, workflow_type: str):
    """List recent chat IDs for a given enterprise and workflow"""
    try:
        # Convert to ObjectId if possible
        try:
            eid = ObjectId(enterprise_id)
        except:
            eid = enterprise_id
        # Query workflows collection
        cursor = mongodb_manager.workflows_collection.find(
            {"enterprise_id": eid, "workflow_type": workflow_type}
        ).sort("created_at", -1)
        docs = await cursor.to_list(length=20)
        chat_ids = [doc.get("chat_id") for doc in docs]
        return {"chat_ids": chat_ids}
    except Exception as e:
        logger.error(f"❌ Failed to list chats for enterprise {enterprise_id}, workflow {workflow_type}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chats")
@app.post("/api/chats/{enterprise_id}/{workflow_type}/start")
async def start_chat(
    enterprise_id: str,
    workflow_type: str,
    payload: StartChatRequest,
):
    """Start a new chat session for the given enterprise and workflow"""
    # Generate unique chat ID
    chat_id = str(uuid4())
    
    # Get concept for enterprise
    concept = await mongodb_manager.find_latest_concept_for_enterprise(enterprise_id)
    if not concept:
        raise HTTPException(status_code=404, detail="No concept found for enterprise")
    
    # Initialize workflow in database
    workflow_id = await mongodb_manager.create_workflow_for_chat(
        chat_id=chat_id,
        enterprise_id=enterprise_id,
        concept_id=concept["_id"],
        workflow_type=workflow_type,
        user_id=payload.user_id
    )
    
    if not workflow_id:
        raise HTTPException(status_code=500, detail="Failed to initialize chat workflow")
    
    return {"chat_id": chat_id, "workflow_id": str(workflow_id)}


@app.get("/sse/{workflow_type}/{enterprise_id}/{chat_id}/{user_id}")
async def sse_endpoint(
    workflow_type: str,
    enterprise_id: str,
    chat_id: str,
    user_id: str,
):
    """SSE endpoint to stream agent responses."""
    if not simple_transport:
        raise HTTPException(status_code=503, detail="Transport service is not available.")

    # Check if this workflow uses SSE transport
    transport = get_workflow_transport(workflow_type)
    if transport != "sse":
        raise HTTPException(
            status_code=400, 
            detail=f"Workflow '{workflow_type}' uses {transport} transport, not SSE. Use the appropriate endpoint."
        )

    connection_id = f"{enterprise_id}_{chat_id}_{user_id}"
    business_logger.info(f"🔌 New SSE connection: {connection_id} for workflow '{workflow_type}'")
    
    return await simple_transport.create_sse_stream(
        chat_id=chat_id,
        user_id=user_id,
        workflow_type=workflow_type
    )

@app.websocket("/ws/{workflow_type}/{enterprise_id}/{chat_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workflow_type: str,
    enterprise_id: str,
    chat_id: str,
    user_id: str,
):
    """WebSocket endpoint for real-time agent communication."""
    if not simple_transport:
        await websocket.close(code=1000, reason="Transport service not available")
        return

    # Check if this workflow uses WebSocket transport
    transport = get_workflow_transport(workflow_type)
    if transport != "websocket":
        await websocket.close(
            code=1000, 
            reason=f"Workflow '{workflow_type}' uses {transport} transport, not WebSocket"
        )
        return

    business_logger.info(f"🔌 New WebSocket connection for workflow '{workflow_type}'")
    
    await simple_transport.handle_websocket(
        websocket=websocket,
        chat_id=chat_id,
        user_id=user_id,
        workflow_type=workflow_type
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
        workflow_type = data.get("workflow_type")  # No default, must be provided
        
        log_business_event(
            event_type="USER_INPUT_ENDPOINT_CALLED",
            description=f"User input endpoint called for chat {chat_id}",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "workflow_type": workflow_type,
                "message_length": len(message) if message else 0
            }
        )
        
        if not message:
            raise HTTPException(status_code=400, detail="'message' field is required.")

        result = await simple_transport.handle_user_input_from_api(
            chat_id=chat_id, 
            user_id=user_id, 
            workflow_type=workflow_type,
            message=message
        )
        
        log_business_event(
            event_type="USER_INPUT_PROCESSED",
            description=f"User input processed successfully for chat {chat_id}",
            context={"transport": result.get("transport")}
        )
        
        return {"status": "Message received and is being processed.", "transport": result.get("transport")}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"❌ Error handling user input for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process input: {e}")

@app.get("/api/workflows/{workflow_type}/transport")
async def get_workflow_transport_info(workflow_type: str):
    """Get transport information for a specific workflow."""
    transport = get_workflow_transport(workflow_type)
    
    return {
        "workflow_type": workflow_type,
        "transport": transport,
        "endpoints": {
            "sse": f"/sse/{workflow_type}/{{enterprise_id}}/{{chat_id}}/{{user_id}}" if transport == "sse" else None,
            "websocket": f"/ws/{workflow_type}/{{enterprise_id}}/{{chat_id}}/{{user_id}}" if transport == "websocket" else None,
            "input": f"/chat/{{enterprise_id}}/{{chat_id}}/{{user_id}}/input"
        }
    }

@app.get("/api/workflows/{workflow_type}/tools")
async def get_workflow_tools_info(workflow_type: str):
    """Get UI tools manifest for a specific workflow."""
    tools = get_workflow_tools(workflow_type)
    
    return {
        "workflow_type": workflow_type,
        "tools": tools
    }

@app.get("/api/workflows/{workflow_type}/ui-tools")
async def get_workflow_ui_tools_manifest(workflow_type: str):
    """Get UI tools manifest with schemas for frontend development."""
    try:
        # Get UI-specific tools (look for workflow_type + "_ui")
        ui_workflow_type = f"{workflow_type}_ui"
        ui_tools = get_workflow_tools(ui_workflow_type)
        
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
                        for tool_id, tool_info in registry.items():
                            # Avoid duplicates
                            if not any(item["toolId"] == tool_id for item in manifest):
                                manifest.append({
                                    "toolId": tool_id,
                                    "description": tool_info.get("description", ""),
                                    "payloadSchema": tool_info.get("payloadSchema", {}),
                                    "workflow": workflow_type
                                })
                except Exception as e:
                    logger.debug(f"Could not extract module-level UI tool registry: {e}")
        
        return {
            "workflow_type": workflow_type,
            "ui_tools_count": len(manifest),
            "ui_tools": manifest,
            "documentation": f"Each toolId must have a corresponding React component in the frontend. "
                           f"Use the payloadSchema to implement the component's props interface.",
            "usage": f"Backend emits: await channel.send_ui_tool(toolId, payload)"
        }
        
    except Exception as e:
        logger.error(f"Error getting UI tools manifest for {workflow_type}: {e}")
        return {
            "workflow_type": workflow_type,
            "ui_tools_count": 0,
            "ui_tools": [],
            "error": str(e)
        }

# ==============================================================================
# TOKEN API ENDPOINTS
# ==============================================================================

@app.get("/api/tokens/{user_id}/balance")
async def get_user_token_balance(user_id: str, appid: str = "default"):
    """
    Get user token balance.
    """
    try:
        log_business_event(
            event_type="TOKEN_BALANCE_REQUEST",
            description=f"Token balance requested for user {user_id}, app {appid}"
        )
        
        # Use the mock function (or could be real API call)
        result = _mock_get_remaining(user_id, appid)
        
        # Map the response to client expectations
        response = {
            "balance": result.get("remaining", 0),
            "remaining": result.get("remaining", 0),  # Also provide as 'remaining'
            "user_id": user_id,
            "app_id": appid,
            "is_free_trial": False,  # TODO: Integrate with actual TokenManager logic
            "free_loops_remaining": None
        }
        
        business_logger.info(f"Token balance retrieved for user {user_id}: {response['balance']} tokens")
        return response
        
    except Exception as e:
        logger.error(f"Error getting token balance for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tokens/{user_id}/consume")
async def consume_user_tokens(user_id: str, request: Request):
    """
    Consume user tokens.
    """
    try:
        body = await request.json()
        amount = body.get("amount", 0)
        app_id = body.get("app_id", "default")
        
        log_business_event(
            event_type="TOKEN_CONSUMPTION_REQUEST",
            description=f"Token consumption requested: {amount} tokens for user {user_id}, app {app_id}"
        )
        
        # Use the mock function (or could be real API call)
        result = _mock_consume_tokens(user_id, app_id, amount)
        
        if result.get("success"):
            business_logger.info(f"Consumed {amount} tokens for user {user_id}. Remaining: {result.get('remaining')}")
        else:
            business_logger.warning(f"Failed to consume {amount} tokens for user {user_id}: {result.get('error')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error consuming tokens for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workflows/config")
async def get_workflow_configs():
    """Get all workflow configurations for frontend"""
    try:
        from core.workflow.workflow_config import workflow_config
        
        configs = {}
        for workflow_type in workflow_config.get_all_workflow_types():
            configs[workflow_type] = workflow_config.get_config(workflow_type)
        
        log_business_event(
            event_type="WORKFLOW_CONFIGS_REQUESTED",
            description="Workflow configurations requested by frontend",
            context={"workflow_count": len(configs)}
        )
        
        return configs
        
    except Exception as e:
        logger.error(f"❌ Failed to get workflow configs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workflow configurations")