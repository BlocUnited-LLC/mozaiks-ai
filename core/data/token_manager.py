import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# Import AG2 native imports for native usage tracking and logging
import autogen
from autogen import Agent, gather_usage_summary

from logs.logging_config import get_business_logger, get_performance_logger, get_token_manager_logger, log_business_event, log_performance_metric
from .persistence_manager import PersistenceManager

# Logger setup
business_logger = get_business_logger("observability")
performance_logger = get_performance_logger("observability")
token_logger = get_token_manager_logger("observability")  # Use consolidated token logger
logger = logging.getLogger(__name__)

@dataclass
class AgentTokenUsage:
    """Track token usage for individual agents using AG2's CompletionUsage structure."""
    agent_name: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    model_usage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    message_count: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ChatSessionUsage:
    """Track overall usage for a chat session using AG2's usage tracking patterns."""
    chat_id: str
    session_id: str
    enterprise_id: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    agents: Dict[str, AgentTokenUsage] = field(default_factory=dict)
    total_tokens: int = 0
    total_cost: float = 0.0
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    ag2_usage_summary: Dict[str, Any] = field(default_factory=dict)

@dataclass
class UserTrialData:
    """Track trial usage and limits for individual users."""
    user_id: str
    enterprise_id: str
    free_trial: bool = True
    available_tokens: int = 0
    available_trial_tokens: int = 0

class TokenManager:
    """
    Centralized observability manager using AG2's native features.
    Provides token tracking, cost monitoring, and performance metrics
    using autogen.gather_usage_summary and related AG2 APIs.
    
    Now includes free trial logic with available_tokens and trial_limit management.
    """

    # Enterprise trial limits (hardcoded for now)
    # TODO: Create logic where an agent determines these limits during subscription creation processing
    # This should be moved to a dynamic system where an LLM determines the trial token limit
    # based on enterprise analysis, subscription context, and business rules in another flow
    DEFAULT_TRIAL_LIMIT = 100000  # Fallback trial limit when LLM determination is not available

    def __init__(self, chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default"):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_name = workflow_name
        self.session_id = str(uuid.uuid4())
        
        # Initialize persistence manager
        self.persistence_manager = PersistenceManager()
        
        # Initialize usage tracking
        self.session_usage = ChatSessionUsage(
            chat_id=chat_id,
            session_id=self.session_id,
            enterprise_id=enterprise_id
        )
        
        # Initialize trial data (will load from database)
        self.trial_data: Optional[UserTrialData] = None  # Will be loaded asynchronously
        
        # AG2 runtime logging session
        self.ag2_logging_session_id: Optional[str] = None
        
        # Performance tracking
        self.performance_metrics: Dict[str, List[float]] = {
            "agent_response_times": [],
            "message_processing_times": [],
            "token_calculation_times": []
        }
        
        # Agent-specific performance tracking
        self.agent_performance: Dict[str, Dict[str, Any]] = {}
        
        # Session performance tracking
        self.session_start_time = datetime.utcnow()
        
        logger.info(f"🔍 TokenManager initialized for chat {chat_id} | User: {user_id} | Workflow: {workflow_name}")

    async def initialize_async(self) -> bool:
        """Initialize async components (load user data from database)"""
        try:
            # Load user token data from database
            user_data = await self.persistence_manager.get_user_token_data(self.user_id, self.enterprise_id)
            
            if user_data:
                self.trial_data = UserTrialData(
                    user_id=user_data["user_id"],
                    enterprise_id=user_data["enterprise_id"],
                    free_trial=user_data.get("free_trial", True),
                    available_tokens=user_data.get("available_tokens", 0),
                    available_trial_tokens=user_data.get("available_trial_tokens", self.DEFAULT_TRIAL_LIMIT)
                )
                logger.info(f"💾 Loaded user data: {self.trial_data.available_tokens} tokens, {self.trial_data.available_trial_tokens} trial tokens")
            else:
                # Fallback to default initialization
                self.trial_data = self._initialize_trial_data()
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize async components: {e}")
            # Fallback to in-memory initialization
            self.trial_data = self._initialize_trial_data()
            return False

    def _initialize_trial_data(self) -> UserTrialData:
        """Initialize trial data for the user based on enterprise limits."""
        # TODO: Replace with real API integration for token management
        # Need to integrate with actual persistence layer to:
        # - Load existing user trial data from database
        # - Get real-time token balances via API
        # - Handle token purchases and subscriptions
        # - Sync with billing system for accurate token consumption tracking
        # - Get LLM-determined trial limit from subscription creation flow
        
        # For now, use default trial limit (will be replaced by LLM-determined value)
        trial_limit = self.DEFAULT_TRIAL_LIMIT
        
        # In a real implementation, this would load from database
        # For now, create new trial data with full limit available
        trial_data = UserTrialData(
            user_id=self.user_id,
            enterprise_id=self.enterprise_id,
            free_trial=True,
            available_tokens=0,  # Regular tokens (for paid users)
            available_trial_tokens=trial_limit  # Trial tokens
        )
        
        token_logger.info(f"[TRIAL_INIT] User: {self.user_id} | Enterprise: {self.enterprise_id} | Trial tokens: {trial_limit}")
        
        return trial_data

    async def _persist_token_usage(self, tokens_used: int, deduction_result: Dict[str, Any]) -> bool:
        """Persist token usage to database for analytics"""
        try:
            trial_tokens_used = deduction_result.get("trial_tokens_used", 0)
            regular_tokens_used = tokens_used - trial_tokens_used
            
            # Log token usage to database
            await self.persistence_manager.log_token_usage(
                user_id=self.user_id,
                enterprise_id=self.enterprise_id,
                chat_id=self.chat_id,
                workflow_name=self.workflow_name,
                session_id=self.session_id,
                tokens_used=regular_tokens_used,
                trial_tokens_used=trial_tokens_used,
                token_type="gpt-4",  # TODO: Extract from AG2 usage data
                cost_usd=self.session_usage.total_cost
            )
            
            # Update user token balances in database
            if self.trial_data:
                await self.persistence_manager.update_user_tokens(
                    user_id=self.user_id,
                    enterprise_id=self.enterprise_id,
                    available_tokens=self.trial_data.available_tokens,
                    available_trial_tokens=self.trial_data.available_trial_tokens,
                    free_trial=self.trial_data.free_trial
                )
                
            logger.info(f"💾 Persisted token usage: {tokens_used} tokens ({trial_tokens_used} trial)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to persist token usage: {e}")
            return False

    def check_trial_status(self) -> Dict[str, Any]:
        """Check current trial status and return detailed information."""
        if not self.trial_data:
            logger.warning("⚠️ Trial data not initialized. Call initialize_async() first.")
            return {
                "user_id": self.user_id,
                "enterprise_id": self.enterprise_id,
                "free_trial": False,
                "available_tokens": 0,
                "available_trial_tokens": 0,
                "total_available": 0,
                "can_continue": False,
                "error": "not_initialized"
            }
            
        total_available = self.trial_data.available_tokens + self.trial_data.available_trial_tokens
        
        status = {
            "user_id": self.user_id,
            "enterprise_id": self.enterprise_id,
            "free_trial": self.trial_data.free_trial,
            "available_tokens": self.trial_data.available_tokens,
            "available_trial_tokens": self.trial_data.available_trial_tokens,
            "total_available": total_available,
            "can_continue": total_available > 0 and self.trial_data.free_trial
        }

        return status

    async def deduct_trial_tokens(self, tokens_to_deduct: int) -> Dict[str, Any]:
        """
        Deduct tokens from trial allowance and return status.
        Returns information about whether the operation was successful.
        """
        try:
            if not self.trial_data:
                await self.initialize_async()
                
            if not self.trial_data:
                return {
                    "success": False,
                    "reason": "initialization_failed",
                    "tokens_deducted": 0,
                    "remaining_tokens": 0,
                    "remaining_trial_tokens": 0
                }
                
            trial_status = self.check_trial_status()
            
            if not trial_status["can_continue"]:
                return {
                    "success": False,
                    "reason": "trial_inactive",
                    "message": "Trial is inactive",
                    "trial_status": trial_status
                }
            
            total_available = trial_status["total_available"]
            if total_available < tokens_to_deduct:
                return {
                    "success": False,
                    "reason": "insufficient_tokens",
                    "message": f"Insufficient tokens. Need: {tokens_to_deduct}, Available: {total_available}",
                    "trial_status": trial_status
                }
            
            # Track how tokens were used for analytics
            trial_tokens_used = 0
            regular_tokens_used = 0
            
            # Deduct from trial tokens first, then regular tokens
            if self.trial_data.available_trial_tokens >= tokens_to_deduct:
                trial_tokens_used = tokens_to_deduct
                self.trial_data.available_trial_tokens -= tokens_to_deduct
            else:
                trial_tokens_used = self.trial_data.available_trial_tokens
                remaining_needed = tokens_to_deduct - self.trial_data.available_trial_tokens
                regular_tokens_used = remaining_needed
                self.trial_data.available_trial_tokens = 0
                self.trial_data.available_tokens -= remaining_needed
            
            # If no tokens left, deactivate trial
            if self.trial_data.available_tokens == 0 and self.trial_data.available_trial_tokens == 0:
                self.trial_data.free_trial = False
                
            updated_status = self.check_trial_status()
            
            token_logger.info(f"[TRIAL_DEDUCT] User: {self.user_id} | Deducted: {tokens_to_deduct} | Remaining: {updated_status['total_available']}")
            
            log_business_event(
                event_type="trial_tokens_deducted",
                description=f"Deducted {tokens_to_deduct} tokens from trial",
                context={
                    "user_id": self.user_id,
                    "enterprise_id": self.enterprise_id,
                    "tokens_deducted": tokens_to_deduct,
                    "remaining_total": updated_status["total_available"]
                }
            )
            
            return {
                "success": True,
                "tokens_deducted": tokens_to_deduct,
                "trial_tokens_used": trial_tokens_used,
                "regular_tokens_used": regular_tokens_used,
                "trial_status": updated_status
            }
            
        except Exception as e:
            logger.error(f"Error deducting trial tokens: {e}")
            return {
                "success": False,
                "reason": "error",
                "message": str(e),
                "trial_status": self.check_trial_status()
            }

    def can_proceed_with_request(self) -> Dict[str, Any]:
        """
        Check if user can proceed with a request.
        Returns authorization status and trial information.
        
        NOTE: Future enhancement - Add estimated_tokens parameter here to check
        if user has enough tokens for estimated request cost before processing.
        """
        trial_status = self.check_trial_status()
        
        if not trial_status["free_trial"]:
            return {
                "can_proceed": False,
                "reason": "trial_inactive",
                "message": "Trial period has ended",
                "trial_status": trial_status
            }
        
        if trial_status["total_available"] <= 0:
            return {
                "can_proceed": False,
                "reason": "no_tokens",
                "message": "No tokens available",
                "trial_status": trial_status
            }
        
        return {
            "can_proceed": True,
            "message": "Request authorized",
            "trial_status": trial_status
        }

    def track_agent_message(self, agent_name: str, message_content: str, recipient: str = "unknown", message_type: str = "response") -> None:
        """Track individual agent messages for observability."""
        try:
            message_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "agent_name": agent_name,
                "recipient": recipient,
                "message_type": message_type,
                "content_length": len(message_content),
                "session_id": self.session_id
            }
            
            self.session_usage.message_history.append(message_entry)
            
            # Update agent message count in session usage
            if agent_name not in self.session_usage.agents:
                self.session_usage.agents[agent_name] = AgentTokenUsage(agent_name=agent_name)
            
            self.session_usage.agents[agent_name].message_count += 1
            self.session_usage.agents[agent_name].last_updated = datetime.utcnow()
            
            # Track performance metrics
            self.track_agent_message_performance(agent_name, message_content)
            
            # Log message tracking to consolidated token log
            token_logger.debug(f"[MESSAGE_TRACKING] Agent: {agent_name} | To: {recipient} | Length: {len(message_content)} chars")
            
            logger.debug(f"💬 Tracked message from {agent_name} to {recipient}")
            
        except Exception as e:
            logger.error(f"Error tracking agent message: {e}")

    def track_message(self, agent_name: str, message_content: str, recipient: str = "unknown") -> None:
        """Alias for track_agent_message."""
        self.track_agent_message(agent_name, message_content, recipient)

    async def update_usage_from_agents(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Update usage tracking using AG2's native gather_usage_summary.
        This is the primary method for getting accurate token and cost data.
        Now includes automatic trial token deduction and persistence.
        """
        start_time = datetime.utcnow()
        
        try:
            # Use AG2's native usage gathering
            usage_summary = gather_usage_summary(agents)
            
            # Update session usage summary
            self.session_usage.ag2_usage_summary = usage_summary
            
            # Extract overall metrics
            usage_including_cache = usage_summary.get("usage_including_cached_inference", {})
            current_tokens = usage_including_cache.get("total_tokens", 0)
            current_cost = usage_including_cache.get("total_cost", 0.0)
            
            # Calculate new tokens used in this update
            tokens_delta = current_tokens - self.session_usage.total_tokens
            
            # Deduct new tokens from trial if any were used
            if tokens_delta > 0:
                deduction_result = await self.deduct_trial_tokens(tokens_delta)
                if not deduction_result["success"]:
                    logger.warning(f"Trial token deduction failed: {deduction_result['reason']}")
                    # Continue with tracking but log the issue
                else:
                    # Persist the token usage to database
                    await self._persist_token_usage(tokens_delta, deduction_result)
            
            # Update session totals
            self.session_usage.total_tokens = current_tokens
            self.session_usage.total_cost = current_cost
            
            # Log to consolidated token tracking with trial info
            trial_status = self.check_trial_status()
            token_logger.info(f"[AG2_TRACKING] Chat: {self.chat_id[:8]} | Total: {self.session_usage.total_tokens} tokens | Cost: ${self.session_usage.total_cost:.4f} | Trial remaining: {trial_status['total_available']}")
            
            # Track per-agent usage (if methods are available)
            for agent in agents:
                try:
                    agent_name = getattr(agent, 'name', 'unknown')
                    
                    if agent_name not in self.session_usage.agents:
                        self.session_usage.agents[agent_name] = AgentTokenUsage(agent_name=agent_name)
                    
                    agent_usage = self.session_usage.agents[agent_name]
                    
                    # Try to get usage data if methods exist
                    if hasattr(agent, 'get_actual_usage'):
                        actual_usage = agent.get_actual_usage()  # type: ignore
                        if actual_usage:
                            agent_usage.total_tokens = actual_usage.get("total_tokens", 0)
                            agent_usage.prompt_tokens = actual_usage.get("prompt_tokens", 0)
                            agent_usage.completion_tokens = actual_usage.get("completion_tokens", 0)
                            agent_usage.total_cost = actual_usage.get("total_cost", 0.0)
                    
                    if hasattr(agent, 'get_total_usage'):
                        total_usage = agent.get_total_usage()  # type: ignore
                        if total_usage and "usage_by_model" in total_usage:
                            agent_usage.model_usage = total_usage["usage_by_model"]
                    
                    agent_usage.last_updated = datetime.utcnow()
                    
                except Exception as e:
                    logger.debug(f"Could not get detailed usage for agent {getattr(agent, 'name', 'unknown')}: {e}")
                    # Continue processing other agents
            
            # Calculate performance metric
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.performance_metrics["token_calculation_times"].append(processing_time)
            
            log_performance_metric(
                metric_name="ag2_usage_calculation_time",
                value=processing_time,
                unit="ms",
                context={
                    "chat_id": self.chat_id,
                    "total_tokens": self.session_usage.total_tokens,
                    "total_cost": self.session_usage.total_cost,
                    "agent_count": len(agents),
                    "trial_remaining": trial_status["total_available"]
                }
            )
            
            log_business_event(
                event_type="ag2_usage_updated",
                description=f"Updated usage tracking using AG2 native methods",
                context={
                    "chat_id": self.chat_id,
                    "total_tokens": self.session_usage.total_tokens,
                    "total_cost": self.session_usage.total_cost,
                    "agents_tracked": list(self.session_usage.agents.keys()),
                    "tokens_delta": tokens_delta,
                    "trial_status": trial_status
                }
            )
            
            return usage_summary
            
        except Exception as e:
            logger.error(f"Error updating usage from agents: {e}")
            return {}

    def get_session_summary(self) -> Dict[str, Any]:
        """Get comprehensive session summary with AG2 usage data."""
        duration_seconds = (datetime.utcnow() - self.session_usage.start_time).total_seconds()
        
        return {
            "session_info": {
                "chat_id": self.chat_id,
                "session_id": self.session_id,
                "enterprise_id": self.enterprise_id,
                "duration_seconds": duration_seconds,
            },
            "usage_summary": {
                "total_tokens": self.session_usage.total_tokens,
                "total_cost": self.session_usage.total_cost,
                "message_count": len(self.session_usage.message_history),
                "agent_count": len(self.session_usage.agents)
            },
            "agent_breakdown": {
                agent_name: {
                    "total_tokens": agent.total_tokens,
                    "prompt_tokens": agent.prompt_tokens,
                    "completion_tokens": agent.completion_tokens,
                    "total_cost": agent.total_cost,
                    "message_count": agent.message_count,
                    "model_usage": agent.model_usage
                }
                for agent_name, agent in self.session_usage.agents.items()
            },
            "performance_metrics": {
                "avg_agent_response_time": (
                    sum(self.performance_metrics["agent_response_times"]) / 
                    len(self.performance_metrics["agent_response_times"])
                    if self.performance_metrics["agent_response_times"] else 0
                ),
                "avg_token_calc_time": (
                    sum(self.performance_metrics["token_calculation_times"]) / 
                    len(self.performance_metrics["token_calculation_times"])
                    if self.performance_metrics["token_calculation_times"] else 0
                )
            }
        }

    def track_agent_response_time(self, agent_name: str, response_time_ms: float) -> None:
        """Track agent response times for performance monitoring."""
        try:
            self.performance_metrics["agent_response_times"].append(response_time_ms)
            
            # Track agent-specific performance
            if agent_name not in self.agent_performance:
                self.agent_performance[agent_name] = {
                    "response_times": [],
                    "message_count": 0,
                    "total_tokens": 0,
                    "first_seen": datetime.utcnow(),
                    "last_seen": datetime.utcnow()
                }
            
            self.agent_performance[agent_name]["response_times"].append(response_time_ms)
            self.agent_performance[agent_name]["last_seen"] = datetime.utcnow()
            
            log_performance_metric(
                metric_name="agent_response_time",
                value=response_time_ms,
                unit="ms",
                context={
                    "chat_id": self.chat_id,
                    "agent_name": agent_name,
                    "session_id": self.session_id
                }
            )
            
        except Exception as e:
            logger.error(f"Error tracking agent response time: {e}")

    def track_agent_message_performance(self, agent_name: str, message_content: str, 
                                      processing_time_ms: float = 0) -> None:
        """Track agent message processing performance."""
        try:
            # Update agent performance metrics
            if agent_name not in self.agent_performance:
                self.agent_performance[agent_name] = {
                    "response_times": [],
                    "message_count": 0,
                    "total_tokens": 0,
                    "first_seen": datetime.utcnow(),
                    "last_seen": datetime.utcnow()
                }
            
            self.agent_performance[agent_name]["message_count"] += 1
            self.agent_performance[agent_name]["last_seen"] = datetime.utcnow()
            
            if processing_time_ms > 0:
                self.performance_metrics["message_processing_times"].append(processing_time_ms)
                
            # Log performance
            log_performance_metric(
                metric_name="agent_message_processing",
                value=processing_time_ms,
                unit="ms",
                context={
                    "chat_id": self.chat_id,
                    "agent_name": agent_name,
                    "message_length": len(message_content),
                    "session_id": self.session_id
                }
            )
            
        except Exception as e:
            logger.error(f"Error tracking agent message performance: {e}")

    async def persist_session_performance(self) -> bool:
        """Persist comprehensive session performance data to database"""
        try:
            # Calculate session metrics
            session_duration = (datetime.utcnow() - self.session_start_time).total_seconds()
            
            # Prepare agent-level metrics
            agent_metrics = {}
            for agent_name, perf_data in self.agent_performance.items():
                response_times = perf_data.get("response_times", [])
                avg_response_time = sum(response_times) / len(response_times) if response_times else 0
                
                # Get token data from session usage if available
                agent_usage = self.session_usage.agents.get(agent_name)
                total_tokens = agent_usage.total_tokens if agent_usage else 0
                
                agent_metrics[agent_name] = {
                    "avg_response_time_ms": round(avg_response_time, 2),
                    "message_count": perf_data.get("message_count", 0),
                    "total_tokens": total_tokens,
                    "response_time_samples": len(response_times),
                    "first_seen": perf_data.get("first_seen", self.session_start_time).isoformat(),
                    "last_seen": perf_data.get("last_seen", datetime.utcnow()).isoformat()
                }
            
            # Prepare session-level metrics
            session_metrics = {
                "session_duration_seconds": round(session_duration, 2),
                "total_messages": len(self.session_usage.message_history),
                "avg_agent_response_time_ms": round(
                    sum(self.performance_metrics["agent_response_times"]) / 
                    len(self.performance_metrics["agent_response_times"])
                    if self.performance_metrics["agent_response_times"] else 0, 2
                ),
                "avg_token_calc_time_ms": round(
                    sum(self.performance_metrics["token_calculation_times"]) / 
                    len(self.performance_metrics["token_calculation_times"])
                    if self.performance_metrics["token_calculation_times"] else 0, 2
                ),
                "avg_message_processing_time_ms": round(
                    sum(self.performance_metrics["message_processing_times"]) / 
                    len(self.performance_metrics["message_processing_times"])
                    if self.performance_metrics["message_processing_times"] else 0, 2
                ),
                "total_tokens": self.session_usage.total_tokens,
                "total_cost": self.session_usage.total_cost
            }
            
            # Persist to database
            success = await self.persistence_manager.log_performance_metrics(
                workflow_name=self.workflow_name,
                enterprise_id=self.enterprise_id,
                user_id=self.user_id,
                chat_id=self.chat_id,
                session_id=self.session_id,
                agent_metrics=agent_metrics,
                session_metrics=session_metrics
            )
            
            if success:
                logger.info(f"📊 Persisted session performance: {len(agent_metrics)} agents, {session_duration:.1f}s duration")
                
                # Log business event
                log_business_event(
                    event_type="session_performance_logged",
                    description=f"Logged performance metrics for workflow session",
                    context={
                        "workflow_name": self.workflow_name,
                        "chat_id": self.chat_id,
                        "session_duration_seconds": session_duration,
                        "agents_tracked": list(agent_metrics.keys()),
                        "total_messages": session_metrics["total_messages"],
                        "avg_response_time_ms": session_metrics["avg_agent_response_time_ms"]
                    }
                )
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to persist session performance: {e}")
            return False

    async def get_workflow_performance_comparison(self) -> Dict[str, Any]:
        """Get current session performance compared to workflow averages"""
        try:
            # Get workflow averages
            averages = await self.persistence_manager.get_workflow_performance_averages(
                workflow_name=self.workflow_name,
                enterprise_id=self.enterprise_id
            )
            
            if not averages or averages.get("session_count", 0) == 0:
                return {
                    "comparison_available": False,
                    "message": "No historical data available for comparison"
                }
            
            # Calculate current session metrics
            session_duration = (datetime.utcnow() - self.session_start_time).total_seconds()
            current_avg_response = (
                sum(self.performance_metrics["agent_response_times"]) / 
                len(self.performance_metrics["agent_response_times"])
                if self.performance_metrics["agent_response_times"] else 0
            )
            
            current_metrics = {
                "session_duration_seconds": round(session_duration, 2),
                "total_messages": len(self.session_usage.message_history),
                "avg_agent_response_time_ms": round(current_avg_response, 2),
                "total_tokens": self.session_usage.total_tokens,
                "total_cost": self.session_usage.total_cost,
                "agent_count": len(self.agent_performance)
            }
            
            # Compare with averages
            avg_perf = averages.get("performance_averages", {})
            comparison = {
                "comparison_available": True,
                "workflow_name": self.workflow_name,
                "historical_sessions": averages.get("session_count", 0),
                
                "current_session": current_metrics,
                "workflow_averages": avg_perf,
                
                "performance_vs_average": {
                    "duration_vs_avg": round(
                        ((current_metrics["session_duration_seconds"] / avg_perf.get("avg_session_duration_seconds", 1)) - 1) * 100, 1
                    ) if avg_perf.get("avg_session_duration_seconds", 0) > 0 else 0,
                    
                    "response_time_vs_avg": round(
                        ((current_metrics["avg_agent_response_time_ms"] / avg_perf.get("avg_agent_response_time_ms", 1)) - 1) * 100, 1
                    ) if avg_perf.get("avg_agent_response_time_ms", 0) > 0 else 0,
                    
                    "tokens_vs_avg": round(
                        ((current_metrics["total_tokens"] / avg_perf.get("avg_tokens_per_session", 1)) - 1) * 100, 1
                    ) if avg_perf.get("avg_tokens_per_session", 0) > 0 else 0,
                    
                    "cost_vs_avg": round(
                        ((current_metrics["total_cost"] / avg_perf.get("avg_cost_per_session", 0.001)) - 1) * 100, 1
                    ) if avg_perf.get("avg_cost_per_session", 0) > 0 else 0
                },
                
                "agent_comparisons": {}
            }
            
            # Compare agent performance
            agent_averages = averages.get("agent_averages", {})
            for agent_name, perf_data in self.agent_performance.items():
                if agent_name in agent_averages:
                    agent_avg = agent_averages[agent_name]
                    current_avg_response = (
                        sum(perf_data.get("response_times", [])) / len(perf_data.get("response_times", []))
                        if perf_data.get("response_times") else 0
                    )
                    
                    comparison["agent_comparisons"][agent_name] = {
                        "current_avg_response_ms": round(current_avg_response, 2),
                        "historical_avg_response_ms": agent_avg.get("avg_response_time_ms", 0),
                        "response_time_vs_avg": round(
                            ((current_avg_response / agent_avg.get("avg_response_time_ms", 1)) - 1) * 100, 1
                        ) if agent_avg.get("avg_response_time_ms", 0) > 0 else 0
                    }
            
            return comparison
            
        except Exception as e:
            logger.error(f"❌ Failed to get performance comparison: {e}")
            return {"comparison_available": False, "error": str(e)}

    def get_ag2_usage_for_agents(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Get current AG2 usage summary for specific agents.
        Uses AG2's native gather_usage_summary function.
        """
        try:
            return gather_usage_summary(agents)
        except Exception as e:
            logger.error(f"Error getting AG2 usage summary: {e}")
            return {}

    def reset_agent_usage(self, agents: List[Agent]) -> None:
        """Reset usage tracking for all agents using AG2's native reset method."""
        try:
            for agent in agents:
                if hasattr(agent, 'reset'):
                    agent.reset()  # type: ignore
            
            # Reset our internal tracking
            self.session_usage.agents.clear()
            self.session_usage.total_tokens = 0
            self.session_usage.total_cost = 0.0
            self.session_usage.message_history.clear()
            
            log_business_event(
                event_type="agent_usage_reset",
                description="Reset usage tracking for all agents",
                context={"chat_id": self.chat_id, "session_id": self.session_id}
            )
            
        except Exception as e:
            logger.error(f"Error resetting agent usage: {e}")

    async def get_usage_for_business_logic(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Get usage data formatted for business logic systems (like TokenManager).
        Returns usage data in a format suitable for billing and budget enforcement.
        """
        try:
            # Get raw AG2 usage data
            usage_summary = await self.update_usage_from_agents(agents)
            
            # Extract usage including cached inference for comprehensive tracking
            usage_including_cache = usage_summary.get("usage_including_cached_inference", {})
            usage_excluding_cache = usage_summary.get("usage_excluding_cached_inference", {})
            
            # Format for business logic consumption
            business_data = {
                "total_tokens": usage_excluding_cache.get("total_tokens", 0),
                "prompt_tokens": usage_excluding_cache.get("prompt_tokens", 0),
                "completion_tokens": usage_excluding_cache.get("completion_tokens", 0),
                "total_cost": usage_excluding_cache.get("total_cost", 0.0),
                "cached_tokens": (
                    usage_including_cache.get("total_tokens", 0) - 
                    usage_excluding_cache.get("total_tokens", 0)
                ),
                "models_used": list(usage_summary.get("models", {}).keys()),
                "timestamp": datetime.utcnow().isoformat(),
                "raw_ag2_summary": usage_summary  # Full data for debugging
            }
            
            return business_data
            
        except Exception as e:
            logger.error(f"Error getting usage for business logic: {e}")
            return {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_cost": 0.0,
                "cached_tokens": 0,
                "models_used": [],
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }

    async def finalize_session(self) -> Dict[str, Any]:
        """Finalize session and persist all performance data"""
        try:
            # Persist performance metrics
            performance_success = await self.persist_session_performance()
            
            # Get final session summary
            session_summary = self.get_session_summary()
            
            # Get performance comparison
            performance_comparison = await self.get_workflow_performance_comparison()
            
            # Create final summary
            final_summary = {
                "session_finalized": True,
                "performance_persisted": performance_success,
                "session_summary": session_summary,
                "performance_comparison": performance_comparison,
                "finalized_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"🏁 Session finalized for chat {self.chat_id} | Performance persisted: {performance_success}")
            
            return final_summary
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize session: {e}")
            return {
                "session_finalized": False,
                "error": str(e),
                "finalized_at": datetime.utcnow().isoformat()
            }

# ==============================================================================
# GLOBAL OBSERVER MANAGEMENT (for compatibility with existing code)
# ==============================================================================

_observers: Dict[str, TokenManager] = {}

def get_observer(chat_id: str, enterprise_id: str, user_id: str = "unknown") -> TokenManager:
    """Get or create an observability manager for a chat session."""
    key = f"{chat_id}:{enterprise_id}:{user_id}"
    if key not in _observers:
        _observers[key] = TokenManager(chat_id, enterprise_id, user_id)
    return _observers[key]

def get_token_tracker(chat_id: str, enterprise_id: str, user_id: str = "unknown") -> TokenManager:
    """Get token tracker (alias for observer)."""
    return get_observer(chat_id, enterprise_id, user_id)

def cleanup_observer(chat_id: str, enterprise_id: str, user_id: str = "unknown") -> None:
    """Clean up observer resources."""
    key = f"{chat_id}:{enterprise_id}:{user_id}"
    if key in _observers:
        del _observers[key]
