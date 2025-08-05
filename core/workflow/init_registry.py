# ==============================================================================
# FILE: core/workflow/init_registry.py
# DESCRIPTION: CLEAN workflow registration - self-contained handler discovery
#              NO dependencies on workflow_config for handlers
# ==============================================================================
from typing import Dict, Callable, Awaitable, Any, List, Optional
import logging
from pathlib import Path

# Import enhanced logging for workflows
from logs.logging_config import (
    get_workflow_logger,
    log_business_event
)

# Use workflow logger for registry operations
logger = get_workflow_logger(workflow_name="registry")

# Registry storage - self-contained
_WORKFLOW_HANDLERS: Dict[str, Callable[..., Awaitable[Any]]] = {}
_WORKFLOW_METADATA: Dict[str, Dict[str, Any]] = {}
_WORKFLOW_TOOLS: Dict[str, List[Callable]] = {}
_WORKFLOW_TRANSPORTS: Dict[str, str] = {}
_INITIALIZERS: List[Callable[[], Awaitable[None]]] = []

def initialize_workflow_components(workflow_name: str, base_dir: Path) -> List[str]:
    """Initialize components from YAML ui_config"""
    # Import ONLY the clean config system
    from .workflow_config import workflow_config
    
    try:
        ui_capable_agents = workflow_config.get_ui_capable_agents(workflow_name)
        
        logger.debug(f"Initializing components for workflow '{workflow_name}' in {base_dir}")
        
        if not ui_capable_agents:
            logger.debug(f"No ui_capable_agents found for {workflow_name}")
            return []
        
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
            log_business_event(
                log_event_type="WORKFLOW_COMPONENTS_DISCOVERED",
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
    """Register a complete workflow handler with transport specification"""
    def decorator(handler_func):
        _WORKFLOW_HANDLERS[workflow_name] = handler_func
        _WORKFLOW_METADATA[workflow_name] = {
            'human_loop': human_loop,
            'transport': transport,
            'auto_init_components': auto_init_components
        }
        _WORKFLOW_TRANSPORTS[workflow_name] = transport
        
        if auto_init_components:
            logger.debug(f"Event-driven UI system active for {workflow_name}")
        
        logger.debug(f"Registered workflow: {workflow_name} (human_loop={human_loop}, transport={transport})")
        return handler_func
    return decorator

def initialize_workflow_ui_components(workflow_name: str, base_dir: Path | None = None) -> List[str]:
    """Manually initialize UI components for a workflow"""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent
    
    try:
        created_files = initialize_workflow_components(workflow_name, base_dir)
        logger.debug(f"Manually initialized {len(created_files)} component manifests for {workflow_name}")
        return created_files
    except Exception as e:
        logger.error(f"❌ Failed to initialize components for {workflow_name}: {e}")
        return []

def register_workflow_tools(workflow_name: str, tools: List[Callable]):
    """Register tools for a specific workflow"""
    _WORKFLOW_TOOLS[workflow_name] = tools
    logger.debug(f"Registered {len(tools)} tools for {workflow_name}: {[t.__name__ for t in tools]}")

def get_workflow_handler(workflow_name: str) -> Callable[..., Awaitable[Any]] | None:
    """
    SELF-CONTAINED workflow handler discovery.
    
    This is the CLEAN version that doesn't depend on workflow_config for handlers.
    It only uses its own registration system OR creates handlers dynamically.
    """
    # Try to get existing handler first (case-insensitive)
    normalized_name = workflow_name.lower()
    
    # Check existing handlers with case-insensitive lookup
    for registered_name, handler in _WORKFLOW_HANDLERS.items():
        if registered_name.lower() == normalized_name:
            logger.debug(f"✅ Found registered workflow handler: {registered_name}")
            return handler
    
    # If not found, create a dynamic handler that uses orchestration_patterns
    logger.debug(f"[CLEAN-REGISTRY] Creating dynamic handler for: {workflow_name}")
    
    try:
        # Create a dynamic handler that delegates to orchestration_patterns
        async def dynamic_workflow_handler(
            enterprise_id: str,
            chat_id: str,
            user_id: Optional[str] = None,
            initial_message: Optional[str] = None,
            **kwargs
        ):
            # Import and delegate to the execution engine
            from .orchestration_patterns import run_workflow_orchestration
            
            return await run_workflow_orchestration(
                workflow_name=workflow_name,
                enterprise_id=enterprise_id,
                chat_id=chat_id,
                user_id=user_id,
                initial_message=initial_message,
                **kwargs
            )
        
        # Cache the dynamic handler for future use
        _WORKFLOW_HANDLERS[normalized_name] = dynamic_workflow_handler
        logger.debug(f"[CLEAN-REGISTRY] Created and cached dynamic handler for: {workflow_name}")
        return dynamic_workflow_handler
        
    except Exception as e:
        logger.error(f"❌ [CLEAN-REGISTRY] Failed to create handler for {workflow_name}: {e}")
        return None

def get_registered_workflows() -> Dict[str, Dict[str, Any]]:
    """Get all registered workflows and their metadata"""
    return {name: _WORKFLOW_METADATA.get(name, {}) for name in _WORKFLOW_HANDLERS.keys()}

def get_workflow_metadata(workflow_name: str) -> Dict[str, Any]:
    """Get metadata for a specific workflow"""
    return _WORKFLOW_METADATA.get(workflow_name, {})

def run_initializers():
    """Execute all registered initialization coroutines"""
    import asyncio
    
    async def run_all():
        for initializer in _INITIALIZERS:
            try:
                await initializer()
                logger.debug(f"✅ Executed initializer: {initializer.__name__}")
            except Exception as e:
                logger.error(f"❌ Initializer failed: {initializer.__name__}: {e}")
    
    if _INITIALIZERS:
        logger.debug(f"Running {len(_INITIALIZERS)} workflow initializers...")
        asyncio.run(run_all())
        logger.debug("All workflow initializers completed")

def get_initialization_coroutines() -> List[Callable[[], Awaitable[None]]]:
    """Get all registered initialization coroutines"""
    return _INITIALIZERS.copy()

def workflow_status_summary() -> Dict[str, Any]:
    """Get status summary of all workflows"""
    registered_workflows = list(_WORKFLOW_HANDLERS.keys())
    total_workflows = len(registered_workflows)
    total_tools = sum(len(tools) for tools in _WORKFLOW_TOOLS.values())
    total_initializers = len(_INITIALIZERS)
    
    summary = f"{total_workflows} workflows, {total_tools} tools, {total_initializers} initializers"
    
    return {
        "total_workflows": total_workflows,
        "registered_workflows": registered_workflows,
        "metadata": _WORKFLOW_METADATA.copy(),
        "total_tools": total_tools,
        "total_initializers": total_initializers,
        "summary": summary
    }

def get_workflow_transport(workflow_name: str) -> str:
    """Get transport type for a workflow"""
    return _WORKFLOW_TRANSPORTS.get(workflow_name, "websocket")

def get_workflow_tools(workflow_name: str) -> List[Callable]:
    """Get tools registered for a workflow"""
    return _WORKFLOW_TOOLS.get(workflow_name, [])

def get_or_discover_workflow_handler(workflow_name: str) -> Callable[..., Awaitable[Any]] | None:
    """
    Get workflow handler with discovery fallback.
    This is an alias for get_workflow_handler for backward compatibility.
    """
    return get_workflow_handler(workflow_name)

def workflow_human_loop(workflow_name: str) -> bool:
    """Check if workflow requires human interaction"""
    metadata = _WORKFLOW_METADATA.get(workflow_name, {})
    return metadata.get('human_loop', False)

# ==============================================================================
# CLEAN REGISTRY - SELF-CONTAINED, NO CIRCULAR DEPENDENCIES
# ==============================================================================
