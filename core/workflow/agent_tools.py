# ============================================================================
# FILE: core/workflow/agent_tools.py
# DESCRIPTION:
#   Agent tool function loading from workflows/<flow>/tools.json
#   Loads ALL tools (Agent_Tool and UI_Tool) as agent functions.
#   UI_Tools get special handling during execution but are still bound to agents.
#   
#   WEBSOCKET PATH PARAMETER INJECTION:
#   Automatically injects WebSocket path parameters from shared_app.py:
#   /ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}
#   These are available to all tool functions for .py/.js stub generation:
#   - workflow_name: Current workflow being executed
#   - enterprise_id: Enterprise context from WebSocket path  
#   - chat_id: Chat session ID from WebSocket path
#   - user_id: User ID from WebSocket path (optional)
#   
#   NOTE: UI interaction handling logic lives in ui_tools.py.
# ============================================================================
from __future__ import annotations
import logging
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional
import inspect
import functools
import contextvars
from threading import RLock

import json

logger = logging.getLogger(__name__)

# Use contextvars to ensure propagation across asyncio tasks
_cv_chat_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("mozaiks_chat_id", default=None)
_cv_enterprise_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("mozaiks_enterprise_id", default=None)
_cv_workflow_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("mozaiks_workflow_name", default=None)
_cv_context_variables: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("mozaiks_context_variables", default=None)

# Fallback store for cases where contextvars don't propagate across threads
_fallback_lock = RLock()
_fallback_context: Dict[str, Any] = {}

def set_current_execution_context(chat_id: str, enterprise_id: str, workflow_name: str, context_variables: Any = None):
    """Set execution context for tool injection (async-safe via contextvars)."""
    _cv_chat_id.set(chat_id)
    _cv_enterprise_id.set(enterprise_id)
    _cv_workflow_name.set(workflow_name)
    _cv_context_variables.set(context_variables)
    # Also update fallback for cross-thread access (e.g., tool runs in threadpool)
    try:
        with _fallback_lock:
            _fallback_context.clear()
            _fallback_context.update(
                {
                    "chat_id": chat_id,
                    "enterprise_id": enterprise_id,
                    "workflow_name": workflow_name,
                    "context_variables": context_variables,
                }
            )
    except Exception:
        # Never fail set due to fallback issues
        pass

def get_current_execution_context():
    """Get the current execution context (chat_id, enterprise_id, workflow_name, context_variables)."""
    chat_id = _cv_chat_id.get()
    enterprise_id = _cv_enterprise_id.get()
    workflow_name = _cv_workflow_name.get()
    context_variables = _cv_context_variables.get()
    # If any are missing, attempt to use fallback (cross-thread scenario)
    if not chat_id or not enterprise_id or not workflow_name:
        try:
            with _fallback_lock:
                fb_chat = _fallback_context.get("chat_id")
                fb_ent = _fallback_context.get("enterprise_id")
                fb_wf = _fallback_context.get("workflow_name")
                fb_ctx = _fallback_context.get("context_variables")
            # Only apply fallback for the missing parts
            chat_id = chat_id or fb_chat
            enterprise_id = enterprise_id or fb_ent
            workflow_name = workflow_name or fb_wf
            context_variables = context_variables or fb_ctx
            if chat_id and enterprise_id and workflow_name:
                logger.debug("[TOOLS] Using fallback execution context (cross-thread) for injection")
        except Exception:
            # Ignore fallback errors
            pass
    return (chat_id, enterprise_id, workflow_name, context_variables)

def clear_current_execution_context():
    """Clear execution context (reset to defaults)."""
    _cv_chat_id.set(None)
    _cv_enterprise_id.set(None)
    _cv_workflow_name.set(None)
    _cv_context_variables.set(None)
    try:
        with _fallback_lock:
            _fallback_context.clear()
    except Exception:
        pass


def _wrap_function_with_context_injection(func: Callable, workflow_name: str) -> Callable:
    """
    Wrap a tool function to inject context variables if it expects them.
    
    AG2 doesn't automatically inject ContextVariables into tool functions.
    This wrapper checks if the function accepts context-related parameters
    and injects them from the current AG2 execution context.
    """
    try:
        sig = inspect.signature(func)
        param_names = set(sig.parameters.keys())
        
        # Check if function expects context-related parameters
        context_params = {
            'context_variables', 'chat_id', 'enterprise_id',
            'workflow_name', 'workflow'
        }
        needs_injection = bool(context_params.intersection(param_names))
        
        if not needs_injection:
            return func
        
        logger.debug(f"[TOOLS] Function {func.__name__} needs context injection for params: {context_params.intersection(param_names)}")
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get context from thread-local storage set by orchestration
            chat_id, enterprise_id, workflow_name_ctx, context_variables = get_current_execution_context()
            
            try:
                # Inject context variables if function expects them
                if 'context_variables' in param_names and 'context_variables' not in kwargs:
                    kwargs['context_variables'] = context_variables
                    
                # Inject specific values if function expects them
                if 'chat_id' in param_names and 'chat_id' not in kwargs:
                    kwargs['chat_id'] = chat_id
                if 'enterprise_id' in param_names and 'enterprise_id' not in kwargs:
                    kwargs['enterprise_id'] = enterprise_id
                if 'workflow_name' in param_names and 'workflow_name' not in kwargs:
                    kwargs['workflow_name'] = workflow_name_ctx or workflow_name
                if 'workflow' in param_names and 'workflow' not in kwargs:
                    kwargs['workflow'] = workflow_name_ctx or workflow_name
                    
                # CRITICAL: Also inject WebSocket path parameters from AG2 ContextVariables
                # These are automatically available for .py/.js stub generation
                runtime_updates = {}
                
                # First priority: values from execution context (thread-local)
                if chat_id:
                    runtime_updates['chat_id'] = chat_id
                if enterprise_id:
                    runtime_updates['enterprise_id'] = enterprise_id
                if workflow_name_ctx or workflow_name:
                    runtime_updates['workflow_name'] = workflow_name_ctx or workflow_name
                    runtime_updates['workflow'] = workflow_name_ctx or workflow_name
                
                # Second priority: extract from AG2 ContextVariables if available
                if context_variables and hasattr(context_variables, 'get'):
                    try:
                        # Extract WebSocket path parameters from ContextVariables
                        cv_workflow = context_variables.get('workflow_name')
                        cv_enterprise = context_variables.get('enterprise_id')
                        cv_chat = context_variables.get('chat_id')
                        cv_user = context_variables.get('user_id')
                        
                        # Use ContextVariables values if not already set
                        if cv_workflow and 'workflow_name' not in runtime_updates:
                            runtime_updates['workflow_name'] = cv_workflow
                            runtime_updates['workflow'] = cv_workflow
                        if cv_enterprise and 'enterprise_id' not in runtime_updates:
                            runtime_updates['enterprise_id'] = cv_enterprise
                        if cv_chat and 'chat_id' not in runtime_updates:
                            runtime_updates['chat_id'] = cv_chat
                        if cv_user and 'user_id' not in runtime_updates:
                            runtime_updates['user_id'] = cv_user
                            
                    except Exception as cv_extract_err:
                        logger.debug(f"[TOOLS] ContextVariables parameter extraction failed: {cv_extract_err}")
                
                # Always pass the full context_variables object
                if context_variables:
                    runtime_updates['context_variables'] = context_variables
                
                # Update kwargs with all runtime values
                kwargs.update(runtime_updates)
                
                logger.debug(f"[TOOLS] Context injected into {func.__name__}: chat_id={chat_id}, enterprise_id={enterprise_id}")
                    
            except Exception as ctx_err:
                logger.debug(f"[TOOLS] Context injection failed for {func.__name__}: {ctx_err}")
                # Continue without context injection
            
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get context from thread-local storage set by orchestration
            chat_id, enterprise_id, workflow_name_ctx, context_variables = get_current_execution_context()
            
            try:
                if 'context_variables' in param_names and 'context_variables' not in kwargs:
                    kwargs['context_variables'] = context_variables
                    
                if 'chat_id' in param_names and 'chat_id' not in kwargs:
                    kwargs['chat_id'] = chat_id
                if 'enterprise_id' in param_names and 'enterprise_id' not in kwargs:
                    kwargs['enterprise_id'] = enterprise_id
                if 'workflow_name' in param_names and 'workflow_name' not in kwargs:
                    kwargs['workflow_name'] = workflow_name_ctx or workflow_name
                if 'workflow' in param_names and 'workflow' not in kwargs:
                    kwargs['workflow'] = workflow_name_ctx or workflow_name
                    
                # CRITICAL: Also inject WebSocket path parameters from AG2 ContextVariables
                # These are automatically available for .py/.js stub generation
                runtime_updates = {}
                
                # First priority: values from execution context (thread-local)
                if chat_id:
                    runtime_updates['chat_id'] = chat_id
                if enterprise_id:
                    runtime_updates['enterprise_id'] = enterprise_id
                if workflow_name_ctx or workflow_name:
                    runtime_updates['workflow_name'] = workflow_name_ctx or workflow_name
                    runtime_updates['workflow'] = workflow_name_ctx or workflow_name
                
                # Second priority: extract from AG2 ContextVariables if available
                if context_variables and hasattr(context_variables, 'get'):
                    try:
                        # Extract WebSocket path parameters from ContextVariables
                        cv_workflow = context_variables.get('workflow_name')
                        cv_enterprise = context_variables.get('enterprise_id')
                        cv_chat = context_variables.get('chat_id')
                        cv_user = context_variables.get('user_id')
                        
                        # Use ContextVariables values if not already set
                        if cv_workflow and 'workflow_name' not in runtime_updates:
                            runtime_updates['workflow_name'] = cv_workflow
                            runtime_updates['workflow'] = cv_workflow
                        if cv_enterprise and 'enterprise_id' not in runtime_updates:
                            runtime_updates['enterprise_id'] = cv_enterprise
                        if cv_chat and 'chat_id' not in runtime_updates:
                            runtime_updates['chat_id'] = cv_chat
                        if cv_user and 'user_id' not in runtime_updates:
                            runtime_updates['user_id'] = cv_user
                            
                    except Exception as cv_extract_err:
                        logger.debug(f"[TOOLS] ContextVariables parameter extraction failed: {cv_extract_err}")
                
                # Always pass the full context_variables object
                if context_variables:
                    runtime_updates['context_variables'] = context_variables
                
                # Update kwargs with all runtime values
                kwargs.update(runtime_updates)
                
                logger.debug(f"[TOOLS] Context injected into {func.__name__}: chat_id={chat_id}, enterprise_id={enterprise_id}")
                    
            except Exception as ctx_err:
                logger.debug(f"[TOOLS] Context injection failed for {func.__name__}: {ctx_err}")
            
            return func(*args, **kwargs)
        
        # Return the appropriate wrapper based on whether function is async
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    except Exception as wrap_err:
        logger.warning(f"[TOOLS] Failed to wrap function {func.__name__} for context injection: {wrap_err}")
        return func

def load_agent_tool_functions(workflow_name: str) -> Dict[str, List[Callable]]:
    """Discover and import per-agent tool functions for a workflow.

    Reads workflows/<workflow_name>/tools.json and returns a mapping of
    agent_name -> list[callable] so callers can pass functions=... to
    ConversableAgent at construction time.

    Loads ALL tools (both Agent_Tool and UI_Tool types) as agent functions.
    UI_Tools get special handling during execution but still need to be
    registered with their agents for proper function binding.
    """
    mapping: Dict[str, List[Callable]] = {}
    base_dir = Path('workflows') / workflow_name
    tools_json_path = base_dir / 'tools.json'
    if not tools_json_path.exists():
        logger.debug(f"[TOOLS] No tools.json for workflow '{workflow_name}'")
        return mapping
    try:
        data = json.loads(tools_json_path.read_text(encoding='utf-8')) or {}
    except Exception as jerr:
        logger.warning(f"[TOOLS] Failed to parse tools.json for '{workflow_name}': {jerr}")
        return mapping
    entries = data.get('tools', []) or []
    if not isinstance(entries, list):
        logger.warning(f"[TOOLS] tools.json 'tools' section not a list in '{workflow_name}'")
        return mapping
    # Disable per-process tool module caching to always load fresh tool code
    module_cache: Dict[Path, Any] = {}
    logger.debug(f"[TOOLS][TRACE] Starting tool load for workflow '{workflow_name}' (entries={len(entries)})")
    for idx, tool in enumerate(entries, start=1):
        if not isinstance(tool, dict):
            continue
        # NOTE: We load ALL tools (including UI_Tools) as agent functions here.
        # UI_Tools get special handling during execution but still need to be
        # registered with the agent for proper function binding.
        file_name = tool.get('file')
        func_name = tool.get('function')
        agent_field = tool.get('agent')
        if not file_name or not func_name or not agent_field:
            logger.warning(f"[TOOLS][TRACE] Skipping entry #{idx}: missing one of file/function/agent -> file={file_name} func={func_name} agent={agent_field}")
            continue
        # Support agent as str or list
        if isinstance(agent_field, (list, tuple)):
            agent_targets = [a for a in agent_field if isinstance(a, str)]
        else:
            agent_targets = [agent_field] if isinstance(agent_field, str) else []
        if not agent_targets:
            continue
        # Resolve file path (support both root and tools/ subdir)
        base_dir_tools = base_dir / 'tools'
        candidate_paths = [base_dir / file_name, base_dir_tools / file_name]
        file_path: Optional[Path] = next((p for p in candidate_paths if p.exists()), None)
        if not file_path:
            logger.warning(f"[TOOLS][TRACE] File not found for entry #{idx}: {file_name} (searched: {candidate_paths})")
            continue
        # Always load a fresh module instance under an ephemeral name (no sys.modules caching)
        module = None
        try:
            spec = importlib.util.spec_from_file_location(f"mozaiks_{workflow_name}_{file_path.stem}_ephemeral", file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                logger.debug(f"[TOOLS] Loaded module fresh (no cache): {file_path.name}")
            else:
                logger.warning(f"[TOOLS] Could not load spec for {file_path}")
                continue
        except Exception as imp_err:
            logger.warning(f"[TOOLS][TRACE] Import failed for {file_path}: {imp_err}")
            continue
        try:
            func = getattr(module, func_name)
        except AttributeError:
            logger.warning(f"[TOOLS][TRACE] Function '{func_name}' missing in {file_path.name}")
            continue
        if not callable(func):
            logger.warning(f"[TOOLS][TRACE] Attribute '{func_name}' in {file_path.name} not callable")
            continue
        
        # Wrap the function to inject context variables if the function expects them
        func = _wrap_function_with_context_injection(func, workflow_name)
        
        # Log binding details BEFORE adding
        logger.debug(
            "[TOOLS][TRACE] Preparing to bind function -> workflow=%s agent_targets=%s file=%s func=%s module=%s",
            workflow_name, agent_targets, file_path.name, func_name, getattr(func, '__module__', None)
        )
        for ag in agent_targets:
            mapping.setdefault(ag, []).append(func)
            logger.debug(
                "[TOOLS][TRACE] Bound function to agent -> workflow=%s agent=%s func=%s id=%s",
                workflow_name, ag, func_name, hex(id(func))
            )
    # Emit a structured summary for post-mortem debugging
    summary = {agent: [getattr(f, '__name__', '<noname>') for f in funcs] for agent, funcs in mapping.items()}
    total_funcs = sum(len(v) for v in mapping.values())
    logger.info(f"[TOOLS] Bound {total_funcs} tool functions across {len(mapping)} agents for '{workflow_name}'")
    logger.debug(f"[TOOLS][TRACE] Tool binding summary for '{workflow_name}': {summary}")
    return mapping

def clear_tool_cache(workflow_name: Optional[str] = None) -> int:
    """Clear cached tool modules to force fresh reload.
    
    Args:
        workflow_name: If provided, only clear modules for this workflow.
                      If None, clear all mozaiks_* modules.
    
    Returns:
        Number of modules cleared from sys.modules cache.
    """
    cleared_count = 0
    modules_to_clear = []
    
    # Find modules to clear
    for module_name in sys.modules.keys():
        if workflow_name:
            # Clear only specific workflow modules
            if module_name.startswith(f"mozaiks_{workflow_name}_"):
                modules_to_clear.append(module_name)
        else:
            # Clear all mozaiks modules
            if module_name.startswith("mozaiks_"):
                modules_to_clear.append(module_name)
    
    # Clear the modules
    for module_name in modules_to_clear:
        try:
            del sys.modules[module_name]
            cleared_count += 1
            logger.debug(f"[TOOLS] Cleared cached module: {module_name}")
        except KeyError:
            # Module was already removed by another thread
            pass
    
    if cleared_count > 0:
        logger.info(f"[TOOLS] Cleared {cleared_count} cached tool modules")
    else:
        logger.debug("[TOOLS] No cached tool modules found to clear")
    
    return cleared_count

__all__ = [
    'load_agent_tool_functions',
    'clear_tool_cache',
    'set_current_execution_context',
    'get_current_execution_context',
    'clear_current_execution_context',
]
