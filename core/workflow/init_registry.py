# ==============================================================================
# FILE: init_registry.py
# DESCRIPTION: Central registry for workflows and tools - workflow agnostic
# ==============================================================================
from typing import Dict, Callable, Awaitable, Any, List
import logging
from pathlib import Path
from core.transport.ag2_iostream import AG2StreamingManager

logger = logging.getLogger(__name__)

# Registry storage
_WORKFLOW_HANDLERS: Dict[str, Callable[..., Awaitable[Any]]] = {}
_WORKFLOW_METADATA: Dict[str, Dict[str, Any]] = {}
_WORKFLOW_TOOLS: Dict[str, List[Callable]] = {}  # Tools per workflow
_WORKFLOW_TRANSPORTS: Dict[str, str] = {}  # Transport type per workflow (sse, websocket)
_INITIALIZERS: List[Callable[[], Awaitable[None]]] = []

# Import component generator
from .component_generator import initialize_workflow_components

def add_initialization_coroutine(coro: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    """Register startup coroutine"""
    _INITIALIZERS.append(coro)
    logger.debug(f"Registered initializer: {coro.__name__}")
    return coro

def register_workflow(workflow_type: str, human_loop: bool = False, transport: str = "sse", auto_init_components: bool = True):
    """Register a complete workflow handler with transport specification
    
    Args:
        workflow_type: Unique identifier for the workflow
        human_loop: Whether workflow requires human interaction
        transport: Transport type - "sse" or "websocket"
        auto_init_components: Whether to automatically initialize UI components for this workflow
    """
    def decorator(handler_func):
        _WORKFLOW_HANDLERS[workflow_type] = handler_func
        _WORKFLOW_METADATA[workflow_type] = {
            'human_loop': human_loop,
            'transport': transport,
            'auto_init_components': auto_init_components
        }
        _WORKFLOW_TRANSPORTS[workflow_type] = transport
        
        # Auto-initialize component manifests if enabled
        if auto_init_components:
            try:
                base_dir = Path(__file__).parent.parent.parent  # Get to project root
                created_files = initialize_workflow_components(workflow_type, workflow_type, base_dir)
                logger.info(f"🎨 Auto-initialized {len(created_files)} component manifests for {workflow_type}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to auto-initialize components for {workflow_type}: {e}")
        
        logger.info(f"✅ Registered workflow: {workflow_type} (human_loop={human_loop}, transport={transport})")
        return handler_func
    return decorator

def initialize_workflow_ui_components(workflow_type: str, base_dir: Path | None = None) -> List[str]:
    """
    Manually initialize UI components for a workflow.
    Useful for workflows that need custom component setup.
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent  # Get to project root
    
    try:
        created_files = initialize_workflow_components(workflow_type, workflow_type, base_dir)
        logger.info(f"🎨 Manually initialized {len(created_files)} component manifests for {workflow_type}")
        return created_files
    except Exception as e:
        logger.error(f"❌ Failed to initialize components for {workflow_type}: {e}")
        return []

def register_workflow_tools(workflow_type: str, tools: List[Callable]):
    """Register tools for a specific workflow"""
    _WORKFLOW_TOOLS[workflow_type] = tools
    logger.info(f"🔧 Registered {len(tools)} tools for {workflow_type}: {[t.__name__ for t in tools]}")

def get_workflow_handler(workflow_type: str) -> Callable[..., Awaitable[Any]] | None:
    """Get workflow handler by type"""
    return _WORKFLOW_HANDLERS.get(workflow_type)

def get_workflow_tools(workflow_type: str) -> List[Callable]:
    """Get tools for a specific workflow"""
    return _WORKFLOW_TOOLS.get(workflow_type, [])

def get_registered_workflows() -> List[str]:
    """Get list of registered workflow types"""
    return list(_WORKFLOW_HANDLERS.keys())
    
def get_workflow_transport(workflow_type: str) -> str:
    """Get the preferred transport for a workflow (sse or websocket)"""
    return _WORKFLOW_TRANSPORTS.get(workflow_type, "sse")

def get_workflows_by_transport() -> Dict[str, List[str]]:
    """Get workflows grouped by their transport type"""
    transport_groups = {"sse": [], "websocket": []}
    for workflow, transport in _WORKFLOW_TRANSPORTS.items():
        if transport in transport_groups:
            transport_groups[transport].append(workflow)
    return transport_groups

def workflow_human_loop(workflow_type: str) -> bool:
    """Return True if the workflow requires human in the loop"""
    return _WORKFLOW_METADATA.get(workflow_type, {}).get('human_loop', False)

def get_workflows_with_tools() -> Dict[str, List[str]]:
    """Get workflows and their associated tools"""
    return {
        workflow: [tool.__name__ for tool in tools] 
        for workflow, tools in _WORKFLOW_TOOLS.items()
    }

def get_initialization_coroutines() -> List[Callable[[], Awaitable[None]]]:
    """Get startup coroutines"""
    return list(_INITIALIZERS)

def workflow_status_summary() -> Dict[str, Any]:
    """Get comprehensive summary of registered workflows and tools"""
    transport_groups = get_workflows_by_transport()
    return {
        "total_workflows": len(_WORKFLOW_HANDLERS),
        "registered_workflows": list(_WORKFLOW_HANDLERS.keys()),
        "transport_groups": transport_groups,
        "workflows_with_tools": get_workflows_with_tools(),
        "total_tools": sum(len(tools) for tools in _WORKFLOW_TOOLS.values()),
        "initialization_coroutines": len(_INITIALIZERS),
        "summary": f"{len(_WORKFLOW_HANDLERS)} workflows ({len(transport_groups['sse'])} SSE, {len(transport_groups['websocket'])} WebSocket), {sum(len(tools) for tools in _WORKFLOW_TOOLS.values())} total tools"
    }

async def run_workflow_with_streaming(
    workflow_type: str, 
    enterprise_id: str, 
    chat_id: str, 
    user_id: str, 
    initial_message: str, 
    communication_channel,
    streaming_speed: str = "fast"
) -> Any:
    """
    Enhanced workflow runner with AG2 token streaming support.
    
    This function integrates the new AG2StreamingIOStream with any workflow handler.
    """
    # Get the workflow handler
    handler = get_workflow_handler(workflow_type)
    if not handler:
        raise ValueError(f"No handler registered for workflow type: {workflow_type}")
    
    # Set up AG2 streaming
    streaming_manager = AG2StreamingManager(communication_channel, chat_id, enterprise_id)
    streaming_iostream = streaming_manager.setup_streaming(streaming_speed=streaming_speed)
    
    try:
        logger.info(f"🚀 Starting {workflow_type} workflow with AG2 streaming")
        
        # Run the workflow handler with streaming enabled
        result = await handler(
            enterprise_id=enterprise_id,
            chat_id=chat_id,
            user_id=user_id,
            initial_message=initial_message,
            communication_channel=communication_channel
        )
        
        logger.info(f"✅ Completed {workflow_type} workflow with streaming")
        return result
        
    finally:
        # Always restore the original IOStream
        streaming_manager.restore_original_iostream()
        logger.debug("🔄 AG2 IOStream restored")