# ==============================================================================
# FILE: core/capabilities/budget_capability.py
# DESCRIPTION: Modular budget and free trial management capability
#              Can be easily enabled/disabled for open source vs commercial versions
# ==============================================================================

from typing import Dict, List, Optional, Any
import logging
from abc import ABC, abstractmethod

from logs.logging_config import get_chat_logger

logger = logging.getLogger(__name__)
chat_logger = get_chat_logger("budget_capability")


class BudgetCapability(ABC):
    """Abstract base class for budget management capabilities."""
    
    def __init__(self, chat_id: str, enterprise_id: str, workflow_type: str, user_id: Optional[str] = None):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.workflow_type = workflow_type
        self.user_id = user_id
        self.enabled = True
    
    @abstractmethod
    async def initialize_budget(self) -> Dict[str, Any]:
        """Initialize budget for a new chat session."""
        pass
    
    @abstractmethod
    async def check_budget_limits(self) -> Dict[str, Any]:
        """Check if budget limits allow continuation."""
        pass
    
    @abstractmethod
    async def update_usage(self, agents: List[Any]) -> Dict[str, Any]:
        """Update usage tracking."""
        pass
    
    @abstractmethod
    async def complete_user_feedback_loop(self) -> bool:
        """Handle completion of user feedback loop."""
        pass
    
    @abstractmethod
    def get_turn_limit(self) -> Optional[int]:
        """Get maximum turns allowed for this session."""
        pass
    
    def is_enabled(self) -> bool:
        """Check if this capability is enabled."""
        return self.enabled
    
    def disable(self):
        """Disable this capability (for open source mode)."""
        self.enabled = False
        chat_logger.info(f"🔓 [BUDGET] Budget capability disabled")


class CommercialBudgetCapability(BudgetCapability):
    """Commercial budget capability with full token management and free trials."""
    
    def __init__(self, chat_id: str, enterprise_id: str, workflow_type: str, user_id: Optional[str] = None):
        super().__init__(chat_id, enterprise_id, workflow_type, user_id)
        self.token_manager = None
        self.budget_info = {}
        
    async def initialize_budget(self) -> Dict[str, Any]:
        """Initialize commercial budget with TokenManager."""
        try:
            # Import TokenManager only when commercial capability is used
            from ..data.token_manager import TokenManager
            
            self.token_manager = TokenManager(self.chat_id, self.enterprise_id, self.workflow_type, self.user_id)
            self.budget_info = await self.token_manager.initialize_budget(self.user_id)
            
            chat_logger.info(f"💰 [COMMERCIAL] Budget initialized: {self.budget_info.get('budget_type', 'unknown')}")
            
            return self.budget_info
            
        except Exception as e:
            logger.error(f"Failed to initialize commercial budget: {e}")
            self.budget_info = {'budget_type': 'error', 'is_free_trial': False}
            return self.budget_info
    
    async def check_budget_limits(self) -> Dict[str, Any]:
        """Check commercial budget limits."""
        if not self.token_manager:
            return {"can_continue": True, "reason": "no_budget_manager"}
        
        try:
            # Check free trial exhaustion
            if (self.token_manager.is_free_trial and 
                hasattr(self.token_manager, 'free_loops_remaining') and
                (self.token_manager.free_loops_remaining is None or self.token_manager.free_loops_remaining <= 0)):
                
                return {
                    "can_continue": False, 
                    "reason": "free_trial_exhausted",
                    "message": f"Free trial loops exhausted for chat {self.chat_id}"
                }
            
            # Check token balance for paid users
            if (not self.token_manager.is_free_trial and 
                hasattr(self.token_manager, 'token_balance') and
                self.token_manager.token_balance <= 0):
                
                return {
                    "can_continue": False,
                    "reason": "insufficient_tokens", 
                    "message": "Insufficient token balance"
                }
            
            return {"can_continue": True, "reason": "budget_ok"}
            
        except Exception as e:
            logger.error(f"Error checking budget limits: {e}")
            return {"can_continue": True, "reason": "check_failed"}
    
    async def update_usage(self, agents: List[Any]) -> Dict[str, Any]:
        """Update usage via TokenManager."""
        if not self.token_manager:
            return {"status": "no_manager"}
        
        try:
            return await self.token_manager.update_usage(agents)
        except Exception as e:
            logger.error(f"Error updating usage: {e}")
            return {"status": "error", "error": str(e)}
    
    async def complete_user_feedback_loop(self) -> bool:
        """Complete user feedback loop via TokenManager."""
        if not self.token_manager:
            return True
        
        try:
            return await self.token_manager.complete_user_feedback_loop()
        except Exception as e:
            logger.error(f"Error completing feedback loop: {e}")
            return False
    
    def get_turn_limit(self) -> Optional[int]:
        """Get turn limit from TokenManager."""
        if self.token_manager and hasattr(self.token_manager, 'turn_limit'):
            return self.token_manager.turn_limit
        return None


class OpenSourceBudgetCapability(BudgetCapability):
    """Open source budget capability - minimal implementation without commercial features."""
    
    async def initialize_budget(self) -> Dict[str, Any]:
        """Initialize open source budget (no limits)."""
        self.budget_info = {
            'budget_type': 'unlimited',
            'is_free_trial': False,
            'message': 'Open source mode - no budget limits'
        }
        
        chat_logger.info(f"🔓 [OPENSOURCE] Open source budget initialized - unlimited usage")
        return self.budget_info
    
    async def check_budget_limits(self) -> Dict[str, Any]:
        """Open source - no limits."""
        return {"can_continue": True, "reason": "opensource_unlimited"}
    
    async def update_usage(self, agents: List[Any]) -> Dict[str, Any]:
        """Open source - track usage but don't enforce limits."""
        # Could still track basic usage stats without enforcement
        return {"status": "tracked_only", "enforcement": "disabled"}
    
    async def complete_user_feedback_loop(self) -> bool:
        """Open source - always allow continuation."""
        return True
    
    def get_turn_limit(self) -> Optional[int]:
        """Open source - no turn limits."""
        return None


class TestingBudgetCapability(BudgetCapability):
    """Testing budget capability - for development/testing without real API calls."""
    
    async def initialize_budget(self) -> Dict[str, Any]:
        """Initialize testing budget."""
        self.budget_info = {
            'budget_type': 'testing',
            'is_free_trial': False,
            'message': 'Testing mode - no real budget enforcement'
        }
        
        chat_logger.info(f"🧪 [TESTING] Testing budget initialized")
        return self.budget_info
    
    async def check_budget_limits(self) -> Dict[str, Any]:
        """Testing - no limits but log checks."""
        chat_logger.debug("🧪 [TESTING] Budget check - allowing continuation")
        return {"can_continue": True, "reason": "testing_mode"}
    
    async def update_usage(self, agents: List[Any]) -> Dict[str, Any]:
        """Testing - log usage without real tracking."""
        # agents parameter not used in testing mode
        chat_logger.debug("🧪 [TESTING] Usage update - no real tracking")
        return {"status": "testing_logged"}
    
    async def complete_user_feedback_loop(self) -> bool:
        """Testing - always allow continuation."""
        return True
    
    def get_turn_limit(self) -> Optional[int]:
        """Testing - no turn limits."""
        return None


class BudgetCapabilityFactory:
    """Factory for creating budget capabilities based on configuration."""
    
    @staticmethod
    def create_capability(
        mode: str,
        chat_id: str, 
        enterprise_id: str, 
        workflow_type: str, 
        user_id: Optional[str] = None
    ) -> BudgetCapability:
        """Create budget capability based on mode.
        
        Args:
            mode: "commercial", "opensource", or "testing"
        """
        if mode == "commercial":
            return CommercialBudgetCapability(chat_id, enterprise_id, workflow_type, user_id)
        elif mode == "opensource":
            return OpenSourceBudgetCapability(chat_id, enterprise_id, workflow_type, user_id)
        elif mode == "testing":
            return TestingBudgetCapability(chat_id, enterprise_id, workflow_type, user_id)
        else:
            logger.warning(f"Unknown budget mode '{mode}', defaulting to testing")
            return TestingBudgetCapability(chat_id, enterprise_id, workflow_type, user_id)


# Configuration - easily changeable for different deployment modes
from .config import get_budget_mode

def get_budget_capability(
    chat_id: str, 
    enterprise_id: str, 
    workflow_type: str, 
    user_id: Optional[str] = None
) -> BudgetCapability:
    """Get the appropriate budget capability for current configuration."""
    current_mode = get_budget_mode()
    return BudgetCapabilityFactory.create_capability(
        current_mode, chat_id, enterprise_id, workflow_type, user_id
    )
