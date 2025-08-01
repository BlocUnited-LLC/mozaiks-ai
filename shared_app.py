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
from typing import Optional, Dict, Any
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

from core.core_config import make_llm_config, get_mongo_client
from core.transport.simple_transport import SimpleTransport
from core.workflow.init_registry import get_initialization_coroutines, get_registered_workflows, workflow_status_summary, get_workflow_transport, get_workflow_tools, workflow_human_loop
from core.data.persistence_manager import PersistenceManager

# Simple mock functions for token management (TODO: replace with real token service)
def _mock_get_remaining(user_id: str, app_id: str = "default") -> Dict[str, Any]:
    """Mock function for getting user token balance"""
    return {"remaining": 10000, "user_id": user_id, "app_id": app_id}

def _mock_consume_tokens(user_id: str, app_id: str, amount: int) -> Dict[str, Any]:
    """Mock function for consuming user tokens"""
    return {"success": True, "remaining": 9000, "consumed": amount, "user_id": user_id}

# Initialize persistence manager
mongodb_manager = PersistenceManager()

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
        # Initialize simple transport with basic LLM config
        streaming_start = datetime.utcnow()
        _, streaming_llm_config = await make_llm_config()
        simple_transport = SimpleTransport(streaming_llm_config)
        
        streaming_time = (datetime.utcnow() - streaming_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="streaming_config_init_duration",
            value=streaming_time,
            context={
                "config_keys": list(streaming_llm_config.keys()) if streaming_llm_config else [],
                "streaming_enabled": True  # AG2 IOStream handles streaming
            }
        )
        
        business_logger.info(f"🔌 Simple transport initialized - Streaming: True (AG2 IOStream)")

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

        # Component system is now event-driven - no registration needed
        registry_start = datetime.utcnow()
        business_logger.info("🎯 Component system: Event-driven (ui_tools → transport.send_tool_event() → React)")
        
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
    """
    Workflow system startup - using runtime auto-discovery.
    No more scanning for initializer.py files - workflows are discovered on-demand.
    """
    business_logger.info(f"🔍 Workflow system ready - using runtime auto-discovery")

    scan_start = datetime.utcnow()
    
    # Runtime auto-discovery means no upfront imports needed
    # Workflows will be discovered when requested via WebSocket
    
    scan_time = (datetime.utcnow() - scan_start).total_seconds() * 1000
    
    log_performance_metric(
        metric_name="workflow_discovery_duration",
        value=scan_time,
        unit="ms",
        context={
            "discovery_mode": "runtime_auto_discovery",
            "upfront_imports": 0
        }
    )
    
    business_logger.info(f"🚀 Workflow system ready - auto-discovery will handle new requests on-demand")

    log_business_event(
        event_type="WORKFLOW_SYSTEM_READY",
        description="Workflow system initialized with runtime auto-discovery",
        context={
            "scan_duration_ms": scan_time,
            "discovery_mode": "runtime_on_demand"
        }
    )

# ============================================================================
# API ENDPOINTS (WebSocket and workflow handling)
# ============================================================================

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
        
        # Use primary schema
        chat_history = chat_data.get("chat_history", [])
        chat_state = chat_data.get("chat_state", {})
        workflow_name = chat_data.get("workflow_name", "unknown")
        
        response_time = (datetime.utcnow() - request_start).total_seconds() * 1000
        log_performance_metric(
            metric_name="api_chat_messages_duration",
            value=response_time,
            unit="ms",
            context={
                "chat_id": chat_id,
                "message_count": len(chat_history),
                "workflow_name": workflow_name
            }
        )
        
        chat_logger.debug(
            f"📨 Chat messages API - Chat: {chat_id}, Messages: {len(chat_history)}, "
            f"Workflow: {workflow_name}"
        )
        
        return {
            "chat_id": chat_id,
            "message_count": len(chat_history),
            "messages": chat_history,
            "workflow_name": workflow_name,
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
            "websocket_connections": 0, "total_connections": 0
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

@app.post("/api/chats/{enterprise_id}/{workflow_name}/start")
async def start_chat(enterprise_id: str, workflow_name: str, request: Request):
    """Start a new chat session for a workflow"""
    try:
        data = await request.json()
        user_id = data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        # Generate a new chat ID
        chat_id = str(uuid4())
        
        log_business_event(
            event_type="CHAT_SESSION_STARTED",
            description=f"New chat session started for workflow {workflow_name}",
            context={
                "enterprise_id": enterprise_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "chat_id": chat_id
            }
        )
        
        return {
            "success": True,
            "chat_id": chat_id,
            "workflow_name": workflow_name,
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "websocket_url": f"/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}",
            "message": "Chat session created successfully"
        }
        
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
        except:
            eid = enterprise_id
            
        # Query chat sessions collection with the refactored schema
        cursor = mongodb_manager.chat_sessions_collection.find(
            {"enterprise_id": eid, "workflow_name": workflow_name}
        ).sort("created_at", -1)
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

    business_logger.info(f"🔌 New WebSocket connection for workflow '{workflow_name}'")
    
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
        
        log_business_event(
            event_type="USER_INPUT_ENDPOINT_CALLED",
            description=f"User input endpoint called for chat {chat_id}",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "workflow_name": workflow_name,
                "message_length": len(message) if message else 0
            }
        )
        
        if not message:
            raise HTTPException(status_code=400, detail="'message' field is required.")

        result = await simple_transport.handle_user_input_from_api(
            chat_id=chat_id, 
            user_id=user_id, 
            workflow_name=workflow_name,
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
            log_business_event(
                event_type="USER_INPUT_RESPONSE_SUBMITTED",
                description=f"User input response submitted for request {input_request_id}",
                context={
                    "input_request_id": input_request_id,
                    "input_length": len(user_input)
                }
            )
            return {"status": "success", "message": "User input submitted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Input request not found or already completed")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"❌ Error submitting user input response: {e}")
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
                        for tool_id, tool_info in registry.items():
                            # Avoid duplicates
                            if not any(item["toolId"] == tool_id for item in manifest):
                                manifest.append({
                                    "toolId": tool_id,
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
            "documentation": f"Each toolId must have a corresponding React component in the frontend. "
                           f"Use the payloadSchema to implement the component's props interface.",
            "usage": f"Backend emits: await channel.send_ui_tool(toolId, payload)"
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
async def get_user_token_balance(user_id: str, appid: str = "default"):
    """Get user token balance"""
    try:
        log_business_event(
            event_type="TOKEN_BALANCE_REQUEST",
            description=f"Token balance requested for user {user_id}, app {appid}"
        )
        
        # Use the mock function for token balance
        result = _mock_get_remaining(user_id, appid)

        # For now, use mock data for free trial info since the TokenManager interface changed
        # TODO: Update TokenManager to provide proper budget/trial methods
        is_free_trial = False
        free_loops_remaining = None

        # Map the response to client expectations
        response = {
            "balance": result.get("remaining", 0),
            "remaining": result.get("remaining", 0),  # Also provide as 'remaining'
            "user_id": user_id,
            "app_id": appid,
            "is_free_trial": is_free_trial,
            "free_loops_remaining": free_loops_remaining
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

@app.get("/api/workflows")
async def get_workflows():
    """Get all workflows for frontend (alias for /api/workflows/config)"""
    try:
        from core.workflow.workflow_config import workflow_config
        
        configs = {}
        for workflow_name in workflow_config.get_all_workflow_names():
            configs[workflow_name] = workflow_config.get_config(workflow_name)
        
        log_business_event(
            event_type="WORKFLOWS_REQUESTED",
            description="Workflows requested by frontend",
            context={"workflow_count": len(configs)}
        )
        
        return configs
        
    except Exception as e:
        logger.error(f"❌ Failed to get workflows: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve workflows")

@app.get("/api/workflows/config")
async def get_workflow_configs():
    """Get all workflow configurations for frontend"""
    try:
        from core.workflow.workflow_config import workflow_config
        
        configs = {}
        for workflow_name in workflow_config.get_all_workflow_names():
            configs[workflow_name] = workflow_config.get_config(workflow_name)
        
        log_business_event(
            event_type="WORKFLOW_CONFIGS_REQUESTED",
            description="Workflow configurations requested by frontend",
            context={"workflow_count": len(configs)}
        )
        
        return configs
        
    except Exception as e:
        logger.error(f"❌ Failed to get workflow configs: {e}")
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
        
        log_business_event(
            event_type="COMPONENT_ACTION_ENDPOINT_CALLED",
            description=f"Component action endpoint called for chat {chat_id}",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "component_id": component_id,
                "action_type": action_type
            }
        )
        
        if not component_id or not action_type:
            raise HTTPException(status_code=400, detail="'component_id' and 'action_type' fields are required.")

        logger.info(f"📋 Received component action via HTTP: {component_id} -> {action_type}")

        try:
            # Component actions are now handled by AG2 tools via the workflow system
            # The ContextVariablesAgent in the Generator workflow handles context updates
            logger.info(f"📋 Component action received via HTTP: {component_id} -> {action_type}")
            
            # Send this action as a tool event to the active workflow
            await simple_transport.send_tool_event(
                tool_id=component_id,
                payload={
                    "action_type": action_type,
                    "action_data": action_data,
                    "source": "http_endpoint"
                },
                display="inline",
                chat_id=chat_id
            )
            
            logger.info(f"✅ Component action forwarded to AG2 workflow via tool event")
            
            log_business_event(
                event_type="COMPONENT_ACTION_PROCESSED",
                description=f"Component action processed successfully for chat {chat_id}",
                context={"forwarded_to_workflow": True}
            )
            
            return {
                "status": "success",
                "message": "Component action forwarded to workflow",
                "timestamp": datetime.utcnow().isoformat()
            }
                
        except Exception as action_error:
            logger.error(f"❌ Component action forwarding failed (HTTP): {action_error}")
            raise HTTPException(status_code=500, detail=f"Component action forwarding failed: {action_error}")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"❌ Error handling component action for chat {chat_id}: {e}")
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
            log_business_event(
                event_type="UI_TOOL_RESPONSE_SUBMITTED",
                description=f"UI tool response submitted for event {event_id}",
                context={
                    "event_id": event_id,
                    "response_status": response_data.get("status", "unknown"),
                    "tool_id": response_data.get("data", {}).get("toolId", "unknown")
                }
            )
            return {"status": "success", "message": "UI tool response submitted successfully"}
        else:
            raise HTTPException(status_code=404, detail="UI tool event not found or already completed")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error(f"❌ Error submitting UI tool response: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit UI tool response: {e}")