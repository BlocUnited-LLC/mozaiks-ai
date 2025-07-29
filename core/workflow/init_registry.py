# ==============================================================================
# FILE: init_registry.py
# DESCRIPTION: Central registry for workflows and tools - workflow agnostic
# ==============================================================================
from typing import Dict, Callable, Awaitable, Any, List, Optional
import logging
from pathlib import Path
from core.transport.ag2_iostream import AG2StreamingManager

# Import enhanced logging for workflows
from logs.logging_config import (
    get_workflow_logger,
    log_business_event
)

# Use workflow logger for registry operations
logger = get_workflow_logger(workflow_name="registry")

# Registry storage
_WORKFLOW_HANDLERS: Dict[str, Callable[..., Awaitable[Any]]] = {}
_WORKFLOW_METADATA: Dict[str, Dict[str, Any]] = {}
_WORKFLOW_TOOLS: Dict[str, List[Callable]] = {}  # Tools per workflow
_WORKFLOW_TRANSPORTS: Dict[str, str] = {}  # Transport type per workflow (websocket only)
_INITIALIZERS: List[Callable[[], Awaitable[None]]] = []

def initialize_workflow_components(workflow_name: str, base_dir: Path) -> List[str]:
    """Initialize components from workflow.json ui_capable_agents"""
    from .workflow_config import WorkflowConfig
    
    try:
        workflow_config = WorkflowConfig()
        ui_capable_agents = workflow_config.get_ui_capable_agents(workflow_name)
        
        # Log the initialization context
        logger.debug(f"Initializing components for workflow '{workflow_name}' in {base_dir}")
        
        if not ui_capable_agents:
            logger.debug(f"No ui_capable_agents found for {workflow_name}")
            return []
        
        # Count components from ui_capable_agents
        component_count = 0
        components_found = []
        
        for agent in ui_capable_agents:
            agent_name = agent.get("name", "Unknown")
            components = agent.get("components", [])
            
            logger.debug(f"Processing agent '{agent_name}' with {len(components)} components")
            
            for component in components:
                component_name = component.get("name")
                component_type = component.get("type")
                if component_name and component_type:
                    component_count += 1
                    components_found.append(f"{component_name} ({component_type})")
        
        if component_count > 0:
            logger.info(f"🎨 Found {component_count} UI components in {workflow_name}: {', '.join(components_found)}")
            
            # Log business event for component discovery
            log_business_event(
                event_type="WORKFLOW_COMPONENTS_DISCOVERED",
                description=f"Discovered {component_count} UI components for {workflow_name}",
                context={
                    "workflow_name": workflow_name,
                    "component_count": component_count,
                    "components": components_found
                }
            )
        else:
            logger.debug(f"No components defined in ui_capable_agents for {workflow_name}")
        
        return components_found
        
    except Exception as e:
        logger.warning(f"Failed to initialize components for {workflow_name}: {e}")
        return []

def add_initialization_coroutine(coro: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    """Register startup coroutine"""
    _INITIALIZERS.append(coro)
    logger.debug(f"Registered initializer: {coro.__name__}")
    return coro

def register_workflow(workflow_name: str, human_loop: bool = False, transport: str = "websocket", auto_init_components: bool = False):
    """Register a complete workflow handler with transport specification
    
    Args:
        workflow_name: Unique identifier for the workflow
        human_loop: Whether workflow requires human interaction
        transport: Transport type - "websocket" only
        auto_init_components: Whether to automatically initialize UI components for this workflow
    """
    def decorator(handler_func):
        _WORKFLOW_HANDLERS[workflow_name] = handler_func
        _WORKFLOW_METADATA[workflow_name] = {
            'human_loop': human_loop,
            'transport': transport,
            'auto_init_components': auto_init_components
        }
        _WORKFLOW_TRANSPORTS[workflow_name] = transport
        
        # Auto-initialize component manifests if enabled
        if auto_init_components:
            # Component system is now event-driven via ui_tools → transport layer
            logger.info(f"🎨 Event-driven UI system active for {workflow_name} (no manifest initialization needed)")
        else:
            logger.info(f"🎨 Auto-initialized 0 component manifests for {workflow_name}")
        
        logger.info(f"✅ Registered workflow: {workflow_name} (human_loop={human_loop}, transport={transport})")
        return handler_func
    return decorator

def initialize_workflow_ui_components(workflow_name: str, base_dir: Path | None = None) -> List[str]:
    """
    Manually initialize UI components for a workflow.
    Useful for workflows that need custom component setup.
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent  # Get to project root
    
    try:
        created_files = initialize_workflow_components(workflow_name, base_dir)
        logger.info(f"🎨 Manually initialized {len(created_files)} component manifests for {workflow_name}")
        return created_files
    except Exception as e:
        logger.error(f"❌ Failed to initialize components for {workflow_name}: {e}")
        return []

def register_workflow_tools(workflow_name: str, tools: List[Callable]):
    """Register tools for a specific workflow"""
    _WORKFLOW_TOOLS[workflow_name] = tools
    logger.info(f"🔧 Registered {len(tools)} tools for {workflow_name}: {[t.__name__ for t in tools]}")

def get_workflow_handler(workflow_name: str) -> Callable[..., Awaitable[Any]] | None:
    """Get workflow handler by type"""
    return _WORKFLOW_HANDLERS.get(workflow_name)

def get_workflow_tools(workflow_name: str) -> List[Callable]:
    """Get tools for a specific workflow"""
    return _WORKFLOW_TOOLS.get(workflow_name, [])

def get_registered_workflows() -> List[str]:
    """Get list of registered workflow types"""
    return list(_WORKFLOW_HANDLERS.keys())
    
def get_workflow_transport(workflow_name: str) -> str:
    """Get the preferred transport for a workflow (websocket only)"""
    return _WORKFLOW_TRANSPORTS.get(workflow_name, "websocket")

def get_workflows_by_transport() -> Dict[str, List[str]]:
    """Get workflows grouped by their transport type"""
    transport_groups = {"websocket": []}
    for workflow, transport in _WORKFLOW_TRANSPORTS.items():
        if transport in transport_groups:
            transport_groups[transport].append(workflow)
    return transport_groups

def workflow_human_loop(workflow_name: str) -> bool:
    """Return True if the workflow requires human in the loop"""
    return _WORKFLOW_METADATA.get(workflow_name, {}).get('human_loop', False)

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
        "summary": f"{len(_WORKFLOW_HANDLERS)} workflows ({len(transport_groups['websocket'])} WebSocket), {sum(len(tools) for tools in _WORKFLOW_TOOLS.values())} total tools"
    }

async def run_workflow_with_streaming(
    workflow_name: str, 
    enterprise_id: str, 
    chat_id: str, 
    user_id: str, 
    initial_message: str, 
    streaming_speed: str = "fast"
) -> Any:
    """
    Enhanced workflow runner with AG2 token streaming support using SimpleTransport singleton.
    
    This function integrates the new AG2StreamingIOStream with any workflow handler.
    """
    # Get the workflow handler
    handler = get_workflow_handler(workflow_name)
    if not handler:
        raise ValueError(f"No handler registered for workflow type: {workflow_name}")
    
    # Get SimpleTransport singleton for communication
    from core.transport.simple_transport import SimpleTransport
    transport = SimpleTransport._get_instance()
    if not transport:
        raise RuntimeError(f"SimpleTransport instance not available for {workflow_name} workflow")
    
    # Set up AG2 streaming
    streaming_manager = AG2StreamingManager(chat_id, enterprise_id)
    streaming_manager.setup_streaming(streaming_speed=streaming_speed)
    
    try:
        logger.info(f"🚀 Starting {workflow_name} workflow with AG2 streaming (speed: {streaming_speed})")
        
        # Run the workflow handler with streaming enabled
        result = await handler(
            enterprise_id=enterprise_id,
            chat_id=chat_id,
            user_id=user_id,
            initial_message=initial_message
        )
        
        logger.info(f"✅ Completed {workflow_name} workflow with streaming")
        return result
        
    finally:
        # Always restore the original IOStream
        streaming_manager.restore_original_iostream()
        logger.debug("🔄 AG2 IOStream restored")

# ==============================================================================
# AUTO-DISCOVERY SYSTEM - Eliminates need for workflow-specific initializer.py files
# ==============================================================================

def auto_discover_and_register_workflows():
    """
    Auto-discover all workflows from workflow.json files and register them.
    This eliminates the need for individual initializer.py files in each workflow.
    """
    import json
    import importlib
    from pathlib import Path
    
    workflows_dir = Path(__file__).parent.parent.parent / "workflows"
    if not workflows_dir.exists():
        logger.warning(f"Workflows directory not found: {workflows_dir}")
        return
    
    registered_count = 0
    
    # Scan all workflow directories
    for workflow_dir in workflows_dir.iterdir():
        if not workflow_dir.is_dir() or workflow_dir.name.startswith('.'):
            continue
            
        workflow_json = workflow_dir / "workflow.json"
        if not workflow_json.exists():
            continue
            
        try:
            # Load workflow configuration
            with open(workflow_json, 'r') as f:
                config = json.load(f)
            
            workflow_name = workflow_dir.name.lower()
            
            # Auto-discover agent factory
            agents_factory = None
            try:
                agents_module = importlib.import_module(f"workflows.{workflow_name.title()}.Agents")
                agents_factory = getattr(agents_module, "define_agents", None)
            except (ImportError, AttributeError) as e:
                logger.warning(f"Could not import agents for {workflow_name}: {e}")
            
            # Auto-discover context factory  
            context_factory = None
            try:
                context_module = importlib.import_module(f"workflows.{workflow_name.title()}.ContextVariables")
                context_factory = getattr(context_module, "get_context", None)
            except (ImportError, AttributeError) as e:
                logger.warning(f"Could not import context for {workflow_name}: {e}")
            
            # Create auto-generated workflow handler
            def create_workflow_handler(wf_type, agents_fact, context_fact):
                async def workflow_handler(enterprise_id: str, chat_id: str, user_id: Optional[str] = None, initial_message: Optional[str] = None):
                    from core.workflow.groupchat_manager import run_workflow_orchestration
                    from core.transport.simple_transport import SimpleTransport
                    
                    # Get LLM config from transport
                    transport = SimpleTransport._get_instance()
                    if not transport:
                        raise RuntimeError(f"SimpleTransport instance not available for {wf_type}")
                    
                    llm_config = transport.default_llm_config
                    if not llm_config:
                        raise ValueError(f"No LLM config available for {wf_type}")
                    
                    # Call workflow orchestration with auto-discovered factories
                    return await run_workflow_orchestration(
                        workflow_name=wf_type,
                        llm_config=llm_config,
                        enterprise_id=enterprise_id,
                        chat_id=chat_id,
                        user_id=user_id,
                        initial_message=initial_message,
                        agents_factory=agents_fact,
                        context_factory=context_fact
                    )
                return workflow_handler
            
            # Register the auto-generated workflow
            workflow_handler = create_workflow_handler(workflow_name, agents_factory, context_factory)
            
            # Extract configuration from workflow.json
            human_loop = config.get("human_in_the_loop", False)
            
            # Register using the decorator pattern
            register_workflow(
                workflow_name=workflow_name,
                human_loop=human_loop,
                transport="websocket",
                auto_init_components=True
            )(workflow_handler)
            
            # Also register a startup initialization coroutine for tool discovery
            def create_startup_handler(wf_type):
                async def startup_handler():
                    from core.workflow.tool_registry import WorkflowToolRegistry
                    from logs.logging_config import log_business_event
                    
                    try:
                        # Pre-discover tools for group chat initialization
                        tool_registry = WorkflowToolRegistry(wf_type)
                        tool_registry.load_configuration()
                        
                        log_business_event(
                            event_type=f"{wf_type.upper()}_AUTO_STARTUP_COMPLETED",
                            description=f"Auto-discovered {wf_type} workflow initialization completed"
                        )
                        
                        logger.info(f"🔧 Auto-initialized tools for workflow: {wf_type}")
                        
                    except Exception as e:
                        log_business_event(
                            event_type=f"{wf_type.upper()}_AUTO_STARTUP_FAILED", 
                            description=f"Auto-discovered {wf_type} workflow initialization failed",
                            context={"error": str(e)},
                            level="ERROR"
                        )
                        logger.error(f"❌ Auto-initialization failed for {wf_type}: {e}")
                        raise
                        
                return startup_handler
            
            # Register the startup handler
            startup_handler = create_startup_handler(workflow_name)
            add_initialization_coroutine(startup_handler)
            
            logger.info(f"🤖 Auto-registered workflow: {workflow_name} from {workflow_json}")
            registered_count += 1
            
        except Exception as e:
            logger.error(f"❌ Failed to auto-register workflow {workflow_dir.name}: {e}")
    
    logger.info(f"🎯 Auto-discovery complete: {registered_count} workflows registered")

# Auto-discover and register workflows on module import
try:
    auto_discover_and_register_workflows()
except Exception as e:
    logger.error(f"❌ Auto-discovery failed: {e}")