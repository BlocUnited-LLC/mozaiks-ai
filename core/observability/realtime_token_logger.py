"""Real-time token tracking using AG2's BaseLogger pattern.

This implements the AG2 team's recommended approach for real-time token/cost tracking
by extending BaseLogger and implementing log_chat_completion to capture every LLM call.
"""

import asyncio
import uuid
import datetime
from typing import Dict, Any, Optional, Union, TYPE_CHECKING
from autogen.logger.base_logger import BaseLogger
from logs.logging_config import get_workflow_logger
from core.observability.performance_manager import get_performance_manager

# Import types for proper typing
if TYPE_CHECKING:
    from openai.types.chat import ChatCompletion

logger = get_workflow_logger("realtime_tokens")

class RealtimeTokenLogger(BaseLogger):
    """Custom AG2 BaseLogger that tracks tokens/costs in real-time per LLM call.
    
    This captures every chat completion call and immediately updates our performance
    tracking, providing real-time token usage instead of waiting for UsageSummaryEvent.
    """
    
    def __init__(self):
        super().__init__()
        self._chat_id: Optional[str] = None
        self._current_agent: Optional[str] = None
        self._session_totals: Dict[str, float] = {  # Changed to float for total_cost
            "prompt_tokens": 0.0,
            "completion_tokens": 0.0,
            "total_cost": 0.0
        }
        
    def set_chat_context(self, chat_id: str, current_agent: str):
        """Set the current chat and agent context for token attribution."""
        self._chat_id = chat_id
        self._current_agent = current_agent
        
    def start(self) -> str:
        """Start a new logging session."""
        logger.debug(f"Starting realtime token logging for chat {self._chat_id}")
        return f"realtime_token_session_{self._chat_id}"
        
    def log_chat_completion(
        self,
        invocation_id: uuid.UUID,
        client_id: int,
        wrapper_id: int,
        source: Any,
        request: Dict[str, Any],
        response: Union[str, "ChatCompletion"],  # Use quoted string for forward reference
        is_cached: int,
        cost: float,
        start_time: str
    ):
        """Log each chat completion call in real-time.
        
        This is the key method that captures every LLM call immediately
        as it happens, allowing real-time token/cost tracking.
        """
        try:
            if not self._chat_id or not self._current_agent:
                logger.debug("No chat context set, skipping token logging")
                return
                
            # Extract token usage from response
            prompt_tokens = 0
            completion_tokens = 0
            
            if isinstance(response, dict):
                usage = response.get("usage", {})
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    
            # Update session totals
            self._session_totals["prompt_tokens"] += prompt_tokens
            self._session_totals["completion_tokens"] += completion_tokens  
            self._session_totals["total_cost"] += cost
            
            # Log the real-time usage
            logger.info(
                f"🪙 [REALTIME] Agent={self._current_agent} "
                f"prompt={prompt_tokens} completion={completion_tokens} "
                f"cost=${cost:.6f} session_total=${self._session_totals['total_cost']:.6f}"
            )
            
            # Record to performance manager immediately
            if prompt_tokens > 0 or completion_tokens > 0 or cost > 0:
                # Run async task to record the turn
                asyncio.create_task(self._record_realtime_turn(
                    prompt_tokens, completion_tokens, cost
                ))
                
        except Exception as e:
            logger.warning(f"Failed to log chat completion in real-time: {e}")
            
    async def _record_realtime_turn(self, prompt_tokens: int, completion_tokens: int, cost: float):
        """Record the token usage immediately to performance manager."""
        try:
            if not self._chat_id or not self._current_agent:
                return
                
            perf_mgr = await get_performance_manager()
            await perf_mgr.record_agent_turn(
                chat_id=self._chat_id,
                agent_name=self._current_agent,
                duration_sec=0.0,  # Duration handled separately in orchestration
                model=None,  # Could extract from request if needed
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost
            )
        except Exception as e:
            logger.warning(f"Failed to record realtime turn to performance manager: {e}")
            
    async def _write_session_totals_to_mongo(self, chat_id: str, totals: Dict[str, float]):
        """Write session totals to MongoDB asynchronously."""
        try:
            from core.core_config import get_mongo_client
            client = get_mongo_client()
            coll = client["MozaiksAI"]["RealtimeTokenSessions"]
            
            doc = {
                "_id": f"session_{chat_id}",
                "chat_id": chat_id,
                "prompt_tokens": int(totals["prompt_tokens"]),
                "completion_tokens": int(totals["completion_tokens"]),
                "total_cost": float(totals["total_cost"]),
                "updated_ts": datetime.datetime.utcnow()
            }
            
            await coll.update_one(
                {"_id": doc["_id"]}, 
                {"$set": doc}, 
                upsert=True
            )
            logger.debug(f"Persisted session totals to MongoDB for chat {chat_id}")
            
        except Exception as e:
            logger.warning(f"Failed to persist session totals to MongoDB: {e}")
            
    def stop(self):
        """Stop the logging session and save totals."""
        try:
            if self._chat_id and self._session_totals["total_cost"] > 0:
                logger.info(
                    f"📊 [SESSION_TOTALS] Chat={self._chat_id} "
                    f"prompt_tokens={int(self._session_totals['prompt_tokens'])} "
                    f"completion_tokens={int(self._session_totals['completion_tokens'])} "
                    f"total_cost=${self._session_totals['total_cost']:.6f}"
                )
                
                # Persist session totals to MongoDB (non-blocking)
                asyncio.create_task(self._write_session_totals_to_mongo(
                    self._chat_id, 
                    self._session_totals.copy()
                ))
                
        except Exception as e:
            logger.warning(f"Failed to log session totals: {e}")
            
    def log_new_agent(self, agent: Any, init_args: Dict[str, Any]):
        """Track when new agents are created."""
        agent_name = getattr(agent, 'name', str(agent))
        logger.debug(f"New agent logged: {agent_name}")
        
    def log_event(self, source: Any, name: str, **kwargs):
        """Log other AG2 events."""
        # We can add additional event tracking here if needed
        pass
        
    def log_new_wrapper(self, wrapper: Any, init_args: Dict[str, Any]):
        """Log new LLM wrapper creation."""
        pass
        
    def log_new_client(self, client: Any, wrapper: Any, init_args: Dict[str, Any]):
        """Log new client creation.""" 
        pass
        
    def log_function_use(self, source: Any, function: Any, args: Dict[str, Any], returns: Any):
        """Log function usage (required by BaseLogger)."""
        # Optional: Track tool usage if needed
        pass
        
    def get_connection(self) -> Optional[Any]:
        """Return database connection (required by BaseLogger)."""
        # We don't use SQLite, return None
        return None

# Global instance for easy access
_realtime_logger: Optional[RealtimeTokenLogger] = None

def get_realtime_token_logger() -> RealtimeTokenLogger:
    """Get the global realtime token logger instance."""
    global _realtime_logger
    if _realtime_logger is None:
        _realtime_logger = RealtimeTokenLogger()
    return _realtime_logger

def start_realtime_tracking(chat_id: str, current_agent: str) -> str:
    """Start real-time token tracking for a chat session."""
    logger_instance = get_realtime_token_logger()
    logger_instance.set_chat_context(chat_id, current_agent)
    return logger_instance.start()
    
def stop_realtime_tracking():
    """Stop real-time token tracking."""
    logger_instance = get_realtime_token_logger()
    logger_instance.stop()