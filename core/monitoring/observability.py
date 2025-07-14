# =============================================================================
# FILE: core/observability.py
# DESCRIPTION: AG2-native observability, token tracking, and cost monitoring
#              Uses AG2's built-in gather_usage_summary, CompletionUsage, and
#              runtime logging instead of external tools like OpenLIT
# =============================================================================

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# AG2 imports for native usage tracking and logging
import autogen
from autogen import Agent, gather_usage_summary

from logs.logging_config import get_business_logger, get_performance_logger, get_token_manager_logger, log_business_event, log_performance_metric

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

class AG2ObservabilityManager:
    """
    Centralized observability manager using AG2's native features.
    Provides token tracking, cost monitoring, and performance metrics
    using autogen.gather_usage_summary and related AG2 APIs.
    """

    def __init__(self, chat_id: str, enterprise_id: str):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.session_id = str(uuid.uuid4())
        
        # Initialize usage tracking
        self.session_usage = ChatSessionUsage(
            chat_id=chat_id,
            session_id=self.session_id,
            enterprise_id=enterprise_id
        )
        
        # AG2 runtime logging session
        self.ag2_logging_session_id: Optional[str] = None
        
        # Performance tracking
        self.performance_metrics: Dict[str, List[float]] = {
            "agent_response_times": [],
            "message_processing_times": [],
            "token_calculation_times": []
        }
        
        logger.info(f"🔍 AG2 Observability Manager initialized for chat {chat_id}")

    def start_ag2_logging(self, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Start AG2's native runtime logging (currently disabled due to serialization issues)."""
        try:
            if config is None:
                # Default to SQLite logging with chat-specific database
                config = {"dbname": f"ag2_logs_{self.chat_id}.db"}
            
            # Temporarily disable AG2 runtime logging due to JSON serialization issues
            # This will be re-enabled once AG2 fixes the ModelMetaclass serialization
            logger.info("AG2 runtime logging temporarily disabled due to serialization issues")
            self.ag2_logging_session_id = f"disabled_session_{uuid.uuid4()}"
            
            # Start AG2 runtime logging if available (DISABLED)
            # if hasattr(autogen, 'runtime_logging'):
            #     session_id = autogen.runtime_logging.start(config=config)  # type: ignore
            #     self.ag2_logging_session_id = session_id
            # else:
            #     logger.warning("AG2 runtime_logging not available in this version")
            #     self.ag2_logging_session_id = f"manual_session_{uuid.uuid4()}"
            
            log_business_event(
                event_type="ag2_logging_started",
                description=f"AG2 runtime logging started for chat {self.chat_id}",
                context={
                    "chat_id": self.chat_id,
                    "session_id": self.ag2_logging_session_id,
                    "config": config
                }
            )
            
            logger.info(f"📊 AG2 runtime logging started: {self.ag2_logging_session_id}")
            return self.ag2_logging_session_id
            
        except Exception as e:
            logger.error(f"Failed to start AG2 logging: {e}")
            raise

    def stop_ag2_logging(self) -> None:
        """Stop AG2's native runtime logging (currently disabled)."""
        try:
            if self.ag2_logging_session_id and "disabled_session" not in self.ag2_logging_session_id:
                if hasattr(autogen, 'runtime_logging'):
                    autogen.runtime_logging.stop()  # type: ignore
                logger.info("AG2 runtime logging stopped")
            elif self.ag2_logging_session_id:
                logger.info("AG2 runtime logging was disabled, no stop needed")
                
            log_business_event(
                event_type="ag2_logging_stopped",
                description=f"AG2 runtime logging stopped for chat {self.chat_id}",
                context={
                    "chat_id": self.chat_id,
                    "session_id": self.ag2_logging_session_id
                }
            )
            
            logger.info(f"📊 AG2 runtime logging stopped: {self.ag2_logging_session_id}")
            self.ag2_logging_session_id = None
                
        except Exception as e:
            logger.error(f"Failed to stop AG2 logging: {e}")

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
            
            # Update agent message count
            if agent_name not in self.session_usage.agents:
                self.session_usage.agents[agent_name] = AgentTokenUsage(agent_name=agent_name)
            
            self.session_usage.agents[agent_name].message_count += 1
            self.session_usage.agents[agent_name].last_updated = datetime.utcnow()
            
            # Log message tracking to consolidated token log
            token_logger.debug(f"[MESSAGE_TRACKING] Agent: {agent_name} | To: {recipient} | Length: {len(message_content)} chars")
            
            logger.debug(f"💬 Tracked message from {agent_name} to {recipient}")
            
        except Exception as e:
            logger.error(f"Error tracking agent message: {e}")

    def track_message(self, agent_name: str, message_content: str, recipient: str = "unknown") -> None:
        """Alias for track_agent_message."""
        self.track_agent_message(agent_name, message_content, recipient)

    def update_usage_from_agents(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Update usage tracking using AG2's native gather_usage_summary.
        This is the primary method for getting accurate token and cost data.
        """
        start_time = datetime.utcnow()
        
        try:
            # Use AG2's native usage gathering
            usage_summary = gather_usage_summary(agents)
            
            # Update session usage summary
            self.session_usage.ag2_usage_summary = usage_summary
            
            # Extract overall metrics
            usage_including_cache = usage_summary.get("usage_including_cached_inference", {})
            self.session_usage.total_tokens = usage_including_cache.get("total_tokens", 0)
            self.session_usage.total_cost = usage_including_cache.get("total_cost", 0.0)
            
            # Log to consolidated token tracking
            token_logger.info(f"[AG2_TRACKING] Chat: {self.chat_id[:8]} | Total: {self.session_usage.total_tokens} tokens | Cost: ${self.session_usage.total_cost:.4f}")
            
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
                    "agent_count": len(agents)
                }
            )
            
            log_business_event(
                event_type="ag2_usage_updated",
                description=f"Updated usage tracking using AG2 native methods",
                context={
                    "chat_id": self.chat_id,
                    "total_tokens": self.session_usage.total_tokens,
                    "total_cost": self.session_usage.total_cost,
                    "agents_tracked": list(self.session_usage.agents.keys())
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
                "ag2_logging_session": self.ag2_logging_session_id
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
            "ag2_native_summary": self.session_usage.ag2_usage_summary,
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

    def get_usage_for_business_logic(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Get usage data formatted for business logic systems (like TokenManager).
        Returns usage data in a format suitable for billing and budget enforcement.
        """
        try:
            # Get raw AG2 usage data
            usage_summary = self.update_usage_from_agents(agents)
            
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

# Global instances
_observers: Dict[str, AG2ObservabilityManager] = {}

def get_observer(chat_id: str, enterprise_id: str) -> AG2ObservabilityManager:
    """Get or create an observability manager for a chat session."""
    key = f"{chat_id}:{enterprise_id}"
    if key not in _observers:
        _observers[key] = AG2ObservabilityManager(chat_id, enterprise_id)
    return _observers[key]

def get_token_tracker(chat_id: str, enterprise_id: str, user_id: str = "unknown") -> AG2ObservabilityManager:
    """Get token tracker (alias for observer)."""
    # user_id parameter kept for compatibility but not used in current implementation
    return get_observer(chat_id, enterprise_id)

def cleanup_observer(chat_id: str, enterprise_id: str) -> None:
    """Clean up observer resources."""
    key = f"{chat_id}:{enterprise_id}"
    if key in _observers:
        observer = _observers[key]
        try:
            observer.stop_ag2_logging()
        except Exception as e:
            logger.error(f"Error stopping AG2 logging during cleanup: {e}")
        del _observers[key]
