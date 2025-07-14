# =============================================================================
# FILE: core/groupchat_manager.py
# DESCRIPTION: Core helper for starting or resuming AG2 group chats
#              (now registers the YAML-export tool from core.file_manager)
# =============================================================================
import time
import logging
from typing import Optional, Any, TYPE_CHECKING, List
from datetime import datetime

if TYPE_CHECKING:
    from ..events.simple_protocols import SimpleCommunicationChannel as CommunicationChannel

from ..data.db_manager import mongodb_manager
from ..ui.simple_ui_tools import (
    route_to_inline_component, 
    route_to_artifact_component, 
    smart_route_content,
    send_ui_tool_action,
    set_communication_channel
)
from ..monitoring.observability import get_observer, get_token_tracker
from ..transport.ag2_iostream import AG2StreamingManager
from logs.logging_config import (
    get_chat_logger,
    log_business_event,
    log_performance_metric,
    get_agent_logger,
    get_workflow_logger,
    log_operation
)

chat_logger = get_chat_logger("core_groupchat")
agent_logger = get_agent_logger("groupchat_manager")
workflow_logger = get_workflow_logger("groupchat")
logger      = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core-level agent response-time tracking
# ---------------------------------------------------------------------------
class AgentResponseTimeTracker:
    """Core-level tracking for agent response times (workflow-agnostic)."""

    def __init__(self, chat_id: str, enterprise_id: str):
        self.chat_id       = chat_id
        self.enterprise_id = enterprise_id
        self.agent_timings = {}

    def track_agent_start(self, agent_name: str):
        self.agent_timings[agent_name] = time.time()
        chat_logger.debug(f"⏱️ [CORE] Agent {agent_name} started processing")

    def track_agent_complete(self, agent_name: str, message_content: str = ""):
        if agent_name in self.agent_timings:
            start_time    = self.agent_timings[agent_name]
            response_time = (time.time() - start_time) * 1000

            log_performance_metric(
                metric_name="individual_agent_response_time",
                value=response_time,
                unit="ms",
                context={
                    "enterprise_id": self.enterprise_id,
                    "chat_id":       self.chat_id,
                    "agent_name":    agent_name,
                    "message_length": len(message_content) if message_content else 0,
                },
            )

            chat_logger.info(
                f"✅ [CORE] Agent {agent_name} responded in {response_time:.2f}ms"
            )
            del self.agent_timings[agent_name]
        else:
            chat_logger.warning(f"⚠️ [CORE] No start time recorded for {agent_name}")

def create_core_response_tracking_hooks(
    tracker: AgentResponseTimeTracker, 
    communication_channel: Optional['CommunicationChannel'] = None, 
    chat_id: str = "", 
    enterprise_id: str = "", 
    budget_capability = None,
    agents = None,
    streaming_manager: Optional[AG2StreamingManager] = None,
    workflow_type: str = "unknown",
    token_tracker = None
):
    """
    Create core-level hooks for tracking agent response times and streaming via CommunicationChannel.
    
    Args:
        tracker: Agent response time tracker
        communication_channel: Unified transport channel (SSE or WebSocket) implementing CommunicationChannel protocol
        chat_id: Chat identifier
        enterprise_id: Enterprise identifier
        budget_capability: Modular budget capability for usage tracking
        agents: List of agents for token tracking
        streaming_manager: AG2 streaming manager for real-time updates
        workflow_type: Type of workflow being executed
        token_tracker: AG2-native token tracker for usage monitoring
    """

    # Initialize AG2-native observability systems
    observer = get_observer(chat_id, enterprise_id)
    
    # Start AG2's native runtime logging for this session
    try:
        observer.start_ag2_logging()
    except Exception as e:
        chat_logger.error(f"❌ [CORE] Failed to start AG2 logging: {e}")

    def before_reply_hook(messages, **kwargs):
        # AG2 expects messages parameter and accepts additional kwargs
        # Simple logging without agent context for now
        chat_logger.debug("🔄 [CORE] Processing messages before reply")
        return messages

    def before_send_hook(message, sender=None, recipient=None, silent=None, **kwargs):
        # AG2 passes sender, recipient, and silent arguments to this hook
        # Track agent response timing if sender information is available
        if sender and hasattr(sender, 'name'):
            tracker.track_agent_start(sender.name)
            # Set agent context for IOStream streaming
            if streaming_manager:
                streaming_manager.set_agent_context(sender.name)
            
        # Extract message content and sender info
        sender_name = getattr(sender, 'name', 'unknown')
        recipient_name = getattr(recipient, 'name', 'unknown')
        message_content = ""
        
        if isinstance(message, dict):
            message_content = message.get('content', str(message))
        elif isinstance(message, str):
            message_content = message
        else:
            message_content = str(message)
            
        chat_logger.debug(f"📤 [CORE] Processing message before send from {sender_name}")
        
        # === MESSAGE VISIBILITY FILTERING ===
        # Check if this agent's messages should appear in the UI
        try:
            from .workflow_config import workflow_config
            is_visible = workflow_config.is_visible_agent(sender_name, workflow_type)
            
            if not is_visible:
                # Hidden agent (CoordinatorAgent, LoggingAgent, etc.)
                # Log the message but don't send to UI
                chat_logger.debug(f"🔇 [HIDDEN] Message from {sender_name} filtered from UI (background agent)")
            else:
                # Visible agent (ConversationAgent, ContentGeneratorAgent, etc.)
                # Send message to UI via communication channel
                if communication_channel and message_content:
                    try:
                        # Send Simple Event to UI (make it async)
                        import asyncio
                        event_data = {
                            "content": message_content,
                            "sender": sender_name,
                            "role": "assistant",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        # Use asyncio to run the async method
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # If we're in an async context, schedule for later
                                asyncio.create_task(communication_channel.send_event("chat_message", event_data, sender_name))
                            else:
                                # Run in a new event loop
                                asyncio.run(communication_channel.send_event("chat_message", event_data, sender_name))
                        except Exception:
                            # Fallback - just log if async fails
                            pass
                        
                        chat_logger.debug(f"📤 [VISIBLE] Message from {sender_name} sent to UI")
                    except Exception as e:
                        chat_logger.error(f"❌ Failed to send message to UI: {e}")
        except Exception as e:
            # If workflow config fails, default to showing all messages
            chat_logger.warning(f"⚠️ Workflow config error, showing all messages: {e}")
            is_visible = True
        
        # Track in AG2-native observability system
        if message_content and sender_name != 'unknown':
            observer.track_agent_message(
                agent_name=sender_name,
                message_content=message_content,
                recipient=recipient_name,
                message_type="response"
            )
        
        # Log the actual agent conversation to chat logs with full content
        if message_content and sender_name != 'unknown':
            # Log a summary for readability
            summary = message_content[:150] + '...' if len(message_content) > 150 else message_content
            chat_logger.info(f"🤖 [AGENT] {sender_name} → {recipient_name}: {summary}")
            
            # Log full content at debug level for complete tracking
            chat_logger.debug(f"📋 [FULL] {sender_name} complete message:\n{'-'*50}\n{message_content}\n{'-'*50}")
            
            # Log message metadata
            chat_logger.debug(f"📊 [META] Length: {len(message_content)} chars | Type: {type(message).__name__}")
            
            # Save comprehensive message and state to MongoDB
            try:
                import asyncio
                from core.data.db_manager import mongodb_manager
                
                async def save_clean_message_state():
                    try:
                        # Prepare message data
                        message_data = {
                            "sender": sender_name,
                            "recipient": recipient_name,
                            "content": message_content,
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_type": "agent_response",
                            "content_length": len(message_content)
                        }
                        
                        # Save only the clean state (phasing out comprehensive state for cleaner schema)
                        await mongodb_manager.save_chat_state(
                            chat_id=tracker.chat_id,
                            enterprise_id=tracker.enterprise_id,
                            sender=sender_name,
                            content=message_content,
                            session_id=getattr(observer, 'session_id', tracker.chat_id) if observer else tracker.chat_id,
                            agent_count=1,  # Could be improved to track actual agent count
                            iteration_count=1  # Could be improved to track actual iteration
                        )
                        
                        chat_logger.debug(f"💾 [CLEAN] Saved clean message state for {sender_name}")
                        
                    except Exception as e:
                        chat_logger.error(f"💾 [CLEAN] Failed to save clean state: {e}")
                
                # Run async function to save clean state
                asyncio.create_task(save_clean_message_state())
                        
            except Exception as e:
                chat_logger.error(f"❌ [CORE] Error setting up comprehensive state saving: {e}")
        
        # NOTE: IOStream handles the streaming automatically through AG2's native streaming
        # We no longer need manual chunking - AG2 will call iostream.print() as needed
        
        # FRONTEND/BACKEND AGENT FILTERING + UI ROUTING
        # Only agents specified in workflow.json appear in the UI
        # All other agents are "backend agents" that work behind the scenes
        should_show_in_ui = False
        routing_agent = None
        
        if communication_channel and message_content and sender_name != 'unknown':
            try:
                from .workflow_config import workflow_config
                import asyncio
                
                # Check if this sender is a frontend agent
                chat_pane_agents = workflow_config.get_chat_pane_agents(workflow_type)
                artifact_agents = workflow_config.get_artifact_agents(workflow_type)
                
                if sender_name in chat_pane_agents:
                    should_show_in_ui = True
                    routing_agent = "chat_pane"
                elif sender_name in artifact_agents:
                    should_show_in_ui = True
                    routing_agent = "artifact"
                else:
                    # This is a backend agent - don't show in UI at all
                    chat_logger.debug(f"🔇 [BACKEND] {sender_name} output filtered (backend agent)")
                    should_show_in_ui = False
                
                # Only send to UI if this is a frontend agent
                if should_show_in_ui and len(message_content.strip()) > 20:
                    async def route_content():
                        try:
                            if routing_agent == "chat_pane":
                                await route_to_inline_component(
                                    content=message_content,
                                    component_name="ChatMessage"
                                )
                                chat_logger.info(f"💬 [FRONTEND] {sender_name} → Chat Pane")
                            elif routing_agent == "artifact":
                                await route_to_artifact_component(
                                    title=f"Output from {sender_name}",
                                    content=message_content,
                                    component_name="ArtifactDisplay",
                                    category="agent_output"
                                )
                                chat_logger.info(f"📋 [FRONTEND] {sender_name} → Artifact Panel")
                        except Exception as e:
                            chat_logger.error(f"❌ [UI] Routing failed for {sender_name}: {e}")
                    
                    # Create task to run the routing
                    loop = asyncio.get_event_loop()
                    loop.create_task(route_content())
                    
            except Exception as e:
                chat_logger.error(f"❌ [UI] Error setting up agent filtering: {e}")
        
        # Log backend agent activity (but don't send to UI)
        if not should_show_in_ui and sender_name != 'unknown':
            summary = message_content[:100] + '...' if len(message_content) > 100 else message_content
            chat_logger.info(f"🔧 [BACKEND] {sender_name} (hidden): {summary}")
        
        # Continue with normal message processing (MongoDB save, token tracking, etc.)
        # This ensures backend agents are still logged and tracked, just not shown in UI
        
        # BUDGET CAPABILITY USAGE TRACKING: Update usage via modular capability
        # This works with any budget mode (commercial, opensource, testing)
        if budget_capability and budget_capability.is_enabled() and agents and message_content and sender_name != 'unknown':
            try:
                import asyncio
                
                async def track_capability_usage():
                    try:
                        if budget_capability and hasattr(budget_capability, 'update_usage'):
                            usage_result = await budget_capability.update_usage(agents)
                            chat_logger.debug(f"🪙 [BUDGET] Updated usage for {sender_name} via {budget_capability.__class__.__name__}")
                    except Exception as e:
                        chat_logger.error(f"❌ [BUDGET] Failed to update usage for {sender_name}: {e}")
                
                # Create task to run the usage tracking
                loop = asyncio.get_event_loop()
                loop.create_task(track_capability_usage())
                
            except Exception as e:
                chat_logger.error(f"❌ [BUDGET] Error setting up capability usage tracking: {e}")
        
        # AG2-NATIVE TOKEN TRACKING: Track usage via get_token_tracker
        # This provides additional observability while TokenManager is disabled for testing
        if token_tracker and message_content and sender_name != 'unknown':
            try:
                # Track token usage for this agent message
                token_tracker.track_agent_tokens(
                    agent_name=sender_name,
                    message_content=message_content,
                    recipient=recipient_name
                )
                chat_logger.debug(f"📊 [AG2-TOKEN] Tracked usage for {sender_name} via AG2-native tracker")
            except Exception as e:
                chat_logger.error(f"❌ [AG2-TOKEN] Failed to track tokens for {sender_name}: {e}")
        
        return message

    return before_reply_hook, before_send_hook

# ---------------------------------------------------------------------------
# Group Chat Hook Manager for dynamic tool registration
# ---------------------------------------------------------------------------
class GroupChatHookManager:
    """Wrapper to add dynamic hook registration capabilities to AG2 GroupChatManager."""
    
    def __init__(self, group_chat_manager: Any, chat_id: str, enterprise_id: str):
        self.group_chat_manager = group_chat_manager
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.registered_hooks = {
            "after_each_agent": [],
            "on_end": [],
            "on_start": []
        }
        self.agent_specific_hooks = {}
        
    def register_hook(self, hook_type: str, hook_func):
        """Register a hook for group chat events."""
        if hook_type in self.registered_hooks:
            self.registered_hooks[hook_type].append(hook_func)
            chat_logger.info(f"🪝 [CORE] Registered {hook_type} hook")
        else:
            chat_logger.warning(f"⚠️ [CORE] Unknown hook type: {hook_type}")
            
    def register_agent_hook(self, agent_name: str, hook_func):
        """Register a hook for a specific agent."""
        if agent_name not in self.agent_specific_hooks:
            self.agent_specific_hooks[agent_name] = []
        self.agent_specific_hooks[agent_name].append(hook_func)
        chat_logger.info(f"🪝 [CORE] Registered agent-specific hook for {agent_name}")
        
    def trigger_after_each_agent(self, message_history):
        """Trigger after_each_agent hooks."""
        for hook_func in self.registered_hooks.get("after_each_agent", []):
            try:
                hook_func(self.group_chat_manager, message_history)
            except Exception as e:
                logger.error(f"Error in after_each_agent hook: {e}")
                
        # Check for agent-specific hooks
        if message_history:
            last_message = message_history[-1]
            sender = last_message.get("sender") if isinstance(last_message, dict) else getattr(last_message, "sender", None)
            if sender and sender in self.agent_specific_hooks:
                for hook_func in self.agent_specific_hooks[sender]:
                    try:
                        hook_func(self.group_chat_manager, message_history)
                    except Exception as e:
                        logger.error(f"Error in agent-specific hook for {sender}: {e}")
                        
    def trigger_on_end(self, message_history):
        """Trigger on_end hooks."""
        for hook_func in self.registered_hooks.get("on_end", []):
            try:
                hook_func(self.group_chat_manager, message_history)
            except Exception as e:
                logger.error(f"Error in on_end hook: {e}")
                
    def trigger_on_start(self, message_history):
        """Trigger on_start hooks."""
        for hook_func in self.registered_hooks.get("on_start", []):
            try:
                hook_func(self.group_chat_manager, message_history)
            except Exception as e:
                logger.error(f"Error in on_start hook: {e}")
                
    def __getattr__(self, name):
        """Delegate unknown attributes to the underlying group_chat_manager."""
        return getattr(self.group_chat_manager, name)

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def start_or_resume_group_chat(
    manager: Any,
    initiating_agent: Any,
    chat_id: str,
    enterprise_id: str,
    user_id: Optional[str] = None,
    initial_message: Optional[str] = None,  # ✅ Already supports this
    max_turns: Optional[int] = None,
    workflow_type: str = "unknown",
    communication_channel: Optional['CommunicationChannel'] = None,
):
    """
    Starts a new group chat or resumes an existing one with unified transport support.
    
    This function now supports both SSE and WebSocket transports through the unified
    CommunicationChannel protocol. On resume, it automatically replays chat state
    and message history to restore the client UI.
    
    Args:
        manager: AG2 GroupChatManager instance
        initiating_agent: Agent to start/resume the conversation
        chat_id: Unique chat identifier
        enterprise_id: Enterprise identifier
        user_id: User identifier (optional)
        initial_message: Initial message to send (optional)
        max_turns: Maximum conversation turns (optional)
        workflow_type: Type of workflow for proper handling
        communication_channel: Unified transport channel (SSE or WebSocket)
        sse_connection: SSE connection (deprecated - use communication_channel instead)
    
    Returns:
        None (conversation runs and streams via communication_channel)
    """
    
    # ------------------------------------------------------------------
    # Initialize Budget Capability (Modular Design)
    # ------------------------------------------------------------------
    # Use modular budget capability - easily switchable between:
    from ..capabilities import get_budget_capability
    
    budget_capability = get_budget_capability(chat_id, enterprise_id, workflow_type, user_id)
    budget_info = await budget_capability.initialize_budget()
    
    # Legacy compatibility - extract token_manager if commercial mode
    token_manager = getattr(budget_capability, 'token_manager', None)
    
    # Initialize AG2-native token tracking for observability
    token_tracker = get_token_tracker(chat_id, enterprise_id, user_id or "unknown")
    
    chat_logger.info(f"💰 [BUDGET] Capability initialized: {budget_info.get('budget_type', 'unknown')}")
    chat_logger.info(f"📊 [BUDGET] AG2-native token tracking initialized for observability")
    if budget_info.get('is_free_trial'):
        chat_logger.info(f"🆓 [BUDGET] Free trial: {budget_info.get('free_loops_remaining', 0)} loops remaining")
    else:
        chat_logger.info(f"💳 [BUDGET] Mode: {budget_info.get('budget_type', 'unknown')}")

    # ------------------------------------------------------------------
    # Initialize UI routing with communication channel
    # ------------------------------------------------------------------
    if communication_channel:
        set_communication_channel(communication_channel)
        chat_logger.info("🎯 [CORE] UI routing communication channel initialized")

    # ------------------------------------------------------------------
    # Dynamic Tool Registration System
    # Automatically discovers and registers tools from active workflow
    # ------------------------------------------------------------------
    if (
        hasattr(manager, "register_tool")
        and not getattr(manager, "_workflow_tools_registered", False)
    ):
        try:
            # Import the dynamic tool discovery system
            from .tool_registry import discover_and_register_workflow_tools
            
            # Register workflow-specific tools dynamically
            agents_dict = {}
            if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
                agents_dict = {agent.name: agent for agent in manager.groupchat.agents}
            
            registered_tools = await discover_and_register_workflow_tools(
                manager=manager,
                workflow_type=workflow_type,
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                agents=agents_dict
            )
            
            setattr(manager, "_workflow_tools_registered", True)
            chat_logger.info(f"🔧 [CORE] Dynamically registered {len(registered_tools)} workflow tools: {registered_tools}")
            
        except Exception as e:
            chat_logger.error(f"❌ [CORE] Failed to register workflow tools: {e}")
            # Fallback to core tools only - maintain workflow agnostic design
            chat_logger.info("🔄 [CORE] Attempting fallback to core tools only...")
            
            try:
                from .tool_registry import register_core_tools_only
                core_tools = register_core_tools_only(manager)
                setattr(manager, "_core_tools_registered", True)
                chat_logger.info(f"🔧 [CORE] Registered {len(core_tools)} core tools as fallback")
            except Exception as final_error:
                chat_logger.error(f"❌ [CORE] Core tool registration failed: {final_error}")
                chat_logger.warning("⚠️ [CORE] Proceeding without tool registration - tools will need to be manually registered")

    # ------------------------------------------------------------------
    # Register simplified UI routing tools for chat/artifact panel routing
    # 
    # These tools enable agents to route content to different UI components:
    # - route_to_chat_pane: Route to inline chat components  
    # - route_to_artifact_panel: Create dedicated artifact workspaces
    # - smart_route_content: Automatically decide routing based on content
    # - send_ui_tool_action: Send UI tool actions
    #
    # The auto-routing is triggered in the before_send_hook below to automatically
    # route every agent message to the appropriate UI component via simple events.
    # ------------------------------------------------------------------
    if (
        hasattr(manager, "register_tool")
        and not getattr(manager, "_ui_routing_tools_registered", False)
    ):
        try:
            # Register inline component routing tool
            manager.register_tool(
                name="route_to_inline_component",
                func=route_to_inline_component,
            )
            
            # Register artifact component routing tool  
            manager.register_tool(
                name="route_to_artifact_component", 
                func=route_to_artifact_component,
            )
            
            # Register smart routing tool
            manager.register_tool(
                name="smart_route_content",
                func=smart_route_content,
            )
            
            # Register UI tool action
            manager.register_tool(
                name="send_ui_tool_action",
                func=send_ui_tool_action,
            )
            
            setattr(manager, "_ui_routing_tools_registered", True)
            chat_logger.info("🔧 [CORE] UI routing tools registered (route_to_inline_component, route_to_artifact_component, smart_route_content, send_ui_tool_action)")
            chat_logger.info("🎯 [CORE] Auto-routing enabled - all agent messages will be routed to appropriate UI components")
        except Exception as e:
            chat_logger.error(f"❌ [CORE] Failed to register UI routing tools: {e}")

    # ------------------------------------------------------------------
    # Existing logic (unchanged except for minimal variable renames)
    # ------------------------------------------------------------------
    is_human            = False
    before_reply_hook   = None
    before_send_hook    = None
    streaming_manager   = None  # Initialize to avoid UnboundLocalError in finally block
    chat_start          = time.time()

    try:
        if not initiating_agent:
            error_msg = "❌ [CORE] Critical: An initiating_agent must be provided."
            logger.error(error_msg)
            raise ValueError(error_msg)

        chat_logger.info(
            f"✅ [CORE] Initiating/resuming chat with '{initiating_agent.name}' as the entry point."
        )

        # Check budget limits using modular capability
        budget_check = await budget_capability.check_budget_limits()
        if not budget_check.get("can_continue", True):
            error_msg = f"❌ [BUDGET] {budget_check.get('message', 'Budget limits exceeded')}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        response_tracker = AgentResponseTimeTracker(chat_id, enterprise_id)
        
        # Get agents list for token tracking
        agents_list = getattr(manager.groupchat, "agents", []) if hasattr(manager, "groupchat") else []
        
        # Create AG2 streaming manager for real-time streaming
        streaming_manager = None
        if communication_channel:
            streaming_manager = AG2StreamingManager(communication_channel, chat_id, enterprise_id)
            # Attach IOStream to all agents for real-time streaming
            if agents_list:
                streaming_manager.attach_to_agents(agents_list)
                chat_logger.info(f"📡 [CORE] AG2 IOStream attached to {len(agents_list)} agents")
        
        before_reply_hook, before_send_hook = create_core_response_tracking_hooks(
            tracker=response_tracker,
            communication_channel=communication_channel,
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            budget_capability=budget_capability,
            agents=agents_list,
            streaming_manager=streaming_manager,
            workflow_type=workflow_type,
            token_tracker=token_tracker
        )

        if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
            for agent in manager.groupchat.agents:
                if hasattr(agent, "register_hook"):
                    agent.register_hook("process_all_messages_before_reply", before_reply_hook)
                    agent.register_hook("process_message_before_send",       before_send_hook)
                    chat_logger.debug(f"🎯 [CORE] Response time tracking enabled for {agent.name}")
            chat_logger.info("🎯 [CORE] Core-level response time tracking enabled for all agents")

        determined_max_turns = None
        # Get turn limit from budget capability
        capability_turn_limit = budget_capability.get_turn_limit()
        if capability_turn_limit is not None:
            determined_max_turns = capability_turn_limit
        if max_turns is not None:
            determined_max_turns = max_turns

        if determined_max_turns:
            chat_logger.info(f"🔢 [CORE] Chat will run with max_turns={determined_max_turns}")
        else:
            chat_logger.info("♾️ [CORE] Chat will run without turn limit (handoffs control flow)")

        prev_state = await mongodb_manager.load_chat_state(chat_id, enterprise_id)

        prior_messages = []
        if prev_state:
            prior_messages = prev_state.get("session_state", {}).get("messages", []) or []
            if not prior_messages and prev_state.get("conversation_state"):
                prior_messages = prev_state["conversation_state"].get("messages", []) or []

        if not prior_messages:
            chat_logger.info(f"🚀 [CORE] Initiating group chat: {chat_id}")
            
            # Trigger on_start hooks before initiating the chat
            if hasattr(manager, 'trigger_on_start'):
                try:
                    manager.trigger_on_start([])  # Empty message history at start
                    manager._on_start_hooks_fired = True  # Mark as fired
                    chat_logger.info("🪝 [CORE] on_start hooks triggered")
                except Exception as e:
                    chat_logger.error(f"❌ [CORE] Error triggering on_start hooks: {e}")
            
            initiate_kwargs = {
                "recipient": initiating_agent,
                "message":   initial_message or "Start the workflow",
            }
            if determined_max_turns:
                initiate_kwargs["max_turns"] = determined_max_turns

            agent_start_time = time.time()
            chat_logger.info("⏱️ [CORE] Starting agent conversation...")
            await manager.a_initiate_chat(**initiate_kwargs)

            agent_response_time = (time.time() - agent_start_time) * 1000
            log_performance_metric(
                metric_name="agent_conversation_duration",
                value=agent_response_time,
                unit="ms",
                context={
                    "enterprise_id": enterprise_id,
                    "chat_id":       chat_id,
                    "initiating_agent": initiating_agent.name,
                    "max_turns":     determined_max_turns,
                },
            )
            chat_logger.info(f"✅ [CORE] Agent conversation completed in {agent_response_time:.2f}ms")

            # Complete user feedback loop if applicable
            if budget_capability and budget_capability.is_enabled() and initial_message is not None:
                try:
                    await budget_capability.complete_user_feedback_loop()
                except Exception as e:
                    chat_logger.error(f"❌ [BUDGET] Failed to complete feedback loop: {e}")

        else:
            chat_logger.info(f"⏱️ [CORE] Resuming group chat: {chat_id}")
            await mongodb_manager.mark_chat_reconnected(chat_id, enterprise_id)

            # Replay state to client on reconnect (unified for both SSE and WebSocket)
            if communication_channel is not None and prev_state:
                try:
                    # Send complete state snapshot for client UI restoration
                    await communication_channel.send_event("state_snapshot", prev_state.get("session_state", {}))
                    
                    # Send messages snapshot for chat history restoration  
                    if prior_messages:
                        await communication_channel.send_event("messages_snapshot", prior_messages)
                        chat_logger.info(f"📡 [CORE] Replayed {len(prior_messages)} messages to reconnected client")
                    
                    # Send connection status event
                    await communication_channel.send_event(
                        event_type="connection_restored",
                        data={
                            "chat_id": chat_id,
                            "enterprise_id": enterprise_id,
                            "message_count": len(prior_messages),
                            "workflow_type": workflow_type,
                            "reconnected_at": datetime.utcnow().isoformat()
                        }
                    )
                    
                    chat_logger.info(f"✅ [CORE] Chat state restored for reconnected client")
                    
                except Exception as e:
                    chat_logger.error(f"❌ [CORE] Failed to replay state on reconnect: {e}")

            # Trigger on_start hooks if this is the first resume after restart
            # (on_start hooks should only fire once per chat lifecycle)
            if hasattr(manager, 'trigger_on_start') and not getattr(manager, '_on_start_hooks_fired', False):
                try:
                    manager.trigger_on_start(prior_messages)
                    manager._on_start_hooks_fired = True  # Mark as fired
                    chat_logger.info("🪝 [CORE] on_start hooks triggered on resume")
                except Exception as e:
                    logger.error(f"❌ [CORE] Error triggering on_start hooks on resume: {e}")

            resume_kwargs = {}
            if determined_max_turns:
                resume_kwargs["max_turns"] = determined_max_turns
            if initial_message:
                resume_kwargs["message"] = initial_message

            agent_start_time = time.time()
            chat_logger.info("⏱️ [CORE] Resuming agent conversation...")
            await manager.a_run_group_chat(**resume_kwargs)

            agent_response_time = (time.time() - agent_start_time) * 1000
            log_performance_metric(
                metric_name="agent_resume_duration",
                value=agent_response_time,
                unit="ms",
                context={
                    "enterprise_id": enterprise_id,
                    "chat_id":       chat_id,
                    "max_turns":     determined_max_turns,
                },
            )
            chat_logger.info(f"✅ [CORE] Agent conversation resumed in {agent_response_time:.2f}ms")

            # Complete user feedback loop if applicable  
            if budget_capability and budget_capability.is_enabled() and initial_message is not None:
                try:
                    await budget_capability.complete_user_feedback_loop()
                except Exception as e:
                    chat_logger.error(f"❌ [BUDGET] Failed to complete feedback loop: {e}")

    except Exception:
        logger.exception("Unexpected error in start_or_resume_group_chat")
        raise

    finally:
        # Clean up IOStream if it was set up
        if streaming_manager:
            try:
                streaming_manager.restore_iostream()
                chat_logger.info("🧹 [CORE] AG2 IOStream restored")
            except Exception as e:
                logger.error(f"❌ [CORE] Error restoring IOStream: {e}")
        
        if before_reply_hook and before_send_hook and hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
            for agent in manager.groupchat.agents:
                if hasattr(agent, "unregister_hook"):
                    agent.unregister_hook("process_all_messages_before_reply", before_reply_hook)
                    agent.unregister_hook("process_message_before_send",       before_send_hook)
                    chat_logger.debug(f"🧹 [CORE] Response time tracking disabled for {agent.name}")

        chat_time = (time.time() - chat_start) * 1000
        log_performance_metric(
            metric_name="groupchat_execution_duration",
            value=chat_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id},
        )
        log_business_event(
            event_type="GROUPCHAT_COMPLETED",
            description="Core groupchat start/resume completed",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id, "duration_ms": chat_time},
        )

# ==============================================================================
# FRONTEND/BACKEND AGENT ARCHITECTURE
# ==============================================================================
# 
# Clean separation between frontend agents (visible to users) and backend agents:
#
# Configuration in workflow.json:
# {
#   "chat_pane_agents": ["UserAgent", "ConversationAgent"],
#   "artifact_agents": ["ArtifactAgent1", "ArtifactAgent2"]
# }
#
# Agent Behavior:
# ✅ FRONTEND AGENTS (specified in arrays):
#   - chat_pane_agents → Messages appear in ChatPane component
#   - artifact_agents → Output creates Artifact panels
#   - All sent via SSE/WebSocket to UI
#
# 🔇 BACKEND AGENTS (all others):
#   - Never sent to UI - completely filtered out
#   - Still logged and tracked in MongoDB
#   - Still participate in agent conversations
#   - Work behind the scenes for coordination/analysis
# ==============================================================================

def create_enhanced_group_chat_manager(group_chat_manager: Any, chat_id: str, enterprise_id: str) -> GroupChatHookManager:
    """Create an enhanced group chat manager with dynamic hook registration."""
    return GroupChatHookManager(group_chat_manager, chat_id, enterprise_id)

def get_frontend_agents(workflow_type: str) -> List[str]:
    """
    Get all frontend agents for a workflow.
    
    Returns:
        List[str]: All agents that appear in UI (chat + artifact agents)
    """
    try:
        from .workflow_config import workflow_config
        return workflow_config.get_frontend_agents(workflow_type)
    except Exception as e:
        logger.error(f"Failed to get frontend agents for {workflow_type}: {e}")
        return []

def is_frontend_agent(agent_name: str, workflow_type: str) -> bool:
    """
    Check if an agent should appear in the frontend UI.
    
    Args:
        agent_name: Name of the agent to check
        workflow_type: Type of workflow
        
    Returns:
        bool: True if agent should appear in UI, False if backend-only
    """
    try:
        from .workflow_config import workflow_config
        return workflow_config.is_frontend_agent(agent_name, workflow_type)
    except Exception as e:
        logger.error(f"Failed to check frontend agent {agent_name} for {workflow_type}: {e}")
        return False
