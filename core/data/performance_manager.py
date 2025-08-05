"""
PERFORMANCE MANAGER: Business Intelligence & Resource Tracking
Handles token usage, cost tracking, and workflow performance metrics.

Role in Architecture:
- PersistenceManager: Stores WHAT happened (messages, sessions, state)
- PerformanceManager: Tracks HOW MUCH it cost (tokens, $$$, efficiency) 
- OpenLitObservability: Monitors HOW WELL it performed (speed, errors, health)

This integrates with PersistenceManager for data storage but focuses specifically
on business intelligence, cost tracking, and resource usage metrics.
"""
import asyncio
import uuid
import time
from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Any, Optional, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

# AG2 imports
from autogen import Agent, gather_usage_summary

# Core imports
from core.data.persistence_manager import PersistenceManager

from core.core_config import get_mongo_client
from logs.logging_config import get_business_logger, log_business_event

logger = get_business_logger("performance_manager")

@dataclass
class BusinessPerformanceData:
    """Business intelligence data structure for workflow performance tracking"""
    # Session info
    chat_id: str = ""
    enterprise_id: str = ""
    user_id: str = ""
    workflow_name: str = ""
    
    # Timing
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    # Token data (maps to real_time_tracking.tokens)
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    
    # Performance data (maps to real_time_tracking.performance)
    agent_count: int = 0
    operation_count: int = 0
    avg_response_time_ms: float = 0.0
    
    # Status
    success: bool = True
    completion_status: str = "running"


class BusinessPerformanceManager:
    """
    BUSINESS INTELLIGENCE: Token usage, cost tracking, and workflow performance metrics.
    
    Role in Architecture:
    - Focuses on business metrics: tokens, costs, efficiency, ROI
    - Integrates with PersistenceManager for data storage
    - Provides business intelligence for resource usage optimization
    - Works alongside OpenLitObservability (technical metrics) and PersistenceManager (data storage)
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str, workflow_name: str):
        
        self.data = BusinessPerformanceData(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_name=workflow_name
        )
        
        # Use enhanced PersistenceManager instead of direct MongoDB
        from core.data.persistence_manager import PersistenceManager
        self.persistence = PersistenceManager()
        
        logger.info(f"🔗 Business performance manager initialized: {workflow_name} | Tracks costs & metrics")

    async def update_from_agents(self, agents: List[Agent]) -> Dict[str, Any]:
        """Update tracking data directly in ChatSessions.real_time_tracking"""
        try:
            total_tokens = 0
            total_cost = 0.0
            prompt_tokens = 0
            completion_tokens = 0
            
            # Try AG2's gather_usage_summary first (for real agents)
            try:
                usage_summary = gather_usage_summary(agents)
                
                if usage_summary:
                    # Extract token data from AG2 format
                    usage_data = usage_summary.get("usage_including_cached_inference", {})
                    if usage_data:
                        total_cost = usage_data.get("total_cost", 0)
                        
                        # Calculate totals
                        total_tokens = sum(model.get("total_tokens", 0) for model in usage_data.values() if isinstance(model, dict))
                        prompt_tokens = sum(model.get("prompt_tokens", 0) for model in usage_data.values() if isinstance(model, dict))
                        completion_tokens = sum(model.get("completion_tokens", 0) for model in usage_data.values() if isinstance(model, dict))
                        
            except Exception as ag2_error:
                # Fall back to manual extraction (for mock agents or when AG2 fails)
                logger.debug(f"AG2 extraction failed, using manual: {ag2_error}")
                
                for agent in agents:
                    try:
                        # Try different attribute patterns (use getattr for type safety)
                        client_usage = None
                        client = getattr(agent, 'client', None)
                        if client:
                            client_usage = getattr(client, 'total_usage_summary', None) or getattr(client, 'usage_summary', None)
                        
                        if client_usage and isinstance(client_usage, dict):
                            total_tokens += client_usage.get("total_tokens", 0)
                            total_cost += client_usage.get("total_cost", 0.0)
                            prompt_tokens += client_usage.get("prompt_tokens", 0)
                            completion_tokens += client_usage.get("completion_tokens", 0)
                    except Exception as agent_error:
                        logger.debug(f"Could not extract from agent {getattr(agent, 'name', 'unknown')}: {agent_error}")
            
            # Update local data
            self.data.total_tokens = total_tokens
            self.data.prompt_tokens = prompt_tokens
            self.data.completion_tokens = completion_tokens
            self.data.total_cost = total_cost
            self.data.agent_count = len(agents)
            self.data.operation_count += 1
            
            # Update ChatSessions.real_time_tracking directly (no separate collection!)
            tracking_update = {
                "tokens": {
                    "total_tokens": total_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_cost": total_cost,
                    "cumulative_tokens": self.data.total_tokens,
                    "cumulative_cost": self.data.total_cost
                },
                "performance": {
                    "agent_count": len(agents),
                    "operation_count": self.data.operation_count
                }
            }
            
            await self.persistence.update_real_time_tracking(
                self.data.chat_id,
                self.data.enterprise_id,
                tracking_update
            )
            
            logger.info(f"📊 Updated ChatSessions directly: {total_tokens} tokens, ${total_cost:.6f}")
            
            return {"success": True, "tokens": total_tokens, "cost": total_cost}
            
        except Exception as e:
            logger.error(f"❌ Update failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_summary(self) -> Dict[str, Any]:
        """Get current summary from ChatSessions.real_time_tracking"""
        try:
            tracking_data = await self.persistence.get_real_time_tracking(
                self.data.chat_id,
                self.data.enterprise_id
            )
            
            if tracking_data:
                duration_ms = (datetime.utcnow() - tracking_data.get("start_time", datetime.utcnow())).total_seconds() * 1000
                
                return {
                    "session_id": tracking_data.get("session_id"),
                    "workflow_name": self.data.workflow_name,
                    "duration_ms": duration_ms,
                    "total_tokens": tracking_data.get("tokens", {}).get("total_tokens", 0),
                    "total_cost": tracking_data.get("tokens", {}).get("total_cost", 0.0),
                    "agent_count": tracking_data.get("performance", {}).get("agent_count", 0),
                    "success": tracking_data.get("current_status") != "failed"
                }
            else:
                # Fallback to local data
                duration_ms = (datetime.utcnow() - self.data.start_time).total_seconds() * 1000
                return {
                    "session_id": f"local_{self.data.chat_id}",
                    "workflow_name": self.data.workflow_name,
                    "duration_ms": duration_ms,
                    "total_tokens": self.data.total_tokens,
                    "total_cost": self.data.total_cost,
                    "agent_count": self.data.agent_count,
                    "success": self.data.success
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to get summary: {e}")
            return {"success": False, "error": str(e)}

    async def finalize(self, success: bool = True) -> str:
        """Finalize tracking in ChatSessions and return session ID"""
        try:
            self.data.end_time = datetime.utcnow()
            self.data.success = success
            self.data.completion_status = "completed" if success else "failed"
            
            # Update final status in ChatSessions.real_time_tracking
            await self.persistence.update_real_time_tracking(
                self.data.chat_id,
                self.data.enterprise_id,
                {"status": self.data.completion_status}
            )
            
            # Finalize the tracking session
            session_id = await self.persistence.finalize_real_time_tracking(
                self.data.chat_id,
                self.data.enterprise_id,
                success
            )
            
            logger.info(f"✅ Finalized tracking in ChatSessions: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"❌ Finalization failed: {e}")
            raise

# Simple context manager
@asynccontextmanager
async def performance_tracking_context(chat_id: str, enterprise_id: str, user_id: str, workflow_name: str):
    """
    Business performance tracking context manager.
    Tracks token usage, costs, and business metrics for workflow optimization.
    """
    tracker = BusinessPerformanceManager(chat_id, enterprise_id, user_id, workflow_name)
    
    # Log workflow start
    log_business_event(
        log_event_type="WORKFLOW_STARTED",
        description=f"Started {workflow_name} workflow",
        context={"chat_id": chat_id}
    )
    
    try:
        yield tracker
    except Exception as e:
        logger.error(f"❌ Workflow failed: {e}")
        await tracker.finalize(success=False)
        raise
    else:
        await tracker.finalize(success=True)
        
        # Log completion
        summary = await tracker.get_summary()
        log_business_event(
            log_event_type="WORKFLOW_COMPLETED", 
            description=f"Completed {workflow_name} workflow",
            context={
                "chat_id": chat_id,
                "tokens": summary.get("total_tokens", 0),
                "cost": summary.get("total_cost", 0.0)
            }
        )


# Factory function
def create_performance_manager(chat_id: str, enterprise_id: str, user_id: str, workflow_name: str) -> BusinessPerformanceManager:
    """Create business performance manager instance for tracking workflow costs and metrics"""
    return BusinessPerformanceManager(chat_id, enterprise_id, user_id, workflow_name)

