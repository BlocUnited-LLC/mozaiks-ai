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
    "user123": 100000,    "user456": 50000, 
    "user789": 5000,    "user0001": 150000,    "test_user": 200000,}

MOCK_APP_IDS = {
    "default": "app_12345",
    "enterprise_test": "app_67890"
}

# Mock enterprise data for testing free trial logic
MOCK_ENTERPRISE_DATA = {
    "enterprise_new": {"free_trial": True, "available_tokens": 0},
    "enterprise_trial_ended": {"free_trial": False, "available_tokens": 50000},
    "enterprise_no_tokens": {"free_trial": False, "available_tokens": 0},
    "test_enterprise": {"free_trial": True, "available_tokens": 0}
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

def _mock_get_enterprise_data(enterprise_id: str) -> dict:
    """Mock function to get enterprise free trial status and token balance"""
    return MOCK_ENTERPRISE_DATA.get(enterprise_id, {"free_trial": True, "available_tokens": 0})

class InsufficientTokensError(Exception):
    """Raised when user has insufficient tokens for workflow execution"""
    pass

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

from core.data.persistence_manager import PersistenceManager

# Create instance for database operations
mongodb_manager = PersistenceManager()
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
    Simplified token-based usage system with free trial support.
    
    Core Principles:
    - Always tracks token usage for analytics
    - Free trial: tracks but doesn't deduct tokens from balance
    - Post-trial: deducts tokens from available_tokens balance
    - Simple error when balance insufficient: "You're out of tokens. Please top up your account."
    
    Usage Pattern:
    1. initialize_budget() - Load enterprise trial status and token balance
    2. update_usage() - Track token consumption during workflow execution
    3. check_token_balance() - Validate sufficient tokens before expensive operations
    4. finalize_conversation() - Complete workflow and handle token deduction
    """

    def __init__(self, chat_id: str, enterprise_id: str, workflow_type: str, user_id: Optional[str] = None):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.workflow_type = workflow_type
        self.user_id = user_id
        
        # Core usage tracking (always tracked for analytics)
        self.session_usage = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "agents": {}
        }
        
        # Simple billing flags
        self.is_free_trial = None  # Will be loaded from enterprise data
        self.available_tokens = 0  # Will be loaded from enterprise balance
        
        # Session tracking
        self.session_id = str(uuid.uuid4())
        self.workflow_finalized = False
        
        # Remove complex logic - keep simple
        self.termination_triggered = False
        self.termination_reason = None
        
        # Business usage tracking (simplified)
        self.business_usage = {
            "total_tokens_billed": 0,
            "total_cost_billed": 0.0,
            "api_calls_made": 0,
            "api_tokens_consumed": 0
        }
        
        # Initialize observability and persistence
        from core.monitoring.observability import AG2ObservabilityManager
        self.observability = AG2ObservabilityManager(self.chat_id, self.enterprise_id)
        
        # Session tracking (simplified)
        self.session_history = []
        
        # Use instance
        self.mongodb_manager = mongodb_manager
        
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
        Load enterprise token balance and free trial status.
        Simple initialization - no complex tier logic.
        """
        if user_id:
            self.user_id = user_id
            
        try:
            # Load enterprise data (mock or real API)
            if USE_MOCK_API:
                enterprise_data = _mock_get_enterprise_data(str(self.enterprise_id))
                self.is_free_trial = enterprise_data.get("free_trial", True)
                self.available_tokens = enterprise_data.get("available_tokens", 0)
            else:
                # Load from database in real implementation
                enterprise_doc = await mongodb_manager.enterprises_collection.find_one({
                    "_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id")
                })
                
                if not enterprise_doc:
                    # New enterprise - start with free trial
                    self.is_free_trial = True
                    self.available_tokens = 0
                    
                    # Initialize enterprise record
                    await mongodb_manager.enterprises_collection.update_one(
                        {"_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id")},
                        {
                            "$set": {
                                "free_trial": True,
                                "available_tokens": 0,
                                "total_tokens_used": 0,
                                "total_cost_incurred": 0.0,
                                "created_at": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                else:
                    # Existing enterprise - load current status
                    self.is_free_trial = enterprise_doc.get("free_trial", False)
                    self.available_tokens = enterprise_doc.get("available_tokens", 0)
            
            log_business_event(
                event_type="budget_initialized",
                description=f"Budget initialized for enterprise {self.enterprise_id}",
                context={
                    "enterprise_id": self.enterprise_id,
                    "is_free_trial": self.is_free_trial,
                    "available_tokens": self.available_tokens,
                    "chat_id": self.chat_id,
                    "workflow_type": self.workflow_type
                }
            )
            
            return {
                "success": True,
                "is_free_trial": self.is_free_trial,
                "available_tokens": self.available_tokens,
                "session_id": self.session_id
            }
            
        except Exception as e:
            logger.error(f"Failed to initialize budget for enterprise {self.enterprise_id}: {e}")
            return {"success": False, "error": str(e)}

    async def check_token_balance(self, estimated_tokens: int = 0) -> Tuple[bool, Optional[str]]:
        """
        Check if user has sufficient tokens for continued execution.
        
        - Free trial: Always return True (no deduction)
        - Post-trial: Check available_tokens balance
        """
        if self.is_free_trial:
            return True, None
        
        if self.available_tokens <= 0:
            return False, "You're out of tokens. Please top up your account."
        
        if estimated_tokens > 0 and self.available_tokens < estimated_tokens:
            return False, f"Insufficient tokens. Need {estimated_tokens}, have {self.available_tokens}. Please top up your account."
        
        return True, None

    async def update_usage(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        CENTRALIZED TOKEN TRACKING LOGIC
        
        Extracts per-agent usage from AG2 and creates structured session data.
        Uses PersistenceManager for database storage with new schema:
        - Per-agent tracking within sessions
        - Workflow aggregates across all sessions
        - Clean separation: TokenManager=logic, PersistenceManager=storage
        """
        start_time = datetime.utcnow()
        
        # Use direct AG2 gather_usage_summary approach
        agent_summary = gather_usage_summary(agents)
        
        # ====================================================================
        # EXTRACT PER-AGENT USAGE (New Schema)
        # ====================================================================
        agent_names = [agent.name for agent in agents if hasattr(agent, 'name')]
        session_data = {
            "session_id": self.session_id,
            "PromptTokens": 0,
            "CompletionTokens": 0,
            "TotalCost": 0.0,
            "agents": {}  # Per-agent tracking
        }
        
        # Extract per-agent usage from AG2 client usage data
        for agent in agents:
            if not hasattr(agent, 'name'):
                continue
                
            agent_name = agent.name
            agent_data = {
                f"{agent_name}_PromptTokens": 0,
                f"{agent_name}_CompletionTokens": 0,
                f"{agent_name}_PromptCost": 0.0,
                f"{agent_name}_CompletionCost": 0.0,
                f"{agent_name}_TotalCost": 0.0
            }
            
            # Extract usage from agent's client if available
            # Note: AG2 agents may have different client structures
            client = None
            if hasattr(agent, 'client'):
                client = getattr(agent, 'client', None)
            elif hasattr(agent, '_client'):
                client = getattr(agent, '_client', None)
            elif hasattr(agent, 'llm_config'):
                # Try to get client from config
                llm_config = getattr(agent, 'llm_config', {})
                if isinstance(llm_config, dict):
                    client = llm_config.get('client')
            
            if client and hasattr(client, 'get_usage'):
                try:
                    # Get usage for this specific agent's client
                    client_usage = client.get_usage()
                    if client_usage:
                        # Extract token counts and costs
                        agent_prompt = client_usage.get('prompt_tokens', 0)
                        agent_completion = client_usage.get('completion_tokens', 0)
                        agent_cost = client_usage.get('cost', 0.0)
                        
                        # Calculate cost breakdown (if not provided)
                        if agent_cost > 0 and (agent_prompt + agent_completion) > 0:
                            # Estimate prompt vs completion cost (rough 1:2 ratio typical)
                            total_tokens = agent_prompt + agent_completion
                            prompt_ratio = agent_prompt / total_tokens if total_tokens > 0 else 0.5
                            completion_ratio = agent_completion / total_tokens if total_tokens > 0 else 0.5
                            
                            agent_data[f"{agent_name}_PromptTokens"] = agent_prompt
                            agent_data[f"{agent_name}_CompletionTokens"] = agent_completion
                            agent_data[f"{agent_name}_PromptCost"] = agent_cost * prompt_ratio
                            agent_data[f"{agent_name}_CompletionCost"] = agent_cost * completion_ratio
                            agent_data[f"{agent_name}_TotalCost"] = agent_cost
                            
                            # Add to session totals
                            session_data["PromptTokens"] += agent_prompt
                            session_data["CompletionTokens"] += agent_completion
                            session_data["TotalCost"] += agent_cost
                            
                except Exception as e:
                    token_logger.warning(f"Failed to extract usage for agent {agent_name}: {e}")
            
            # Store agent data in session (even if zero - for complete tracking)
            session_data["agents"][agent_name] = agent_data
        
        # ====================================================================
        # FALLBACK: Use AG2 aggregate if per-agent extraction fails
        # ====================================================================
        if session_data["PromptTokens"] == 0 and session_data["CompletionTokens"] == 0:
            # Fall back to AG2 aggregate usage
            for Model_name, Model_data in agent_summary.get("usage_including_cached_inference", {}).items():
                if Model_name != 'total_cost':
                    session_data["PromptTokens"] += Model_data.get('prompt_tokens', 0)
                    session_data["CompletionTokens"] += Model_data.get('completion_tokens', 0)
                    session_data["TotalCost"] += Model_data.get('cost', 0.0)
            
            token_logger.info(f"Using AG2 aggregate fallback: {session_data['PromptTokens']} tokens")
        
        # ====================================================================
        # PREPARE TURN USAGE DATA (For business logic)
        # ====================================================================
        turn_usage = {
            "total_tokens": session_data["PromptTokens"] + session_data["CompletionTokens"],
            "prompt_tokens": session_data["PromptTokens"],
            "completion_tokens": session_data["CompletionTokens"], 
            "total_cost": session_data["TotalCost"],
            "models_used": list(agent_summary.get("models", {}).keys()),
            "timestamp": start_time.isoformat(),
            "session_data": session_data,  # Include full session data for persistence
            "ag2_usage_summary": agent_summary  # Store full AG2 response for debugging
        }

        # ====================================================================
        # BUSINESS LOGIC & LOGGING (Updated for new schema)
        # ====================================================================
        total_tokens = turn_usage["total_tokens"]
        total_cost = turn_usage["total_cost"]
        
        # Log the usage calculation
        token_logger.info(f"[USAGE] Chat: {self.chat_id[:8]} | Tokens: {total_tokens} | Cost: ${total_cost:.4f}")
        token_logger.debug(f"[DETAIL] Prompt: {session_data['PromptTokens']}, Completion: {session_data['CompletionTokens']}")

        # Skip if no usage
        if total_tokens == 0 and total_cost == 0.0:
            token_logger.info(f"[SKIP] No usage or cost incurred for chat {self.chat_id[:8]}")
            return turn_usage

        # Update business usage tracking (what we bill for)
        self.business_usage["total_tokens_billed"] += total_tokens
        self.business_usage["total_cost_billed"] += total_cost
        
        # Log to consolidated token tracking log with clear categorization
        token_logger.info(f"[BILLING] Usage Update | Chat: {self.chat_id[:8]} | Tokens: {total_tokens} | Cost: ${total_cost:.4f}")
        token_logger.debug(f"[CUMULATIVE] Total Billed: {self.business_usage['total_tokens_billed']} tokens | ${self.business_usage['total_cost_billed']:.4f}")
        
        # ====================================================================
        # TOKEN CONSUMPTION (API Integration)
        # ====================================================================
        # Handle token consumption based on trial status
        if not self.is_free_trial and self.user_id and total_tokens > 0:
            # Actually consume tokens via API for non-free-trial users
            consume_result = await self._consume_tokens_api(self.user_id, total_tokens)
            
            if consume_result.get("success", False):
                # Update local balance with API response
                self.token_balance = consume_result.get("remaining", self.token_balance)
                self.business_usage["api_calls_made"] += 1
                self.business_usage["api_tokens_consumed"] += total_tokens
                
                # IMPORTANT: Reset agent usage counters after successful billing
                # This prevents cumulative token counting in subsequent turns
                try:
                    from core.monitoring.observability import get_observer
                    observer = get_observer(self.chat_id, self.enterprise_id)
                    observer.reset_agent_usage(agents)
                    token_logger.debug(f"[BILLING] Reset agent usage counters after billing {total_tokens} tokens")
                except Exception as reset_error:
                    token_logger.warning(f"[BILLING] Failed to reset agent usage: {reset_error}")
                
                token_logger.info(f"[API_SUCCESS] User: {self.user_id} | Consumed: {total_tokens} | Balance: {self.token_balance}")
                
                log_business_event(
                    event_type="tokens_consumed_via_api",
                    description=f"Tokens consumed via API: {total_tokens}, Balance: {self.token_balance}",
                    context={
                        "chat_id": self.chat_id,
                        "tokens_used": total_tokens,
                        "remaining_balance": self.token_balance,
                        "api_response": consume_result,
                        "technical_usage": agent_summary
                    }
                )
            else:
                # API consumption failed - handle error
                token_logger.error(f"[API_FAILURE] User: {self.user_id} | Requested: {total_tokens} | Error: {consume_result.get('error')}")
                logger.error(f"Failed to consume tokens via API: {consume_result}")
                log_business_event(
                    event_type="token_consumption_failed",
                    description=f"API token consumption failed: {consume_result.get('error', 'Unknown error')}",
                    context={
                        "chat_id": self.chat_id,
                        "tokens_requested": total_tokens,
                        "api_response": consume_result
                    },
                    level="ERROR"
                )
                
                # Force termination on API failure for paid users
                self.termination_reason = f"Token consumption failed: {consume_result.get('error', 'API error')}"
                self.termination_triggered = True
        else:
            # For free trial users, track usage but don't consume tokens
            token_logger.info(f"[FREE_TRIAL] Chat: {self.chat_id[:8]} | Tokens: {total_tokens} (tracked) | Loops Left: {self.free_loops_remaining}")
            
            # Reset agent usage counters for free trial users too
            try:
                from core.monitoring.observability import get_observer
                observer = get_observer(self.chat_id, self.enterprise_id)
                observer.reset_agent_usage(agents)
                token_logger.debug(f"[FREE_TRIAL] Reset agent usage counters after tracking {total_tokens} tokens")
            except Exception as reset_error:
                token_logger.warning(f"[FREE_TRIAL] Failed to reset agent usage: {reset_error}")
            
            log_business_event(
                event_type="tokens_tracked_not_consumed",
                description=f"Free trial - tokens tracked but not consumed: {total_tokens}",
                context={
                    "chat_id": self.chat_id,
                    "tokens_tracked": total_tokens,
                    "free_loops_remaining": self.free_loops_remaining
                }
            )
        
        # ====================================================================
        # PERSISTENCE (Use PersistenceManager for new schema)
        # ====================================================================
        # Increment turn count for limit enforcement
        current_turn = self.increment_turn_count()
        turn_usage["turn_number"] = current_turn
        
        self.session_history.append(turn_usage)

        # Save using PersistenceManager with new schema
        try:
            await mongodb_manager.save_session_usage(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                workflow_type=self.workflow_type,
                session_data=session_data,
                agents=agent_names
            )
            token_logger.debug(f"[PERSISTENCE] Saved session usage to new schema")
        except Exception as e:
            token_logger.error(f"[PERSISTENCE] Failed to save session usage: {e}")

        return turn_usage

    def extract_per_agent_usage(self, agents: List[Any]) -> Dict[str, Dict[str, Any]]:
        """
        Extract per-agent token usage from AG2 agents for centralized tracking.
        This is the main method for getting detailed agent breakdowns.
        
        Args:
            agents: List of AG2 agents from workflow
            
        Returns:
            Dict mapping agent names to their usage data
        """
        per_agent_usage = {}
        
        for agent in agents:
            try:
                agent_name = getattr(agent, 'name', 'Unknown_Agent')
                client = getattr(agent, 'client', None)
                
                if client and hasattr(client, 'usage_summary'):
                    usage = client.usage_summary
                    per_agent_usage[agent_name] = {
                        "PromptTokens": usage.get("prompt_tokens", 0),
                        "CompletionTokens": usage.get("completion_tokens", 0),
                        "TotalTokens": usage.get("total_tokens", 0),
                        "TotalCost": usage.get("total_cost", 0.0)
                    }
                else:
                    # Fallback for agents without client usage
                    per_agent_usage[agent_name] = {
                        "PromptTokens": 0,
                        "CompletionTokens": 0,
                        "TotalTokens": 0,
                        "TotalCost": 0.0
                    }
                    
            except Exception as e:
                token_logger.warning(f"Failed to extract usage for agent {getattr(agent, 'name', 'Unknown')}: {e}")
                per_agent_usage[getattr(agent, 'name', 'Unknown_Agent')] = {
                    "PromptTokens": 0,
                    "CompletionTokens": 0,
                    "TotalTokens": 0,
                    "TotalCost": 0.0
                }
        
        return per_agent_usage

    async def consume_free_loop(self) -> bool:
        """
        Consume one free loop if available. Returns True if successful, False if no loops left.
        Should be called when a complete user feedback cycle is finished.
        """
        if not self.is_free_trial or self.free_loops_remaining is None or self.free_loops_remaining <= 0:
            return False

        try:
            # Simple decrement for free trial tracking
            if self.free_loops_remaining > 0:
                self.free_loops_remaining -= 1
                self.current_loop += 1  # Increment completed loops counter
                
                log_business_event(
                    event_type="free_loop_consumed",
                    description=f"Free loop consumed. Loop #{self.current_loop} completed. Remaining: {self.free_loops_remaining}",
                    context={
                        "chat_id": self.chat_id, 
                        "remaining": self.free_loops_remaining,
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
            
            # Log budget transition without database update for now
            # TODO: Add budget field updates when PersistenceManager supports it
            
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
                session_id=turn_usage.get("session_id", str(uuid.uuid4())),
                usage_data=turn_usage
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

    async def finalize_conversation(self) -> Dict[str, Any]:
        """
        Finalize the workflow conversation and handle token deduction.
        
        - Mark workflow as complete
        - If free trial: end trial and transition to paid model
        - If post-trial: deduct tokens from available balance
        """
        if self.workflow_finalized:
            return {"success": False, "reason": "Workflow already finalized"}
        
        try:
            # Mark workflow as complete in database
            await mongodb_manager.workflows_collection.update_one(
                {
                    "chat_id": self.chat_id,
                    "enterprise_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id")
                },
                {
                    "$set": {
                        "is_complete": True,
                        "completed_at": datetime.utcnow(),
                        f"{self.workflow_type}_status": 1  # Complete status
                    }
                }
            )
            
            # Handle token deduction based on trial status
            if self.is_free_trial:
                # End free trial and transition to paid model
                await mongodb_manager.enterprises_collection.update_one(
                    {"_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id")},
                    {
                        "$set": {
                            "free_trial": False,
                            "trial_ended_at": datetime.utcnow()
                        },
                        "$inc": {
                            "total_tokens_used": self.session_usage["total_tokens"],
                            "total_cost_incurred": self.session_usage["total_cost"]
                        }
                    }
                )
                
                log_business_event(
                    event_type="free_trial_ended",
                    description=f"Free trial ended for enterprise {self.enterprise_id}",
                    context={
                        "enterprise_id": self.enterprise_id,
                        "trial_tokens_used": self.session_usage["total_tokens"],
                        "trial_cost_incurred": self.session_usage["total_cost"],
                        "workflow_type": self.workflow_type
                    }
                )
                
                self.workflow_finalized = True
                return {
                    "success": True,
                    "trial_ended": True,
                    "tokens_used_in_trial": self.session_usage["total_tokens"],
                    "cost_incurred_in_trial": self.session_usage["total_cost"],
                    "message": "Free trial completed! Please add tokens to your account to continue using workflows."
                }
                
            else:
                # Post-trial: Deduct tokens from available balance
                tokens_to_deduct = self.session_usage["total_tokens"]
                cost_to_deduct = self.session_usage["total_cost"]
                
                # Check if sufficient balance
                if self.available_tokens < tokens_to_deduct:
                    raise InsufficientTokensError(
                        f"Insufficient tokens to complete workflow. Need {tokens_to_deduct}, have {self.available_tokens}"
                    )
                
                # Deduct from enterprise balance
                await mongodb_manager.enterprises_collection.update_one(
                    {"_id": mongodb_manager._ensure_object_id(self.enterprise_id, "enterprise_id")},
                    {
                        "$inc": {
                            "available_tokens": -tokens_to_deduct,
                            "total_tokens_used": tokens_to_deduct,
                            "total_cost_incurred": cost_to_deduct
                        }
                    }
                )
                
                # Update local balance
                self.available_tokens -= tokens_to_deduct
                
                log_business_event(
                    event_type="tokens_deducted",
                    description=f"Tokens deducted for completed workflow",
                    context={
                        "enterprise_id": self.enterprise_id,
                        "tokens_deducted": tokens_to_deduct,
                        "cost_deducted": cost_to_deduct,
                        "remaining_tokens": self.available_tokens,
                        "workflow_type": self.workflow_type
                    }
                )
                
                self.workflow_finalized = True
                return {
                    "success": True,
                    "tokens_deducted": tokens_to_deduct,
                    "cost_deducted": cost_to_deduct,
                    "remaining_tokens": self.available_tokens,
                    "workflow_complete": True
                }
                
        except InsufficientTokensError as e:
            logger.warning(f"Insufficient tokens for enterprise {self.enterprise_id}: {e}")
            return {
                "success": False,
                "error": "insufficient_tokens",
                "message": str(e)
            }
            
        except Exception as e:
            logger.error(f"Failed to finalize conversation for {self.chat_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get current session usage summary"""
        return {
            "session_id": self.session_id,
            "chat_id": self.chat_id,
            "workflow_type": self.workflow_type,
            "is_free_trial": self.is_free_trial,
            "available_tokens": self.available_tokens,
            "session_usage": self.session_usage,
            "workflow_finalized": self.workflow_finalized
        }

    def get_summary(self) -> Dict[str, Any]:
        """
        Returns a summary of the current token usage and budget state.
        """
        return {
            "chat_id": self.chat_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "session_usage": self.session_usage,  # Simplified usage tracking
            "technical_usage": self.observability.get_session_summary(),  # Technical AG2 data
            "budget_info": {
                "is_free_trial": self.is_free_trial,
                "available_tokens": self.available_tokens,
                "workflow_finalized": self.workflow_finalized
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