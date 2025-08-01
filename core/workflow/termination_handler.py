"""
AG2 Termination Handler with VE-Style Status Management
Automatically updates workflow status from 0 → 1 when AG2 conversations terminate
Based on TerminateTarget patterns from AD_DevDeploy.py VE-style logic (0 = resumable, 1 = completed)
"""
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Union
from dataclasses import dataclass

from logs.logging_config import get_business_logger, log_business_event
from core.data.persistence_manager import PersistenceManager
from core.data.token_manager import TokenManager

logger = get_business_logger("termination_handler")

@dataclass
class TerminationResult:
    """Result of conversation termination processing"""
    terminated: bool
    termination_reason: str
    final_status: int
    workflow_complete: bool
    session_summary: Optional[Dict[str, Any]] = None

class AG2TerminationHandler:
    """
    Handles AG2 conversation termination and integrates with VE-style workflow status management.
    
    When AG2 conversations end (via TerminateTarget or max_turns), this handler:
    1. Detects the termination event
    2. Updates VE-style status from 0 (in progress) to 1 (complete)
    3. Finalizes conversation in persistence manager
    4. Triggers workflow completion analytics
    5. Cleans up session state appropriately
    
    VE-Style Status Pattern:
    - Status 0: Chat initiated/in progress (resumable)
    - Status 1: Chat ended/completed (not resumable)
    
    Integration Points:
    - AG2 GroupChat termination callbacks
    - VE-style PersistenceManager status updates
    - TokenManager session finalization
    - Workflow completion notifications
    """
    
    def __init__(self, 
                 chat_id: str, 
                 enterprise_id: str, 
                 workflow_name: str = "default",
                 persistence_manager: Optional[PersistenceManager] = None,
                 token_manager: Optional[TokenManager] = None):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.workflow_name = workflow_name
        self.persistence_manager = persistence_manager or PersistenceManager()
        self.token_manager = token_manager
        
        # Termination detection state
        self.conversation_active = False
        self.termination_callbacks = []
        self.start_time = None
        
        logger.info(f"🔄 Termination handler initialized for {workflow_name} workflow")
    
    def add_termination_callback(self, callback: Callable[[TerminationResult], None]):
        """Add callback to be triggered when conversation terminates"""
        self.termination_callbacks.append(callback)
        logger.debug(f"📋 Added termination callback: {callback.__name__}")
    
    async def on_conversation_start(self):
        """Called when AG2 conversation begins"""
        self.conversation_active = True
        self.start_time = time.time()
        
        # Update VE-style status to indicate conversation is active
        await self.persistence_manager.update_workflow_status(
            self.chat_id, self.enterprise_id, 0, self.workflow_name
        )
        
        log_business_event(
            event_type="CONVERSATION_STARTED",
            description=f"AG2 conversation started for {self.workflow_name}",
            context={
                "chat_id": self.chat_id,
                "enterprise_id": self.enterprise_id,
                "workflow_name": self.workflow_name
            }
        )
        
        logger.info(f"🚀 AG2 conversation started for {self.workflow_name}")
    
    async def on_conversation_end(self, 
                                termination_reason: str = "completed",
                                final_status: int = 1,
                                max_turns_reached: bool = False) -> TerminationResult:
        """
        Called when AG2 conversation ends (TerminateTarget triggered or max_turns reached)
        
        Args:
            termination_reason: Why the conversation ended
            final_status: VE-style final status (1 for completion)
            max_turns_reached: Whether conversation ended due to max turns limit
        
        Returns:
            TerminationResult with completion details
        """
        if not self.conversation_active:
            logger.warning(f"⚠️ Termination handler called but conversation not active")
            return TerminationResult(
                terminated=False,
                termination_reason="not_active",
                final_status=0,
                workflow_complete=False
            )
        
        self.conversation_active = False
        conversation_duration = time.time() - self.start_time if self.start_time else 0
        
        try:
            # VE-style status pattern: 0 = in progress, 1 = completed (any reason)
            final_status = 1  # All completed conversations get status 1
            
            # Adjust termination reason if max turns was reached
            if max_turns_reached and termination_reason == "completed":
                termination_reason = "max_turns_reached"
            
            # Update VE-style workflow status (0 → 1)
            status_updated = await self.persistence_manager.update_workflow_status(
                self.chat_id, self.enterprise_id, final_status, self.workflow_name
            )
            
            if not status_updated:
                logger.error(f"❌ Failed to update workflow status to {final_status}")
            
            # Finalize conversation in persistence manager (VE-style)
            conversation_finalized = await self.persistence_manager.finalize_conversation(
                self.chat_id, self.enterprise_id, final_status, self.workflow_name
            )
            
            if not conversation_finalized:
                logger.error(f"❌ Failed to finalize conversation")
            
            # Finalize TokenManager session if available
            session_summary = None
            if self.token_manager:
                try:
                    session_summary = await self.token_manager.finalize_session()
                    logger.info(f"📊 TokenManager session finalized")
                except Exception as e:
                    logger.error(f"❌ Failed to finalize TokenManager session: {e}")
            
            # Create termination result
            result = TerminationResult(
                terminated=True,
                termination_reason=termination_reason,
                final_status=final_status,
                workflow_complete=(final_status == 1),  # VE pattern: 1 = complete
                session_summary=session_summary
            )
            
            # Log business event
            log_business_event(
                event_type="CONVERSATION_TERMINATED",
                description=f"AG2 conversation terminated: {termination_reason}",
                context={
                    "chat_id": self.chat_id,
                    "enterprise_id": self.enterprise_id,
                    "workflow_name": self.workflow_name,
                    "final_status": final_status,
                    "duration_ms": conversation_duration * 1000,
                    "termination_reason": termination_reason,
                    "max_turns_reached": max_turns_reached,
                    "workflow_complete": result.workflow_complete
                }
            )
            
            # Trigger termination callbacks
            for callback in self.termination_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"❌ Termination callback failed: {e}")
            
            logger.info(f"✅ AG2 conversation terminated successfully: {termination_reason} (status: {final_status})")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to handle conversation termination: {e}")
            
            # Return failure result
            return TerminationResult(
                terminated=False,
                termination_reason="termination_error",
                final_status=1,  # Even errors get status 1 (completed, but with error reason)
                workflow_complete=False
            )
    
    async def detect_terminate_target(self, conversation_messages) -> bool:
        """
        Detect if TerminateTarget was triggered based on conversation content
        
        This analyzes the last few messages to detect termination patterns that
        would trigger AG2's TerminateTarget in the handoffs configuration.
        """
        if not conversation_messages:
            return False
        
        # Get the last few messages to analyze
        recent_messages = conversation_messages[-3:] if len(conversation_messages) >= 3 else conversation_messages
        
        termination_indicators = [
            "looks good", "approve", "finished", "done", "thank you",
            "approved", "satisfied", "complete", "end conversation",
            "terminate", "workflow approved", "all set"
        ]
        
        for message in recent_messages:
            content = message.get("content", "").lower()
            for indicator in termination_indicators:
                if indicator in content:
                    logger.info(f"🎯 TerminateTarget pattern detected: '{indicator}' in message")
                    return True
        
        return False
    
    async def check_completion_status(self) -> Dict[str, Any]:
        """Check current completion status of workflow"""
        try:
            # Get current workflow status
            status = await self.persistence_manager.get_workflow_status(
                self.chat_id, self.enterprise_id, self.workflow_name
            )
            
            # Check if can still resume (VE pattern)
            can_resume = await self.persistence_manager.can_resume_chat(
                self.chat_id, self.enterprise_id, self.workflow_name
            )
            
            return {
                "current_status": status,
                "can_resume": can_resume,
                "is_complete": status == 1,  # VE pattern: 1 = complete
                "conversation_active": self.conversation_active,
                "workflow_name": self.workflow_name
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to check completion status: {e}")
            return {
                "current_status": 0,
                "can_resume": False,
                "is_complete": False,
                "conversation_active": self.conversation_active,
                "error": str(e)
            }

def create_termination_handler(chat_id: str, 
                             enterprise_id: str, 
                             workflow_name: str = "default",
                             token_manager: Optional[TokenManager] = None) -> AG2TerminationHandler:
    """
    Factory function to create configured termination handler
    
    Usage in orchestration_patterns.py:
    ```python
    termination_handler = create_termination_handler(chat_id, enterprise_id, workflow_name, token_manager)
    await termination_handler.on_conversation_start()
    
    # ... AG2 conversation happens here ...
    
    # When conversation ends (detect via TerminateTarget or max_turns):
    result = await termination_handler.on_conversation_end("user_approved")
    ```
    """
    return AG2TerminationHandler(
        chat_id=chat_id,
        enterprise_id=enterprise_id,
        workflow_name=workflow_name,
        token_manager=token_manager
    )
