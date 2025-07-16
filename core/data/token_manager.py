# ==============================================================================
# FILE: core\data\token_manager.py
# DESCRIPTION: Manages user budgets, token balances, and business logic for 
#              chat workflows. Integrates with AG2ObservabilityManager for
#              technical token tracking and uses AG2's native usage APIs.
# ==============================================================================

# ==============================================================================
# TESTING PLACEHOLDERS - Remove when integrating real API
# ==============================================================================
USE_MOCK_API = True  # Set to False when ready to use real Tokens API

# Mock user data for testing - replace with real API calls
MOCK_TOKEN_BALANCES = {
    "user123": 100000,     # Increased for testing - was 1000, reduced to 454 through usage
    "user456": 50000, 
    "user789": 5000,       # Low balance for testing warnings  
    "user0001": 150000,    # High balance user
    "test_user": 200000,   # Test user for groupchat testing
}

MOCK_APP_IDS = {
    "default": "app_12345",
    "enterprise_test": "app_67890"
}

def _mock_consume_tokens(user_id: str, app_id: str, amount: int) -> dict:
    """Mock function for POST /api/Tokens/{userId}/consume"""
    if user_id in MOCK_TOKEN_BALANCES:
        if MOCK_TOKEN_BALANCES[user_id] >= amount:
            MOCK_TOKEN_BALANCES[user_id] -= amount
            return {
                "success": True,
                "consumed": amount,
                "remaining": MOCK_TOKEN_BALANCES[user_id],
                "user_id": user_id,
                "app_id": app_id
            }
        else:
            return {
                "success": False,
                "error": "Insufficient tokens",
                "requested": amount,
                "available": MOCK_TOKEN_BALANCES[user_id],
                "user_id": user_id,
                "app_id": app_id
            }
    return {
        "success": False,
        "error": "User not found",
        "user_id": user_id,
        "app_id": app_id
    }

def _mock_get_remaining(user_id: str, app_id: str) -> dict:
    """Mock function for GET /api/Tokens/{userId}/remaining"""
    if user_id in MOCK_TOKEN_BALANCES:
        return {
            "remaining": MOCK_TOKEN_BALANCES[user_id],
            "user_id": user_id,
            "app_id": app_id
        }
    return {
        "remaining": 0,
        "user_id": user_id,
        "app_id": app_id
    }

# ==============================================================================
# END TESTING PLACEHOLDERS
# ==============================================================================

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from autogen import Agent, gather_usage_summary

from core.data.persistence_manager import persistence_manager as mongodb_manager
from core.monitoring.observability import AG2ObservabilityManager
from core.capabilities.config import get_free_trial_config
from logs.logging_config import get_business_logger, get_performance_logger, get_token_manager_logger, log_business_event, log_performance_metric

# Logger setup
business_logger = get_business_logger("token_manager")
performance_logger = get_performance_logger("token_manager")
token_logger = get_token_manager_logger("budget_manager")
logger = logging.getLogger(__name__)

class TokenManager:
    """
    A centralized manager for user budgets, token balances, and business logic
    for all agent-based workflows. Handles free trials, paid accounts, and
    budget enforcement. Integrates with AG2ObservabilityManager for technical
    token tracking and usage monitoring.
    """

    def __init__(self, chat_id: str, enterprise_id: str, workflow_type: str, user_id: Optional[str] = None):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.workflow_type = workflow_type
        self.user_id = user_id  # Store user_id for API calls
        self.session_id = str(uuid.uuid4())

        # Initialize AG2 observability manager for technical token tracking
        self.observability = AG2ObservabilityManager(chat_id, enterprise_id)

        # Business logic state tracking (separate from technical tracking)
        self.business_usage: Dict[str, Any] = {
            "total_tokens_billed": 0,
            "total_cost_billed": 0.0,
            "api_calls_made": 0,
            "api_tokens_consumed": 0,
        }
        self.session_history: List[Dict[str, Any]] = []
        self.termination_triggered = False
        self.termination_reason: Optional[str] = None

        # Budget limits and trial state
        self.token_balance: int = 0
        self.free_loops_remaining: Optional[int] = None
        self.is_free_trial: bool = False
        self.cost_limit: float = 5.0  # Default cost limit
        self.turn_limit: Optional[int] = 20  # Default turn limit (None = unlimited)
        
        # Loop and user interaction tracking
        self.current_loop: int = 0  # Track which loop we're in (completed user feedback cycles)
        self.user_interactions: int = 0  # Track user proxy interactions
        self.max_user_interactions: Optional[int] = None  # Free trial user interaction limit
        self.turn_count: int = 0  # Track individual agent turns/messages

        log_business_event(
            event_type="token_manager_init",
            description=f"TokenManager initialized for chat {chat_id}",
            context={"chat_id": self.chat_id, "workflow": self.workflow_type, "session_id": self.session_id},
        )

    def _get_app_id(self) -> str:
        """Get the app ID for API calls"""
        if USE_MOCK_API:
            return MOCK_APP_IDS.get("default", "app_12345")
        else:
            # Convert enterprise_id to string for API call
            return str(mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id"))

    async def _fetch_token_balance(self, user_id: str) -> int:
        """Fetch token balance from external Tokens API or mock"""
        try:
            app_id = self._get_app_id()
            
            if USE_MOCK_API:
                # Use mock for testing
                result = _mock_get_remaining(user_id, app_id)
                balance = result.get("remaining", 0)
                logger.info(f"Mock token balance fetched: {balance} for user {user_id}")
                return balance
            else:
                # Real API call
                import httpx
                from core.core_config import TOKENS_API_URL
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{TOKENS_API_URL}/api/Tokens/{user_id}/remaining",
                        params={"appid": app_id}
                    )
                
                if resp.status_code == 200:
                    balance = resp.json().get("remaining", 0)
                    logger.info(f"Token balance fetched from API: {balance}")
                    return balance
                else:
                    logger.warning(f"Tokens API error {resp.status_code}")
                    return 0
                
        except Exception as e:
            logger.warning(f"Failed to fetch token balance from API: {e}")
            return 0

    async def _consume_tokens_api(self, user_id: str, amount: int) -> Dict[str, Any]:
        """Consume tokens via external Tokens API or mock"""
        app_id = self._get_app_id()  # Move outside try block to ensure it's always defined
        
        try:
            if USE_MOCK_API:
                # ToDo: Use mock for testing
                result = _mock_consume_tokens(user_id, app_id, amount)
                logger.info(f"Mock tokens consumed: {result}")
                return result
            else:
                # Real API call
                import httpx
                from core.core_config import TOKENS_API_URL
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{TOKENS_API_URL}/api/Tokens/{user_id}/consume",
                        params={"appid": app_id, "amount": amount}
                    )
                
                if resp.status_code == 200:
                    result = resp.json()
                    logger.info(f"Tokens consumed via API: {result}")
                    return result
                else:
                    logger.error(f"Token consume API error {resp.status_code}: {resp.text}")
                    return {
                        "success": False,
                        "error": f"API error {resp.status_code}",
                        "user_id": user_id,
                        "app_id": app_id
                    }
                
        except Exception as e:
            logger.error(f"Failed to consume tokens via API: {e}")
            return {
                "success": False,
                "error": f"API call failed: {e}",
                "user_id": user_id,
                "app_id": app_id
            }

    async def initialize_budget(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Initialize budget for a new chat. Determines if it's a free trial or paid account.
        Returns the budget configuration that was set up.
        """
        if user_id:
            self.user_id = user_id
            
        try:
            # Check if this is the first workflow for this enterprise
            count = await mongodb_manager.workflows_collection.count_documents({
                "enterprise_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id")
            })

            # Always fetch token balance for tracking purposes
            if self.user_id:
                self.token_balance = await self._fetch_token_balance(self.user_id)
            else:
                self.token_balance = 0

            if count == 0:
                # First workflow - grant free trial but still track tokens
                trial_config = get_free_trial_config()
                self.free_loops_remaining = trial_config["loops"]
                self.is_free_trial = True
                self.turn_limit = trial_config["turn_limit"]  # Limited turns for free trial
                
                log_business_event(
                    event_type="free_trial_granted",
                    description="First workflow → 3 free loops granted (tokens tracked but not consumed)",
                    context={
                        "chat_id": self.chat_id, 
                        "enterprise_id": self.enterprise_id,
                        "token_balance": self.token_balance,
                        "user_id": self.user_id
                    }
                )
                
                budget_data = {
                    "budget_type": "free_trial",
                    "free_loops_remaining": self.free_loops_remaining,
                    "token_balance": self.token_balance,  # Track but don't consume during trial
                    "turn_limit": self.turn_limit
                }
            else:
                # Check if user has exhausted free trial but still has tokens
                # Look for any previous workflows to see if they've used free trial
                previous_workflows = await mongodb_manager.workflows_collection.find_one({
                    "enterprise_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id"),
                    "budget_type": "free_trial"
                })
                
                if previous_workflows:
                    # User has used free trial before, now use token balance
                    self.is_free_trial = False
                    self.free_loops_remaining = None
                    self.turn_limit = None  # No turn limit for paid users
                    
                    log_business_event(
                        event_type="token_billing_active",
                        description=f"Post-trial: Using token balance billing ({self.token_balance} tokens)",
                        context={
                            "chat_id": self.chat_id, 
                            "user_id": self.user_id, 
                            "balance": self.token_balance,
                            "low_balance_warning": self.token_balance < 100
                        }
                    )
                    
                    budget_data = {
                        "budget_type": "paid_tokens",
                        "token_balance": self.token_balance,
                        "free_loops_remaining": None,
                        "turn_limit": self.turn_limit,
                        "low_balance_warning": self.token_balance < 100
                    }
                else:
                    # Existing enterprise but no previous free trial workflows
                    # This could be a paid account or enterprise setup
                    self.is_free_trial = False
                    self.free_loops_remaining = None
                    self.turn_limit = None
                    
                    budget_data = {
                        "budget_type": "paid_tokens" if self.token_balance > 0 else "no_budget",
                        "token_balance": self.token_balance,
                        "free_loops_remaining": None,
                        "turn_limit": self.turn_limit,
                        "low_balance_warning": self.token_balance < 100
                    }

            # Update database with budget configuration
            await mongodb_manager.update_budget_fields(self.chat_id, self.enterprise_id, budget_data)
            return budget_data

        except Exception as e:
            logger.error(f"Failed to initialize budget for chat {self.chat_id}: {e}")
            log_business_event(
                event_type="budget_init_failed",
                description=f"Budget initialization error: {e}",
                context={"chat_id": self.chat_id},
                level="ERROR"
            )
            # Default to no budget on error
            return {
                "budget_type": "error",
                "token_balance": 0,
                "free_loops_remaining": None
            }

    async def update_usage(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Updates token usage using AG2ObservabilityManager for technical tracking
        and handles business logic for token consumption and budget enforcement.
        Consumes tokens via API for non-free-trial users.
        """
        start_time = datetime.utcnow()
        
        # Use direct AG2 gather_usage_summary approach (like working VE version)
        agent_summary = gather_usage_summary(agents)
        
        # Calculate session usage (following working VE pattern)
        session_PromptTokens = 0
        session_CompletionTokens = 0
        session_TotalTokens = 0
        session_TotalCost = 0.0

        # Process usage_including_cached_inference like the working version
        for Model_name, Model_data in agent_summary.get("usage_including_cached_inference", {}).items():
            if Model_name != 'total_cost':
                session_PromptTokens += Model_data.get('prompt_tokens', 0)
                session_CompletionTokens += Model_data.get('completion_tokens', 0) 
                session_TotalTokens += Model_data.get('total_tokens', 0)
                session_TotalCost += Model_data.get('cost', 0.0)

        # Prepare turn usage data
        turn_usage = {
            "total_tokens": session_TotalTokens,
            "prompt_tokens": session_PromptTokens,
            "completion_tokens": session_CompletionTokens,
            "total_cost": session_TotalCost,
            "models_used": list(agent_summary.get("models", {}).keys()),
            "cached_tokens": 0,  # Could calculate if needed
            "timestamp": start_time.isoformat(),
            "ag2_usage_summary": agent_summary  # Store full AG2 response for debugging
        }

        # Log the usage calculation
        token_logger.info(f"[USAGE] Chat: {self.chat_id[:8]} | Tokens: {session_TotalTokens} | Cost: ${session_TotalCost:.4f}")
        token_logger.debug(f"[DETAIL] Prompt: {session_PromptTokens}, Completion: {session_CompletionTokens}")

        # Skip if no usage
        if session_TotalTokens == 0 and session_TotalCost == 0.0:
            token_logger.info(f"[SKIP] No usage or cost incurred for chat {self.chat_id[:8]}")
            return turn_usage

        # Update business usage tracking (what we bill for)
        self.business_usage["total_tokens_billed"] += session_TotalTokens
        self.business_usage["total_cost_billed"] += session_TotalCost
        
        # Log to consolidated token tracking log with clear categorization
        token_logger.info(f"[BILLING] Usage Update | Chat: {self.chat_id[:8]} | Tokens: {session_TotalTokens} | Cost: ${session_TotalCost:.4f}")
        token_logger.debug(f"[CUMULATIVE] Total Billed: {self.business_usage['total_tokens_billed']} tokens | ${self.business_usage['total_cost_billed']:.4f}")
        
        # Handle token consumption based on trial status
        if not self.is_free_trial and self.user_id and session_TotalTokens > 0:
            # Actually consume tokens via API for non-free-trial users
            consume_result = await self._consume_tokens_api(self.user_id, session_TotalTokens)
            
            if consume_result.get("success", False):
                # Update local balance with API response
                self.token_balance = consume_result.get("remaining", self.token_balance)
                self.business_usage["api_calls_made"] += 1
                self.business_usage["api_tokens_consumed"] += session_TotalTokens
                
                # IMPORTANT: Reset agent usage counters after successful billing
                # This prevents cumulative token counting in subsequent turns
                try:
                    from core.monitoring.observability import get_observer
                    observer = get_observer(self.chat_id, self.enterprise_id)
                    observer.reset_agent_usage(agents)
                    token_logger.debug(f"[BILLING] Reset agent usage counters after billing {session_TotalTokens} tokens")
                except Exception as reset_error:
                    token_logger.warning(f"[BILLING] Failed to reset agent usage: {reset_error}")
                
                token_logger.info(f"[API_SUCCESS] User: {self.user_id} | Consumed: {session_TotalTokens} | Balance: {self.token_balance}")
                
                log_business_event(
                    event_type="tokens_consumed_via_api",
                    description=f"Tokens consumed via API: {session_TotalTokens}, Balance: {self.token_balance}",
                    context={
                        "chat_id": self.chat_id,
                        "tokens_used": session_TotalTokens,
                        "remaining_balance": self.token_balance,
                        "api_response": consume_result,
                        "technical_usage": agent_summary
                    }
                )
            else:
                # API consumption failed - handle error
                token_logger.error(f"[API_FAILURE] User: {self.user_id} | Requested: {turn_usage['total_tokens']} | Error: {consume_result.get('error')}")
                logger.error(f"Failed to consume tokens via API: {consume_result}")
                log_business_event(
                    event_type="token_consumption_failed",
                    description=f"API token consumption failed: {consume_result.get('error', 'Unknown error')}",
                    context={
                        "chat_id": self.chat_id,
                        "tokens_requested": session_TotalTokens,
                        "api_response": consume_result
                    },
                    level="ERROR"
                )
                
                # Force termination on API failure for paid users
                self.termination_reason = f"Token consumption failed: {consume_result.get('error', 'API error')}"
                self.termination_triggered = True
        else:
            # For free trial users, track usage but don't consume tokens
            token_logger.info(f"[FREE_TRIAL] Chat: {self.chat_id[:8]} | Tokens: {session_TotalTokens} (tracked) | Loops Left: {self.free_loops_remaining}")
            
            # Reset agent usage counters for free trial users too
            try:
                from core.monitoring.observability import get_observer
                observer = get_observer(self.chat_id, self.enterprise_id)
                observer.reset_agent_usage(agents)
                token_logger.debug(f"[FREE_TRIAL] Reset agent usage counters after tracking {session_TotalTokens} tokens")
            except Exception as reset_error:
                token_logger.warning(f"[FREE_TRIAL] Failed to reset agent usage: {reset_error}")
            
            log_business_event(
                event_type="tokens_tracked_not_consumed",
                description=f"Free trial: {session_TotalTokens} tokens tracked but not consumed",
                context={
                    "chat_id": self.chat_id,
                    "tokens_tracked": session_TotalTokens,
                    "free_loops_remaining": self.free_loops_remaining,
                    "technical_usage": agent_summary
                }
            )
        
        # Increment turn count for limit enforcement
        current_turn = self.increment_turn_count()
        turn_usage["turn_number"] = current_turn
        
        self.session_history.append(turn_usage)

        # Save using clean schema only (phasing out comprehensive persistence)
        try:
            # mongodb_manager is already imported at the top as persistence_manager alias
            await mongodb_manager.save_token_usage(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id, 
                session_id=getattr(self, 'session_id', self.chat_id),
                total_tokens=session_TotalTokens,
                prompt_tokens=session_PromptTokens,
                completion_tokens=session_CompletionTokens,
                total_cost=session_TotalCost,
                turn_number=current_turn
            )
            token_logger.info(f"[CLEAN_DB] Saved clean token usage for chat {self.chat_id[:8]} | Turn: {current_turn}")
        except Exception as e:
            token_logger.error(f"[CLEAN_DB] Failed to save clean token usage: {e}")

        return turn_usage

    async def consume_free_loop(self) -> bool:
        """
        Consume one free loop if available. Returns True if successful, False if no loops left.
        Should be called when a complete user feedback cycle is finished.
        """
        if not self.is_free_trial or self.free_loops_remaining is None or self.free_loops_remaining <= 0:
            return False

        try:
            # Atomically decrement in database
            remaining = await mongodb_manager.decrement_free_loops(self.chat_id, self.enterprise_id)
            
            if remaining is not None:
                self.free_loops_remaining = remaining
                self.current_loop += 1  # Increment completed loops counter
                
                log_business_event(
                    event_type="free_loop_consumed",
                    description=f"Free loop consumed. Loop #{self.current_loop} completed. Remaining: {remaining}",
                    context={
                        "chat_id": self.chat_id, 
                        "remaining": remaining,
                        "loops_completed": self.current_loop
                    }
                )
                
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to consume free loop for chat {self.chat_id}: {e}")
            return False

    def increment_turn_count(self) -> int:
        """
        Increment the turn counter for individual agent responses.
        Returns the new turn count.
        """
        self.turn_count += 1
        
        log_business_event(
            event_type="agent_turn_completed",
            description=f"Agent turn #{self.turn_count} completed",
            context={
                "chat_id": self.chat_id,
                "turn_count": self.turn_count,
                "turn_limit": self.turn_limit,
                "is_free_trial": self.is_free_trial
            }
        )
        
        return self.turn_count

    def increment_user_interaction(self) -> int:
        """
        Track user proxy interactions (when the user provides input).
        Returns the new user interaction count.
        """
        self.user_interactions += 1
        
        log_business_event(
            event_type="user_interaction_recorded",
            description=f"User interaction #{self.user_interactions}",
            context={
                "chat_id": self.chat_id,
                "user_interactions": self.user_interactions
            }
        )
        
        return self.user_interactions

    async def complete_user_feedback_loop(self) -> bool:
        """
        Mark a complete user feedback loop as finished and consume a free loop if applicable.
        A loop is complete when:
        1. User provides input
        2. Agents process and respond
        3. Results are delivered back to user
        
        Returns True if loop was successfully completed, False if free trial limit reached.
        """
        if self.is_free_trial:
            loop_consumed = await self.consume_free_loop()
            if not loop_consumed:
                log_business_event(
                    event_type="user_feedback_loop_blocked",
                    description="User feedback loop could not be completed - free trial limit reached",
                    context={"chat_id": self.chat_id, "loops_completed": self.current_loop}
                )
                return False
                
        log_business_event(
            event_type="user_feedback_loop_completed",
            description=f"User feedback loop completed successfully. Total loops: {self.current_loop}",
            context={
                "chat_id": self.chat_id,
                "loops_completed": self.current_loop,
                "is_free_trial": self.is_free_trial
            }
        )
        
        return True

    async def load_budget(self) -> None:
        """
        Loads token balance and other budget-related settings from the database.
        """
        start_time = datetime.utcnow()
        try:
            chat_data = await mongodb_manager.load_chat_state(self.chat_id, self.enterprise_id)
            if chat_data:
                self.token_balance = chat_data.get("token_balance", 0)
                budget_settings = chat_data.get("budget_settings", {})
                self.cost_limit = budget_settings.get("cost_limit", 5.0)
                self.turn_limit = budget_settings.get("turn_limit", 20)
                logger.info(f"Budget loaded for chat {self.chat_id}: {self.token_balance} tokens remaining.")
            else:
                logger.warning(f"No chat data found for chat {self.chat_id}. Using default budget.")
            
            log_performance_metric(
                metric_name="load_budget_duration", 
                value=(datetime.utcnow() - start_time).total_seconds(), 
                unit="seconds"
            )

        except Exception as e:
            logger.error(f"Failed to load budget for chat {self.chat_id}: {e}")
            log_business_event(
                event_type="budget_load_failed", 
                description=f"Error: {e}", 
                context={"chat_id": self.chat_id}, 
                level="ERROR"
            )

    async def _transition_to_token_billing(self) -> None:
        """
        Transition from free trial to token-based billing and persist the state change.
        """
        try:
            budget_data = {
                "budget_type": "paid_tokens" if self.token_balance > 0 else "no_budget",
                "token_balance": self.token_balance,
                "free_loops_remaining": None,
                "turn_limit": None,
                "low_balance_warning": self.token_balance < 100,
                "is_free_trial": False
            }
            
            await mongodb_manager.update_budget_fields(self.chat_id, self.enterprise_id, budget_data)
            
            log_business_event(
                event_type="billing_transition_persisted",
                description="Successfully transitioned from free trial to token-based billing",
                context={
                    "chat_id": self.chat_id,
                    "new_budget_type": budget_data["budget_type"],
                    "token_balance": self.token_balance
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to persist billing transition for chat {self.chat_id}: {e}")
            log_business_event(
                event_type="billing_transition_failed",
                description=f"Error persisting billing transition: {e}",
                context={"chat_id": self.chat_id},
                level="ERROR"
            )

    def check_termination(self) -> Tuple[bool, Optional[str]]:
        """
        Checks if the conversation should terminate based on budget, cost, turn limits, or free trial exhaustion.
        
        For free trial users:
        - Loop limits (user feedback cycles) are the primary constraint
        - Turn limits also apply for safety (10 turns max)
        - Tokens are tracked but not consumed during trial
        
        For post-trial/paid users:
        - Token balance is the primary constraint
        - Warning is issued when tokens < 100
        - No loop limits apply
        """
        if self.termination_triggered:
            return True, self.termination_reason

        # Check turn limit (applies to both free trial and paid users if set)
        if self.turn_limit is not None and self.turn_count >= self.turn_limit:
            self.termination_reason = f"Turn limit reached ({self.turn_count}/{self.turn_limit} turns)"
            self.termination_triggered = True
            log_business_event(
                event_type="turn_limit_reached",
                description=self.termination_reason,
                context={"chat_id": self.chat_id, "turns": self.turn_count, "limit": self.turn_limit}
            )
            return True, self.termination_reason

        # Check cost limit (safety net) - use business usage tracking
        if self.business_usage["total_cost_billed"] >= self.cost_limit:
            self.termination_reason = f"Cost limit reached (${self.business_usage['total_cost_billed']:.2f})"
            self.termination_triggered = True
            return True, self.termination_reason
        
        # Free trial: Check loop limit (primary constraint)
        if self.is_free_trial:
            if self.free_loops_remaining is not None and self.free_loops_remaining <= 0:
                # Transition from free trial to token-based billing
                self.is_free_trial = False
                self.free_loops_remaining = None
                self.turn_limit = None  # Remove turn limit for paid users
                
                # Persist the transition asynchronously (we'll schedule it)
                import asyncio
                try:
                    asyncio.create_task(self._transition_to_token_billing())
                except:
                    # If we can't schedule, just log the transition
                    pass
                
                log_business_event(
                    event_type="free_trial_completed_transition",
                    description=f"Free trial completed ({self.current_loop} loops used). Transitioning to token-based billing.",
                    context={
                        "chat_id": self.chat_id, 
                        "loops_completed": self.current_loop,
                        "token_balance": self.token_balance,
                        "transitioned_to_token_billing": True
                    }
                )
                
                # Now check token balance for continued operation
                if self.token_balance <= 0:
                    self.termination_reason = "Free trial completed and no tokens available. Please purchase tokens to continue."
                    self.termination_triggered = True
                    log_business_event(
                        event_type="post_trial_no_tokens",
                        description=self.termination_reason,
                        context={"chat_id": self.chat_id, "token_balance": self.token_balance}
                    )
                    return True, self.termination_reason
                elif self.token_balance < 100:
                    # Warn but don't terminate
                    log_business_event(
                        event_type="post_trial_low_tokens",
                        description=f"Free trial completed. Low token balance: {self.token_balance} tokens",
                        context={
                            "chat_id": self.chat_id, 
                            "token_balance": self.token_balance,
                            "warning_threshold": 100,
                            "action_required": "purchase_tokens"
                        }
                    )
        else:
            # Post-trial/paid users: Check token balance
            if self.token_balance <= 0:
                self.termination_reason = "Token balance depleted. Please purchase more tokens to continue."
                self.termination_triggered = True
                log_business_event(
                    event_type="token_balance_depleted",
                    description=self.termination_reason,
                    context={"chat_id": self.chat_id, "final_balance": self.token_balance}
                )
                return True, self.termination_reason
            
            # Low balance warning (not termination)
            if self.token_balance < 100 and self.turn_count % 5 == 0:  # Warn every 5 turns when low
                log_business_event(
                    event_type="low_token_balance_warning",
                    description=f"Low token balance: {self.token_balance} tokens remaining",
                    context={
                        "chat_id": self.chat_id, 
                        "balance": self.token_balance,
                        "warning_threshold": 100,
                        "action_required": "purchase_tokens"
                    }
                )

        return False, None

    async def _persist_usage(self, turn_usage: Dict[str, Any]) -> None:
        """
        Persists the latest token usage and balance to the database with comprehensive data.
        """
        try:
            # Get observability data for technical tracking
            observability_summary = self.observability.get_session_summary()
            
            await mongodb_manager.update_token_usage(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                session_usage=turn_usage,
                business_usage=self.business_usage,
                observability_data=observability_summary
            )
            
            token_logger.debug(f"[PERSISTENCE] Saved comprehensive usage data for chat {self.chat_id[:8]}")

        except Exception as e:
            token_logger.error(f"[PERSISTENCE_ERROR] Failed to persist usage data: {e}")
            logger.error(f"Failed to persist token usage for chat {self.chat_id}: {e}")
            log_business_event(
                event_type="persist_usage_failed", 
                description=f"Error: {e}", 
                context={"chat_id": self.chat_id}, 
                level="ERROR"
            )

    def get_summary(self) -> Dict[str, Any]:
        """
        Returns a summary of the current token usage and budget state.
        """
        return {
            "chat_id": self.chat_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "business_usage": self.business_usage,  # Business billing data
            "technical_usage": self.observability.get_session_summary(),  # Technical AG2 data
            "budget_info": {
                "is_free_trial": self.is_free_trial,
                "free_loops_remaining": self.free_loops_remaining,
                "token_balance": self.token_balance,
                "cost_limit": self.cost_limit,
                "turn_limit": self.turn_limit
            },
            "turns_taken": len(self.session_history),
            "termination_status": {
                "triggered": self.termination_triggered,
                "reason": self.termination_reason,
            },
            "api_config": {
                "using_mock_api": USE_MOCK_API,
                "app_id": self._get_app_id()
            }
        }