"""
TokenManager using consolidated 3-collection database design
Replaces complex multi-collection queries with simple single-document operations
"""
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
token_logger = get_token_manager_logger("observability")
logger = logging.getLogger(__name__)

@dataclass
class AgentTokenUsage:
    """Track token usage for individual agents using AG2's CompletionUsage structure."""
    agent_name: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0
    model_usage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    message_count: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)

@dataclass
class SessionUsage:
    """Session usage tracking with embedded analytics."""
    chat_id: str
    session_id: str
    enterprise_id: str
    user_id: str
    workflow_name: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    
    # Agent tracking
    agents: Dict[str, AgentTokenUsage] = field(default_factory=dict)
    
    # Session totals (automatically calculated from agents)
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    
    # Performance metrics (embedded)
    session_duration_ms: int = 0
    avg_response_time_ms: float = 0.0
    response_times: List[float] = field(default_factory=list)
    
    # Status
    is_complete: bool = False
    connection_state: str = "active"

class TokenManager:
    """
    Optimized TokenManager using 3-collection database design
    - Single ChatSessions document per conversation
    - Embedded token, performance, and analytics data
    - Much simpler queries and better performance
    """

    def __init__(self, chat_id: str, enterprise_id: str, user_id: str, workflow_name: str = "default"):
        """Initialize with optimized session tracking"""
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_name = workflow_name
        self.session_id = str(uuid.uuid4())
        
        # Use optimized persistence manager
        self.persistence = PersistenceManager()
        
        # Optimized session usage tracking
        self.session_usage = SessionUsage(
            chat_id=chat_id,
            session_id=self.session_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            workflow_name=workflow_name
        )
        
        # Performance tracking
        self.start_time = datetime.utcnow()
        
        logger.info(f"🔍 TokenManager initialized for chat {chat_id} | User: {user_id} | Workflow: {workflow_name}")

    async def initialize_async(self):
        """Initialize async components and create session document"""
        try:
            # Create consolidated session document
            await self.persistence.create_chat_session(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                user_id=self.user_id,
                workflow_name=self.workflow_name
            )
            
            logger.info(f"✅ Created optimized session document for {self.chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize optimized session: {e}")

    async def update_usage_from_agents(self, agents: List[Agent]) -> Dict[str, Any]:
        """
        Update token usage from AG2 agents using optimized single-document approach
        """
        try:
            start_time = datetime.utcnow()
            
            # Use AG2's native usage gathering
            usage_summary = gather_usage_summary(agents)
            
            if not usage_summary:
                logger.warning("⚠️ No usage summary available from agents")
                return {}
            
            # Extract data from AG2 usage summary - prefer including cached, fallback to excluding
            usage_data = usage_summary.get("usage_including_cached_inference", {})
            if not usage_data or usage_data.get("total_cost", 0) == 0:
                usage_data = usage_summary.get("usage_excluding_cached_inference", {})
            
            logger.debug(f"🔍 Using usage data: {usage_data}")
            
            # Build agent breakdown for optimized storage
            agent_breakdown = {}
            session_totals = {
                "total_tokens": 0,
                "prompt_tokens": 0, 
                "completion_tokens": 0,
                "total_cost": 0.0
            }
            
            # First, try to extract from the summary-level usage data
            if usage_data and usage_data.get("total_cost", 0) > 0:
                total_cost = usage_data.get("total_cost", 0)
                
                # Extract model-specific data from summary
                models_data = {k: v for k, v in usage_data.items() if k != "total_cost"}
                
                if models_data:
                    # Calculate totals from summary data
                    total_tokens = sum(model.get("total_tokens", 0) for model in models_data.values())
                    prompt_tokens = sum(model.get("prompt_tokens", 0) for model in models_data.values())
                    completion_tokens = sum(model.get("completion_tokens", 0) for model in models_data.values())
                    
                    # Update session totals
                    session_totals.update({
                        "total_tokens": total_tokens,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_cost": total_cost
                    })
                    
                    # Create aggregated breakdown by distributing across agents
                    for i, agent in enumerate(agents):
                        agent_breakdown[agent.name] = {
                            "total_tokens": total_tokens // len(agents) + (total_tokens % len(agents) if i == 0 else 0),
                            "prompt_tokens": prompt_tokens // len(agents) + (prompt_tokens % len(agents) if i == 0 else 0),
                            "completion_tokens": completion_tokens // len(agents) + (completion_tokens % len(agents) if i == 0 else 0),
                            "total_cost": total_cost / len(agents),
                            "models": models_data
                        }
                        
                        # Update local session tracking
                        if agent.name not in self.session_usage.agents:
                            self.session_usage.agents[agent.name] = AgentTokenUsage(agent_name=agent.name)
                        
                        agent_usage_obj = self.session_usage.agents[agent.name]
                        agent_usage_obj.total_tokens = agent_breakdown[agent.name]["total_tokens"]
                        agent_usage_obj.prompt_tokens = agent_breakdown[agent.name]["prompt_tokens"]
                        agent_usage_obj.completion_tokens = agent_breakdown[agent.name]["completion_tokens"]
                        agent_usage_obj.total_cost = agent_breakdown[agent.name]["total_cost"]
                        agent_usage_obj.model_usage = models_data
                        agent_usage_obj.last_updated = datetime.utcnow()
            
            # Only try individual agent processing if we didn't get summary data
            if not agent_breakdown:
                logger.debug("🔍 No summary data found, trying individual agent usage...")
                # Process individual agent usage as fallback
                for agent in agents:
                    # Type check for AG2 ConversableAgent methods
                    if hasattr(agent, 'get_actual_usage'):
                        agent_usage = agent.get_actual_usage()  # type: ignore
                    else:
                        continue
                        
                    if agent_usage and agent_usage.get("total_cost", 0) > 0:
                        
                        # Extract agent-specific data
                        agent_total_cost = agent_usage.get("total_cost", 0)
                        agent_models = {k: v for k, v in agent_usage.items() if k != "total_cost"}
                        
                        # Calculate agent totals
                        agent_total_tokens = sum(model.get("total_tokens", 0) for model in agent_models.values())
                        agent_prompt_tokens = sum(model.get("prompt_tokens", 0) for model in agent_models.values())
                        agent_completion_tokens = sum(model.get("completion_tokens", 0) for model in agent_models.values())
                        
                        # Store in agent breakdown
                        agent_breakdown[agent.name] = {
                            "total_tokens": agent_total_tokens,
                            "prompt_tokens": agent_prompt_tokens,
                            "completion_tokens": agent_completion_tokens,
                            "total_cost": agent_total_cost,
                            "models": agent_models
                        }
                        
                        # Add to session totals
                        session_totals["total_tokens"] += agent_total_tokens
                        session_totals["prompt_tokens"] += agent_prompt_tokens
                        session_totals["completion_tokens"] += agent_completion_tokens
                        session_totals["total_cost"] += agent_total_cost
                        
                        # Update local session tracking
                        if agent.name not in self.session_usage.agents:
                            self.session_usage.agents[agent.name] = AgentTokenUsage(agent_name=agent.name)
                        
                        agent_usage_obj = self.session_usage.agents[agent.name]
                        agent_usage_obj.total_tokens = agent_total_tokens
                        agent_usage_obj.prompt_tokens = agent_prompt_tokens
                        agent_usage_obj.completion_tokens = agent_completion_tokens
                        agent_usage_obj.total_cost = agent_total_cost
                        agent_usage_obj.model_usage = agent_models
                        agent_usage_obj.last_updated = datetime.utcnow()
            
            # Update session totals
            self.session_usage.total_tokens = session_totals["total_tokens"]
            self.session_usage.total_prompt_tokens = session_totals["prompt_tokens"]
            self.session_usage.total_completion_tokens = session_totals["completion_tokens"]
            self.session_usage.total_cost = session_totals["total_cost"]
            
            # Single optimized database update
            await self.persistence.update_session_tokens(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                agent_breakdown=agent_breakdown
            )
            
            # Update user token balances (embedded in enterprise document)
            if session_totals["total_tokens"] > 0:
                await self.persistence.update_user_tokens(
                    user_id=self.user_id,
                    enterprise_id=self.enterprise_id,
                    tokens_used=session_totals["total_tokens"],
                    cost=session_totals["total_cost"]
                )
            
            # Log performance
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            try:
                log_performance_metric(
                    metric_name="token_update_time_ms",
                    value=processing_time,
                    unit="ms",
                    context={"chat_id": self.chat_id, "workflow": self.workflow_name}
                )
            except Exception:
                # Fallback if log_performance_metric signature is different
                logger.info(f"⏱️ Token update processing time: {processing_time:.2f}ms")
            
            logger.info(f"💾 Updated optimized session: {session_totals['total_tokens']} tokens, ${session_totals['total_cost']:.6f}")
            
            return {
                "success": True,
                "session_totals": session_totals,
                "agent_breakdown": agent_breakdown,
                "processing_time_ms": processing_time
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to update usage from agents: {e}")
            return {"success": False, "error": str(e)}

    def get_session_summary(self) -> Dict[str, Any]:
        """Get comprehensive session summary from optimized storage"""
        duration_seconds = (datetime.utcnow() - self.session_usage.start_time).total_seconds()
        
        return {
            "session_info": {
                "chat_id": self.chat_id,
                "session_id": self.session_id,
                "enterprise_id": self.enterprise_id,
                "user_id": self.user_id,
                "workflow_name": self.workflow_name,
                "duration_seconds": duration_seconds,
            },
            "usage_summary": {
                "total_tokens": self.session_usage.total_tokens,
                "prompt_tokens": self.session_usage.total_prompt_tokens,
                "completion_tokens": self.session_usage.total_completion_tokens,
                "total_cost": self.session_usage.total_cost,
                "agent_count": len(self.session_usage.agents)
            },
            "agent_breakdown": {
                agent_name: {
                    "total_tokens": agent.total_tokens,
                    "prompt_tokens": agent.prompt_tokens,
                    "completion_tokens": agent.completion_tokens,
                    "total_cost": agent.total_cost,
                    "model_usage": agent.model_usage
                }
                for agent_name, agent in self.session_usage.agents.items()
            },
            "performance_metrics": {
                "session_duration_ms": self.session_usage.session_duration_ms,
                "avg_response_time_ms": self.session_usage.avg_response_time_ms
            }
        }

    async def finalize_session(self) -> Dict[str, Any]:
        """Finalize session and update workflow statistics with enhanced workflow management"""
        try:
            # Calculate final session metrics
            final_duration_ms = (datetime.utcnow() - self.session_usage.start_time).total_seconds() * 1000
            self.session_usage.session_duration_ms = int(final_duration_ms)
            self.session_usage.is_complete = True
            
            # Prepare session data for workflow stats
            session_data = {
                "total_tokens": self.session_usage.total_tokens,
                "total_cost": self.session_usage.total_cost,
                "duration_ms": final_duration_ms,
                "agent_count": len(self.session_usage.agents)
            }
            
            # Update workflow statistics (embedded in enterprise document)
            await self.persistence.update_workflow_stats(
                enterprise_id=self.enterprise_id,
                workflow_name=self.workflow_name,
                session_data=session_data
            )
            
            # Finalize the conversation with VE-style completion status
            await self.persistence.finalize_conversation(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                final_status=100,  # VE-style completion status
                workflow_name=self.workflow_name
            )
            
            logger.info(f"✅ Finalized session {self.chat_id} ({self.workflow_name}): "
                       f"{self.session_usage.total_tokens} tokens, "
                       f"${self.session_usage.total_cost:.6f}, "
                       f"{final_duration_ms:.0f}ms")
            
            return self.get_session_summary()
            
        except Exception as e:
            logger.error(f"❌ Failed to finalize session: {e}")
            return {}

    async def add_message(self, sender: str, content: str, tokens_used: int = 0, cost: float = 0.0):
        """Add message to consolidated session document with workflow support"""
        await self.persistence.update_conversation(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            sender=sender,
            content=content,
            workflow_name=self.workflow_name
        )

    # ==================================================================================
    # WORKFLOW MANAGEMENT INTEGRATION (VE Style)
    # ==================================================================================
    
    async def update_workflow_status(self, status: int) -> bool:
        """Update workflow status for current session"""
        return await self.persistence.update_workflow_status(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            status=status,
            workflow_name=self.workflow_name
        )
    
    async def get_workflow_status(self) -> int:
        """Get current workflow status"""
        return await self.persistence.get_workflow_status(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            workflow_name=self.workflow_name
        ) or 0
    
    async def save_workflow_state(self, state_data: Dict[str, Any]) -> bool:
        """Save workflow state for resume capability"""
        return await self.persistence.save_chat_state(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            state_data=state_data,
            workflow_name=self.workflow_name
        )
    
    async def can_resume_workflow(self) -> bool:
        """Check if workflow can be resumed"""
        return await self.persistence.can_resume_chat(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            workflow_name=self.workflow_name
        )
    
    async def resume_workflow(self) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Resume workflow if possible"""
        return await self.persistence.resume_chat(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            workflow_name=self.workflow_name
        )
    
    async def get_chat_history(self, include_last: bool = True) -> List[Dict[str, Any]]:
        """Get chat history for current workflow"""
        return await self.persistence.send_chat_history(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            workflow_name=self.workflow_name,
            include_last=include_last
        )
    
    async def mark_connection_state(self, state: str, connection_info: Optional[Dict[str, Any]] = None) -> bool:
        """Mark connection state for AG2 iostream integration"""
        return await self.persistence.mark_connection_state(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            state=state,
            transport_type="ag2_websocket",
            connection_info=connection_info
        )
    
    async def handle_disconnection(self, connection_info: Optional[Dict[str, Any]] = None) -> bool:
        """Handle client disconnection"""
        return await self.persistence.handle_disconnection(
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            connection_info=connection_info
        )

    async def get_user_token_balance(self) -> Dict[str, Any]:
        """Get user token balance from embedded enterprise data"""
        return await self.persistence.get_user_tokens(
            user_id=self.user_id,
            enterprise_id=self.enterprise_id
        )

    # Compatibility methods for existing workflows
    def track_agent_message(self, agent_name: str, message_content: str, recipient: str = "unknown", message_type: str = "response") -> None:
        """
        Track agent message for backward compatibility
        In optimized version, messages are tracked via add_message()
        """
        import asyncio
        
        # Calculate basic metrics
        tokens_estimate = len(message_content.split()) * 1.3  # Rough estimate
        
        # Track message asynchronously
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self.add_message(
                sender=agent_name,
                content=message_content,
                tokens_used=int(tokens_estimate),
                cost=0.0
            ))
        except Exception as e:
            logger.warning(f"Failed to track agent message: {e}")

    def track_message(self, agent_name: str, message_content: str, recipient: str = "unknown") -> None:
        """Backward compatibility alias for track_agent_message"""
        self.track_agent_message(agent_name, message_content, recipient)

    def track_agent_start(self, agent_name: str) -> None:
        """
        Track agent start for backward compatibility
        In optimized version, this is handled automatically
        """
        logger.debug(f"Agent {agent_name} started (tracked in optimized mode)")

    def track_agent_response_time(self, agent_name: str, response_time_ms: float) -> None:
        """
        Track agent response time for backward compatibility
        In optimized version, this is embedded in session metrics
        """
        self.session_usage.response_times.append(response_time_ms)
        if self.session_usage.response_times:
            self.session_usage.avg_response_time_ms = sum(self.session_usage.response_times) / len(self.session_usage.response_times)

    def track_agent_message_performance(self, agent_name: str, message_content: str, 
                                       response_time_ms: float = 0.0, tokens_used: int = 0, 
                                       cost: float = 0.0) -> None:
        """
        Track agent message performance for backward compatibility
        """
        # Track message
        self.track_agent_message(agent_name, message_content)
        
        # Track performance
        if response_time_ms > 0:
            self.track_agent_response_time(agent_name, response_time_ms)

# Convenience functions for backward compatibility
def get_observer(chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default") -> TokenManager:
    """Create token manager instance"""
    return TokenManager(chat_id, enterprise_id, user_id, workflow_name)

def get_token_tracker(chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default") -> TokenManager:
    """Create token tracker instance"""
    return TokenManager(chat_id, enterprise_id, user_id, workflow_name)
