# ==============================================================================
# FILE: core/workflow/orchestration_patterns.py
# DESCRIPTION: AG2-compliant orchestration patterns for MozaiksAI workflows
# ==============================================================================

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging

from autogen import ConversableAgent, UserProxyAgent, GroupChat, GroupChatManager

logger = logging.getLogger(__name__)

@dataclass
class OrchestrationPattern(ABC):
    """
    Base class for AG2-style orchestration patterns.
    
    This follows the AG2 documentation pattern where you define:
    - initial_agent: The agent that starts the conversation
    - agents: List of all agents in the conversation
    - user_agent: The user proxy agent for human interaction
    - context_variables: Shared context for the conversation
    - group_manager_args: Arguments for the GroupChatManager
    """
    
    initial_agent: ConversableAgent
    agents: List[ConversableAgent]
    user_agent: Optional[UserProxyAgent] = None
    context_variables: Optional[Any] = None
    group_manager_args: Optional[Dict[str, Any]] = None
    max_rounds: Optional[int] = None
    
    @abstractmethod
    def create_groupchat(self) -> GroupChat:
        """Create and configure the GroupChat object for this pattern."""
        pass
    
    @abstractmethod
    def create_manager(self) -> GroupChatManager:
        """Create and configure the GroupChatManager for this pattern."""
        pass


class AutoPattern(OrchestrationPattern):
    """
    Automatic orchestration pattern - agents decide who speaks next automatically.
    Equivalent to AG2's AutoPattern with speaker_selection_method="auto".
    """
    
    def create_groupchat(self) -> GroupChat:
        """Create GroupChat with automatic speaker selection."""
        logger.info("🎯 [AUTO] Creating AutoPattern GroupChat with automatic speaker selection")
        
        # Ensure user_agent is in agents list if it exists
        all_agents = self.agents.copy()
        if self.user_agent and self.user_agent not in all_agents:
            all_agents.append(self.user_agent)
        
        groupchat = GroupChat(
            agents=list(all_agents),  # Cast for type compatibility
            messages=[],
            max_round=self.max_rounds or 50,
            speaker_selection_method="auto"
        )
        
        logger.info(f"✅ [AUTO] GroupChat created with {len(all_agents)} agents, max_rounds={groupchat.max_round}")
        return groupchat
    
    def create_manager(self) -> GroupChatManager:
        """Create GroupChatManager for automatic orchestration."""
        groupchat = self.create_groupchat()
        
        manager_args = self.group_manager_args or {}
        manager = GroupChatManager(
            groupchat=groupchat,
            **manager_args
        )
        
        logger.info("✅ [AUTO] GroupChatManager created for AutoPattern")
        return manager


class DefaultPattern(OrchestrationPattern):
    """
    Default orchestration pattern with handoffs support.
    Uses automatic speaker selection but allows explicit handoffs between agents.
    """
    
    def __init__(self, *args, enable_handoffs: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_handoffs = enable_handoffs
    
    def create_groupchat(self) -> GroupChat:
        """Create GroupChat with handoffs support."""
        logger.info("🎯 [DEFAULT] Creating DefaultPattern GroupChat with handoffs support")
        
        # Ensure user_agent is in agents list if it exists
        all_agents = self.agents.copy()
        if self.user_agent and self.user_agent not in all_agents:
            all_agents.append(self.user_agent)
        
        groupchat = GroupChat(
            agents=list(all_agents),  # Cast for type compatibility
            messages=[],
            max_round=self.max_rounds or 50,
            speaker_selection_method="auto"  # Auto with handoffs
        )
        
        logger.info(f"✅ [DEFAULT] GroupChat created with {len(all_agents)} agents, handoffs={'enabled' if self.enable_handoffs else 'disabled'}")
        return groupchat
    
    def create_manager(self) -> GroupChatManager:
        """Create GroupChatManager with handoffs configuration."""
        groupchat = self.create_groupchat()
        
        manager_args = self.group_manager_args or {}
        manager = GroupChatManager(
            groupchat=groupchat,
            **manager_args
        )
        
        # Configure handoffs if enabled
        if self.enable_handoffs:
            self._configure_handoffs(manager)
        
        logger.info(f"✅ [DEFAULT] GroupChatManager created with handoffs={'enabled' if self.enable_handoffs else 'disabled'}")
        return manager
    
    def _configure_handoffs(self, manager: GroupChatManager):
        """Configure handoffs for the workflow if a handoffs factory is available."""
        try:
            # Try to find and execute handoffs configuration
            # This will be called by the workflow orchestration
            logger.debug("🔗 [DEFAULT] Handoffs will be configured by workflow-specific handoffs factory")
        except Exception as e:
            logger.warning(f"⚠️ [DEFAULT] Handoffs configuration skipped: {e}")


class RoundRobinPattern(OrchestrationPattern):
    """
    Round-robin orchestration pattern - agents speak in sequential order.
    """
    
    def create_groupchat(self) -> GroupChat:
        """Create GroupChat with round-robin speaker selection."""
        logger.info("🎯 [ROUNDROBIN] Creating RoundRobinPattern GroupChat")
        
        # Ensure user_agent is in agents list if it exists
        all_agents = self.agents.copy()
        if self.user_agent and self.user_agent not in all_agents:
            all_agents.append(self.user_agent)
        
        groupchat = GroupChat(
            agents=list(all_agents),  # Cast for type compatibility
            messages=[],
            max_round=self.max_rounds or 50,
            speaker_selection_method="round_robin"
        )
        
        logger.info(f"✅ [ROUNDROBIN] GroupChat created with {len(all_agents)} agents in sequence")
        return groupchat
    
    def create_manager(self) -> GroupChatManager:
        """Create GroupChatManager for round-robin orchestration."""
        groupchat = self.create_groupchat()
        
        manager_args = self.group_manager_args or {}
        manager = GroupChatManager(
            groupchat=groupchat,
            **manager_args
        )
        
        logger.info("✅ [ROUNDROBIN] GroupChatManager created for RoundRobinPattern")
        return manager


class RandomPattern(OrchestrationPattern):
    """
    Random orchestration pattern - agents are selected randomly.
    """
    
    def create_groupchat(self) -> GroupChat:
        """Create GroupChat with random speaker selection."""
        logger.info("🎯 [RANDOM] Creating RandomPattern GroupChat")
        
        # Ensure user_agent is in agents list if it exists
        all_agents = self.agents.copy()
        if self.user_agent and self.user_agent not in all_agents:
            all_agents.append(self.user_agent)
        
        groupchat = GroupChat(
            agents=list(all_agents),  # Cast for type compatibility
            messages=[],
            max_round=self.max_rounds or 50,
            speaker_selection_method="random"
        )
        
        logger.info(f"✅ [RANDOM] GroupChat created with {len(all_agents)} agents")
        return groupchat
    
    def create_manager(self) -> GroupChatManager:
        """Create GroupChatManager for random orchestration."""
        groupchat = self.create_groupchat()
        
        manager_args = self.group_manager_args or {}
        manager = GroupChatManager(
            groupchat=groupchat,
            **manager_args
        )
        
        logger.info("✅ [RANDOM] GroupChatManager created for RandomPattern")
        return manager


class ManualPattern(OrchestrationPattern):
    """
    Manual orchestration pattern - human selects who speaks next.
    """
    
    def create_groupchat(self) -> GroupChat:
        """Create GroupChat with manual speaker selection."""
        logger.info("🎯 [MANUAL] Creating ManualPattern GroupChat")
        
        # Ensure user_agent is in agents list if it exists
        all_agents = self.agents.copy()
        if self.user_agent and self.user_agent not in all_agents:
            all_agents.append(self.user_agent)
        
        groupchat = GroupChat(
            agents=list(all_agents),  # Cast for type compatibility
            messages=[],
            max_round=self.max_rounds or 50,
            speaker_selection_method="manual"
        )
        
        logger.info(f"✅ [MANUAL] GroupChat created with {len(all_agents)} agents (manual selection)")
        return groupchat
    
    def create_manager(self) -> GroupChatManager:
        """Create GroupChatManager for manual orchestration."""
        groupchat = self.create_groupchat()
        
        manager_args = self.group_manager_args or {}
        manager = GroupChatManager(
            groupchat=groupchat,
            **manager_args
        )
        
        logger.info("✅ [MANUAL] GroupChatManager created for ManualPattern")
        return manager


# ==============================================================================
# PATTERN FACTORY
# ==============================================================================

def create_orchestration_pattern(
    pattern_name: str,
    initial_agent: ConversableAgent,
    agents: List[ConversableAgent],
    user_agent: Optional[UserProxyAgent] = None,
    context_variables: Optional[Any] = None,
    group_manager_args: Optional[Dict[str, Any]] = None,
    max_rounds: Optional[int] = None,
    startup_mode: str = "UserDriven",  # Keep for backwards compatibility but don't pass to pattern
    **pattern_kwargs
) -> OrchestrationPattern:
    """
    Factory function to create AG2 orchestration patterns.
    
    Args:
        pattern_name: Name of the pattern ("AutoPattern", "DefaultPattern", etc.)
        initial_agent: Agent that starts the conversation
        agents: List of all agents in the conversation
        user_agent: Optional user proxy agent
        context_variables: Shared context for the conversation
        group_manager_args: Arguments for GroupChatManager (e.g., llm_config)
        max_rounds: Maximum number of conversation rounds
        startup_mode: MozaiksAI interface behavior (ignored by AG2 patterns)
        **pattern_kwargs: Additional pattern-specific arguments
    
    Returns:
        Configured AG2 orchestration pattern
    """
    
    pattern_map = {
        "AutoPattern": AutoPattern,
        "DefaultPattern": DefaultPattern,
        "RoundRobinPattern": RoundRobinPattern,
        "RandomPattern": RandomPattern,
        "ManualPattern": ManualPattern
    }
    
    if pattern_name not in pattern_map:
        logger.warning(f"⚠️ Unknown pattern '{pattern_name}', defaulting to AutoPattern")
        pattern_name = "AutoPattern"
    
    pattern_class = pattern_map[pattern_name]
    
    logger.info(f"🎯 Creating {pattern_name} AG2 orchestration pattern")
    
    # Create the pattern with AG2-specific arguments only
    pattern = pattern_class(
        initial_agent=initial_agent,
        agents=agents,
        user_agent=user_agent,
        context_variables=context_variables,
        group_manager_args=group_manager_args,
        max_rounds=max_rounds,
        **pattern_kwargs
    )
    
    logger.info(f"✅ {pattern_name} AG2 pattern created successfully")
    
    return pattern


# ==============================================================================
# AG2-STYLE CHAT INITIATION
# ==============================================================================

async def initiate_group_chat(
    pattern: OrchestrationPattern,
    messages: Union[str, List[Dict]],
    max_rounds: Optional[int] = None,
    chat_id: Optional[str] = None,
    enterprise_id: Optional[str] = None,
    user_id: Optional[str] = None,
    workflow_name: Optional[str] = None,
    initial_message_to_user: Optional[str] = None,
    startup_mode: str = "AgentDriven"
) -> tuple:
    """
    AG2-style group chat configuration function with MozaiksAI startup_mode support.
    
    This function configures the AG2 pattern and returns the components for 
    groupchat_manager.py to actually execute. This eliminates double initialization
    by separating pattern configuration from chat execution.
    
    Args:
        pattern: AG2 orchestration pattern (AutoPattern, DefaultPattern, etc.)
        messages: Initial message(s) to start the conversation
        max_rounds: Maximum number of conversation rounds
        chat_id: Chat identifier for logging/persistence
        enterprise_id: Enterprise identifier for logging/persistence
        user_id: User identifier for logging/persistence
        workflow_name: Workflow name for logging/persistence
        initial_message_to_user: Message to show user (for UserDriven mode)
        startup_mode: MozaiksAI interface behavior (BackendOnly, UserDriven, AgentDriven)
    
    Returns:
        Tuple of (result_with_components, final_context, last_agent)
    """
    
    logger.info(f"🎯 Configuring AG2 pattern {type(pattern).__name__} for {startup_mode} mode")
    
    # Override max_rounds if provided
    if max_rounds:
        pattern.max_rounds = max_rounds
    
    # Create the GroupChat and Manager from the pattern
    groupchat = pattern.create_groupchat()
    manager = pattern.create_manager()
    
    # Determine the initiating agent based on startup_mode (MozaiksAI logic)
    if startup_mode == "BackendOnly":
        # For backend-only, use the specified initial_agent directly
        initiating_agent = pattern.initial_agent
    elif startup_mode in ["UserDriven", "AgentDriven"]:
        # For interface modes, user proxy should initiate but behavior differs
        initiating_agent = pattern.user_agent if pattern.user_agent else pattern.initial_agent
    else:
        # Default fallback
        initiating_agent = pattern.initial_agent
    
    # Determine initial message based on startup_mode (MozaiksAI logic)
    final_initial_message = None
    
    if startup_mode == "BackendOnly":
        # BackendOnly: Use provided messages directly, no interface considerations
        if isinstance(messages, str):
            final_initial_message = messages
        elif isinstance(messages, list) and len(messages) > 0:
            first_msg = messages[0]
            if isinstance(first_msg, dict):
                final_initial_message = first_msg.get('content', str(first_msg))
            else:
                final_initial_message = str(first_msg)
        else:
            final_initial_message = "Backend workflow processing initiated."
        
        logger.info(f"🤖 BackendOnly: Using message directly: {final_initial_message[:100]}...")
    
    elif startup_mode == "UserDriven":
        # UserDriven: User will provide the actual message, show initial_message_to_user if available
        if initial_message_to_user:
            # This would be shown to the user via websocket interface
            final_initial_message = initial_message_to_user
            logger.info(f"👤 UserDriven: Will show user prompt: {initial_message_to_user[:100]}...")
        else:
            # Fallback if no specific user message defined
            final_initial_message = "Please provide your request or question."
            logger.info(f"👤 UserDriven: Using fallback user prompt")
    
    elif startup_mode == "AgentDriven":
        # AgentDriven: Use the workflow's initial_message, hidden from user interface
        if isinstance(messages, str):
            final_initial_message = messages
        elif isinstance(messages, list) and len(messages) > 0:
            first_msg = messages[0]
            if isinstance(first_msg, dict):
                final_initial_message = first_msg.get('content', str(first_msg))
            else:
                final_initial_message = str(first_msg)
        else:
            final_initial_message = "Agent-driven workflow processing initiated."
        
        logger.info(f"🤖 AgentDriven: Using workflow message (hidden from user): {final_initial_message[:100]}...")
    
    else:
        # Default fallback
        final_initial_message = str(messages) if messages else "Workflow initiated."
        logger.warning(f"⚠️ Unknown startup_mode '{startup_mode}', using fallback")
    
    # Determine transport/UI behavior
    transport_enabled = startup_mode in ["UserDriven", "AgentDriven"]
    
    # Determine message visibility for UI (MozaiksAI logic)
    if startup_mode == "BackendOnly":
        message_visibility = "none"  # No interface
    elif startup_mode == "UserDriven":
        message_visibility = "user_prompt"  # Show initial_message_to_user to user
    elif startup_mode == "AgentDriven":
        message_visibility = "hidden"  # initial_message hidden from user, agent-initiated
    else:
        message_visibility = "visible"  # Default fallback
    
    # Return configured components for groupchat_manager to execute
    result = {
        "status": "configured", 
        "message": f"AG2 {type(pattern).__name__} configured successfully",
        "startup_mode": startup_mode,
        "transport_enabled": transport_enabled,
        "message_visibility": message_visibility,
        "groupchat": groupchat,
        "manager": manager,
        "initiating_agent": initiating_agent,
        "initial_message": final_initial_message
    }
    final_context = pattern.context_variables
    last_agent = initiating_agent
    
    logger.info(f"✅ AG2 pattern configured successfully - ready for execution in groupchat_manager")
    return result, final_context, last_agent
