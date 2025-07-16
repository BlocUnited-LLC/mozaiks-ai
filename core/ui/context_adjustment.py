# ==============================================================================
# FILE: core/ui/context_adjustment.py
# DESCRIPTION: Workflow-agnostic context variable adjustment system for UI components
# ==============================================================================

import logging
import importlib
from typing import Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from autogen.agentchat.group import ContextVariables

from logs.logging_config import get_business_logger, get_component_logger

logger = logging.getLogger(__name__)
business_logger = get_business_logger("context_adjustment")
component_logger = get_component_logger("context_bridge")

class ContextAdjustmentBridge:
    """
    Workflow-agnostic system for adjusting ContextVariables based on component actions.
    
    This bridge system:
    1. Receives component actions from frontend (via transport)
    2. Checks if the agent/component has context_adjustment enabled
    3. Dynamically loads the workflow's context adjustment function
    4. Updates ContextVariables with the action data
    """
    
    def __init__(self):
        self.workflow_context_modules = {}
    
    def _get_workflow_context_module(self, workflow_type: str):
        """Dynamically import the workflow's ContextVariables module"""
        if workflow_type in self.workflow_context_modules:
            return self.workflow_context_modules[workflow_type]
        
        try:
            # Import the workflow's ContextVariables module
            module_path = f"workflows.{workflow_type}.ContextVariables"
            module = importlib.import_module(module_path)
            self.workflow_context_modules[workflow_type] = module
            
            business_logger.info(f"🔗 Loaded context module for workflow: {workflow_type}")
            return module
            
        except ImportError as e:
            business_logger.error(f"❌ Could not import context module for {workflow_type}: {e}")
            return None
    
    def _has_context_update_function(self, workflow_type: str) -> bool:
        """Check if workflow has a context_update function"""
        module = self._get_workflow_context_module(workflow_type)
        return module is not None and hasattr(module, 'context_update')
    
    async def adjust_context_for_action(
        self, 
        workflow_type: str,
        agent_name: str,
        component_name: str,
        action_data: Dict[str, Any],
        context_variables: 'ContextVariables'
    ) -> Dict[str, Any]:
        """
        Adjust ContextVariables based on component action
        
        Args:
            workflow_type: The workflow type (e.g., 'Generator')
            agent_name: Name of the agent that owns the component
            component_name: Name of the component that sent the action
            action_data: The action data from the frontend component
            context_variables: The AG2 ContextVariables to update
            
        Returns:
            Result of the context adjustment
        """
        try:
            # Check if this workflow has context adjustment capability
            from core.workflow.workflow_config import workflow_config
            
            if not workflow_config.has_context_adjustment_enabled(workflow_type, agent_name):
                business_logger.debug(f"Context adjustment not enabled for {agent_name} in {workflow_type}")
                return {"status": "skipped", "reason": "context_adjustment not enabled"}
            
            component_logger.info(f"🎯 Processing context adjustment: {workflow_type}.{agent_name}.{component_name}")
            
            # Try to get workflow-specific context update function
            module = self._get_workflow_context_module(workflow_type)
            
            if module and hasattr(module, 'context_update'):
                # Call workflow-specific context update
                update_result = await module.context_update(
                    agent_name=agent_name,
                    component_name=component_name,
                    action_data=action_data,
                    context_variables=context_variables
                )
                
                business_logger.info(f"✅ Context updated via workflow function: {workflow_type}")
                return update_result
            
            else:
                # Fall back to generic context update
                result = self._generic_context_update(
                    agent_name, component_name, action_data, context_variables
                )
                
                business_logger.info(f"✅ Context updated via generic function: {workflow_type}")
                return result
                
        except Exception as e:
            business_logger.error(f"❌ Context adjustment failed for {workflow_type}.{agent_name}: {e}")
            return {"status": "error", "message": str(e)}
    
    def _generic_context_update(
        self,
        agent_name: str,
        component_name: str,
        action_data: Dict[str, Any],
        context_variables: 'ContextVariables'
    ) -> Dict[str, Any]:
        """
        Generic context update when no workflow-specific function exists
        """
        try:
            # Track component interactions generically
            interactions = context_variables.get('component_interactions', 0)
            if interactions is None:
                interactions = 0
            
            context_variables.set('component_interactions', interactions + 1)
            
            # Store last action info
            context_variables.set('last_component_action', {
                'agent': agent_name,
                'component': component_name,
                'action_type': action_data.get('type', 'unknown'),
                'timestamp': str(__import__('time').time())
            })
            
            # Store action data in a generic way
            action_history = context_variables.get('action_history', [])
            if action_history is None:
                action_history = []
            
            action_history.append({
                'agent': agent_name,
                'component': component_name,
                'data': action_data,
                'timestamp': str(__import__('time').time())
            })
            
            # Keep only last 10 actions
            if len(action_history) > 10:
                action_history = action_history[-10:]
            
            context_variables.set('action_history', action_history)
            
            component_logger.info(f"📝 Generic context update completed for {component_name}")
            
            return {
                "status": "success",
                "method": "generic",
                "interactions_count": interactions + 1,
                "action_stored": True
            }
            
        except Exception as e:
            component_logger.error(f"Generic context update failed: {e}")
            return {"status": "error", "message": str(e)}


# Global bridge instance
context_adjustment_bridge = ContextAdjustmentBridge()


async def adjust_context_from_component_action(
    workflow_type: str,
    agent_name: str,
    component_name: str,
    action_data: Dict[str, Any],
    context_variables: 'ContextVariables'
) -> Dict[str, Any]:
    """
    Convenience function for adjusting context from component actions
    This is the main entry point from the transport layer
    """
    return await context_adjustment_bridge.adjust_context_for_action(
        workflow_type, agent_name, component_name, action_data, context_variables
    )
