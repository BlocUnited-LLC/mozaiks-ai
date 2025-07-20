# ==============================================================================
# FILE: core/workflow/tool_loader.py
# DESCRIPTION: Universal tool loader that reads from workflow.json configurations
# ==============================================================================

import importlib
import logging
from typing import Dict, Any, List, Optional
from core.workflow.workflow_config import workflow_config

# Import enhanced logging
from logs.logging_config import (
    get_business_logger
)

logger = logging.getLogger(__name__)

def load_tools_from_workflow(workflow_type: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load tools directly from workflow.json - universal tool loading for all workflows.
    
    Args:
        workflow_type: Workflow type to load (e.g., 'generator', 'analyzer')
        
    Returns:
        Dictionary with 'agent_tools' and 'lifecycle_hooks' lists
    """
    try:
        # Get business logger for this specific workflow
        business_logger = get_business_logger(f"{workflow_type}_tool_loader")
        
        agent_tools = workflow_config.get_enabled_agent_tools(workflow_type)
        lifecycle_hooks = workflow_config.get_enabled_lifecycle_hooks(workflow_type)
        
        # Dynamically import and attach the actual functions
        for tool in agent_tools:
            try:
                if "module" not in tool:
                    business_logger.error(f"Tool {tool.get('name', 'unknown')} missing 'module' field")
                    continue
                    
                if "function" not in tool:
                    business_logger.error(f"Tool {tool.get('name', 'unknown')} missing 'function' field")
                    continue
                
                module = importlib.import_module(tool["module"])
                if not hasattr(module, tool["function"]):
                    business_logger.error(f"Function '{tool['function']}' not found in module '{tool['module']}'")
                    tool["enabled"] = False
                    continue
                    
                tool["function_obj"] = getattr(module, tool["function"])
                business_logger.debug(f"✅ Successfully loaded tool {tool['name']} from {tool['module']}.{tool['function']}")
            except Exception as e:
                business_logger.error(f"Failed to import agent tool {tool.get('name', 'unknown')}: {e}")
                business_logger.error(f"Tool config: {tool}")
                # Skip tools that fail to import
                continue
        
        for hook in lifecycle_hooks:
            try:
                if "module" not in hook or "function" not in hook:
                    business_logger.error(f"Hook {hook.get('name', 'unknown')} missing module or function field")
                    continue
                    
                module = importlib.import_module(hook["module"])
                if not hasattr(module, hook["function"]):
                    business_logger.error(f"Function '{hook['function']}' not found in module '{hook['module']}'")
                    continue
                    
                hook["function_obj"] = getattr(module, hook["function"])
                business_logger.debug(f"✅ Successfully loaded hook {hook['name']} from {hook['module']}.{hook['function']}")
            except Exception as e:
                business_logger.error(f"Failed to import lifecycle hook {hook.get('name', 'unknown')}: {e}")
                # Skip hooks that fail to import
                continue
        
        business_logger.info(f"✅ Loaded {len(agent_tools)} agent tools and {len(lifecycle_hooks)} lifecycle hooks from workflow.json")
        
        return {
            "agent_tools": [t for t in agent_tools if "function_obj" in t],
            "lifecycle_hooks": [h for h in lifecycle_hooks if "function_obj" in h]
        }
        
    except Exception as e:
        logger.error(f"Failed to load tools from workflow.json for {workflow_type}: {e}")
        return {"agent_tools": [], "lifecycle_hooks": []}


def register_agent_tools(agents: Dict[str, Any], agent_tools: List[Dict[str, Any]], workflow_type: str = "unknown"):
    """Register agent tools with specific agents based on apply_to configuration"""
    business_logger = get_business_logger(f"{workflow_type}_tool_loader")
    
    business_logger.info(f"🔧 Starting tool registration for {len(agent_tools)} tools")
    business_logger.info(f"🔍 Available agents: {list(agents.keys())}")
    
    for tool in agent_tools:
        if "function_obj" not in tool:
            business_logger.warning(f"⚠️ Skipping tool {tool.get('name', 'unknown')}: missing function_obj")
            continue
            
        apply_to = tool.get("apply_to", [])
        tool_name = tool.get("name")
        tool_func = tool["function_obj"]
        
        business_logger.info(f"🎯 Processing tool '{tool_name}' with apply_to: {apply_to}")
        
        # Get list of target agents
        target_agents = []
        if apply_to == "all":
            target_agents = list(agents.values())
            business_logger.info(f"   📝 Applying to ALL agents: {[a.name for a in target_agents]}")
        elif isinstance(apply_to, list):
            target_agents = [agents[name] for name in apply_to if name in agents]
            missing_agents = [name for name in apply_to if name not in agents]
            business_logger.info(f"   📝 Applying to specific agents: {[a.name for a in target_agents]}")
            if missing_agents:
                business_logger.warning(f"   ⚠️ Missing agents for tool '{tool_name}': {missing_agents}")
        elif isinstance(apply_to, str) and apply_to in agents:
            target_agents = [agents[apply_to]]
            business_logger.info(f"   📝 Applying to single agent: {apply_to}")
        else:
            business_logger.error(f"   ❌ Invalid apply_to configuration for tool '{tool_name}': {apply_to}")
        
        # Register with AG2's proper methods (execution only to avoid function calling)
        for agent in target_agents:
            try:
                # Register for execution only - avoid register_for_llm to prevent IndexError
                agent.register_for_execution(name=tool_name)(tool_func)
                business_logger.info(f"✅ Registered AG2 tool (execution-only): {tool_name} -> {agent.name}")
            except Exception as e:
                business_logger.error(f"❌ Failed to register tool {tool_name} with agent {agent.name}: {e}")
                
    business_logger.info(f"🔧 Tool registration complete for workflow: {workflow_type}")




def register_lifecycle_hooks(agents: Dict[str, Any], lifecycle_hooks: List[Dict[str, Any]], workflow_type: str = "unknown"):
    """Register lifecycle hooks with agents using AG2's register_hook method"""
    business_logger = get_business_logger(f"{workflow_type}_tool_loader")
    
    for hook in lifecycle_hooks:
        if "function_obj" not in hook:
            continue
            
        trigger = hook.get("trigger")
        hook_name = hook.get("name")
        hook_func = hook["function_obj"]
        apply_to = hook.get("apply_to", [])
        
        # Skip if trigger is None
        if trigger is None:
            business_logger.error(f"Hook {hook_name} has no trigger defined")
            continue
        
        # Map workflow.json trigger names to AG2 hook names
        ag2_hook_mapping = {
            "process_last_received_message": "process_last_received_message",
            "process_all_messages_before_reply": "process_all_messages_before_reply", 
            "process_message_before_send": "process_message_before_send",
            "update_agent_state": "update_agent_state"
        }
        
        ag2_hook_name = ag2_hook_mapping.get(trigger, trigger)
        
        # Get list of target agents
        target_agents = []
        if apply_to == "all":
            target_agents = list(agents.values())
        elif isinstance(apply_to, list):
            target_agents = [agents[name] for name in apply_to if name in agents]
        elif isinstance(apply_to, str) and apply_to in agents:
            target_agents = [agents[apply_to]]
        
        # Register hooks with AG2's proper methods
        for agent in target_agents:
            try:
                # Check if hook is already registered to avoid duplicate registration
                if hasattr(agent, 'hook_lists') and ag2_hook_name in agent.hook_lists:
                    if hook_func in agent.hook_lists[ag2_hook_name]:
                        business_logger.debug(f"🔄 Hook {hook_name} already registered with agent {agent.name}, skipping")
                        continue
                
                agent.register_hook(ag2_hook_name, hook_func)
                business_logger.info(f"🪝 Registered AG2 hook: {hook_name} ({ag2_hook_name}) -> {agent.name}")
            except Exception as e:
                business_logger.error(f"Failed to register hook {hook_name} with agent {agent.name}: {e}")


def add_debug_logging_to_agents(agents: Dict[str, Any], workflow_type: str = "unknown"):
    """Add debug logging to track reply function execution and message states"""
    business_logger = get_business_logger(f"{workflow_type}_tool_loader")
    
    for agent_name, agent in agents.items():
        try:
            # Patch the generate_reply method to add logging
            original_generate_reply = agent.generate_reply
            original_a_generate_reply = agent.a_generate_reply
            
            def debug_generate_reply(messages=None, sender=None, **kwargs):
                business_logger.info(f"🔍 Agent {agent_name} generate_reply called:")
                if messages is None:
                    business_logger.warning(f"  ⚠️ messages is None, returning None to prevent errors")
                    return None
                business_logger.info(f"  • messages: {len(messages)} messages")
                business_logger.info(f"  • sender: {sender.name if sender else 'None'}")
                business_logger.info(f"  • kwargs: {list(kwargs.keys())}")
                
                if len(messages) > 0:
                    business_logger.info(f"  • last message: {messages[-1]}")
                
                try:
                    result = original_generate_reply(messages=messages, sender=sender, **kwargs)
                    business_logger.info(f"  ✅ generate_reply succeeded")
                    return result
                except Exception as e:
                    business_logger.error(f"  ❌ generate_reply failed: {e}")
                    business_logger.error(f"  📊 Message details: {messages}")
                    raise
            
            async def debug_a_generate_reply(messages=None, sender=None, **kwargs):
                business_logger.info(f"🔍 Agent {agent_name} a_generate_reply called:")
                if messages is None:
                    business_logger.warning(f"  ⚠️ messages is None, returning None to prevent errors")
                    return None
                business_logger.info(f"  • messages: {len(messages)} messages")
                business_logger.info(f"  • sender: {sender.name if sender else 'None'}")
                business_logger.info(f"  • kwargs: {list(kwargs.keys())}")
                if len(messages) > 0:
                    business_logger.info(f"  • last message: {messages[-1]}")
                
                try:
                    result = await original_a_generate_reply(messages=messages, sender=sender, **kwargs)
                    business_logger.info(f"  ✅ a_generate_reply succeeded")
                    return result
                except Exception as e:
                    business_logger.error(f"  ❌ a_generate_reply failed: {e}")
                    business_logger.error(f"  📊 Message details: {messages}")
                    raise
            
            # Replace the methods with debug versions
            agent.generate_reply = debug_generate_reply
            agent.a_generate_reply = debug_a_generate_reply
            
            business_logger.info(f"🔍 Added debug logging to agent {agent_name}")
            
        except Exception as e:
            business_logger.error(f"Failed to add debug logging to agent {agent_name}: {e}")


def add_comprehensive_agent_logging(agents: Dict[str, Any], workflow_type: str = "unknown"):
    """Add comprehensive logging to track all agent interactions and message flows"""
    business_logger = get_business_logger(f"{workflow_type}_tool_loader")
    
    for agent_name, agent in agents.items():
        try:
            # Track send/receive operations
            original_send = agent.send
            original_a_send = agent.a_send
            original_receive = agent.receive
            original_a_receive = agent.a_receive
            
            def debug_send(message, recipient, request_reply=None, silent=None):
                business_logger.info(f"📤 Agent {agent_name} sending message to {recipient.name}:")
                business_logger.info(f"  • message: {str(message)[:200]}...")
                business_logger.info(f"  • request_reply: {request_reply}")
                try:
                    return original_send(message, recipient, request_reply, silent)
                except Exception as e:
                    business_logger.error(f"  ❌ Send failed: {e}")
                    raise
            
            async def debug_a_send(message, recipient, request_reply=None, silent=None):
                business_logger.info(f"📤 Agent {agent_name} async sending message to {recipient.name}:")
                business_logger.info(f"  • message: {str(message)[:200]}...")
                business_logger.info(f"  • request_reply: {request_reply}")
                try:
                    return await original_a_send(message, recipient, request_reply, silent)
                except Exception as e:
                    business_logger.error(f"  ❌ Async send failed: {e}")
                    raise
            
            def debug_receive(message, sender, request_reply=None, silent=None):
                business_logger.info(f"📥 Agent {agent_name} receiving message from {sender.name}:")
                business_logger.info(f"  • message: {str(message)[:200]}...")
                business_logger.info(f"  • request_reply: {request_reply}")
                business_logger.info(f"  • current chat history length: {len(agent.chat_messages.get(sender, []))}")
                try:
                    return original_receive(message, sender, request_reply, silent)
                except Exception as e:
                    business_logger.error(f"  ❌ Receive failed: {e}")
                    raise
            
            async def debug_a_receive(message, sender, request_reply=None, silent=None):
                business_logger.info(f"📥 Agent {agent_name} async receiving message from {sender.name}:")
                business_logger.info(f"  • message: {str(message)[:200]}...")
                business_logger.info(f"  • request_reply: {request_reply}")
                business_logger.info(f"  • current chat history length: {len(agent.chat_messages.get(sender, []))}")
                try:
                    return await original_a_receive(message, sender, request_reply, silent)
                except Exception as e:
                    business_logger.error(f"  ❌ Async receive failed: {e}")
                    raise
            
            # Replace methods with debug versions
            agent.send = debug_send
            agent.a_send = debug_a_send
            agent.receive = debug_receive
            agent.a_receive = debug_a_receive
            
            business_logger.info(f"📋 Added comprehensive logging to agent {agent_name}")
            
        except Exception as e:
            business_logger.error(f"Failed to add comprehensive logging to agent {agent_name}: {e}")


def create_safe_reply_wrapper(original_func, agent_name: str):
    """Create a safe wrapper that handles empty messages and other edge cases"""
    import asyncio
    from logs.logging_config import get_business_logger
    
    safe_logger = get_business_logger("safe_reply_wrapper")
    
    if asyncio.iscoroutinefunction(original_func):
        async def safe_async_wrapper(messages=None, sender=None, config=None, **kwargs):
            try:
                # Handle empty or None messages
                if not messages:
                    safe_logger.warning(f"🚨 [SAFE_REPLY] Agent {agent_name} called with empty messages - returning False, None")
                    return False, None
                
                # Handle case where messages is not a list
                if not isinstance(messages, list):
                    safe_logger.warning(f"🚨 [SAFE_REPLY] Agent {agent_name} called with non-list messages: {type(messages)} - returning False, None")
                    return False, None
                
                # Log the call for debugging
                safe_logger.debug(f"🔧 [SAFE_REPLY] Agent {agent_name} processing {len(messages)} messages")
                
                # Call the original function
                return await original_func(messages=messages, sender=sender, config=config, **kwargs)
                
            except Exception as e:
                safe_logger.error(f"🚨 [SAFE_REPLY] Agent {agent_name} reply function failed: {e}")
                # Return a safe fallback response
                return False, None
        
        return safe_async_wrapper
    else:
        def safe_sync_wrapper(messages=None, sender=None, config=None, **kwargs):
            try:
                # Handle empty or None messages
                if not messages:
                    safe_logger.warning(f"🚨 [SAFE_REPLY] Agent {agent_name} called with empty messages - returning False, None")
                    return False, None
                
                # Handle case where messages is not a list
                if not isinstance(messages, list):
                    safe_logger.warning(f"🚨 [SAFE_REPLY] Agent {agent_name} called with non-list messages: {type(messages)} - returning False, None")
                    return False, None
                
                # Log the call for debugging
                safe_logger.debug(f"🔧 [SAFE_REPLY] Agent {agent_name} processing {len(messages)} messages")
                
                # Call the original function
                return original_func(messages=messages, sender=sender, config=config, **kwargs)
                
            except Exception as e:
                safe_logger.error(f"🚨 [SAFE_REPLY] Agent {agent_name} reply function failed: {e}")
                # Return a safe fallback response
                return False, None
        
        return safe_sync_wrapper
