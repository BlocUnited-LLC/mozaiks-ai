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

from ..data.persistence_manager import persistence_manager as mongodb_manager
from ..ui.simple_ui_tools import (
    route_to_inline_component, 
    route_to_artifact_component, 
    send_ui_tool_action,
    handle_component_action,
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
        
        # === STREAMING FOR USER-VISIBLE MESSAGES ===
        # Instead of complex async event sending, use the streaming manager to mark content for streaming
        if streaming_manager and message_content and sender_name != 'unknown':
            # Check if this message should be visible to users (not internal coordination)
            is_user_response = True
            
            # Skip internal AutoGen coordination messages
            if any(keyword in sender_name.lower() for keyword in ['chat_manager', 'manager']):
                is_user_response = False
            if any(keyword in message_content.lower() for keyword in ['next speaker', 'terminating', 'function_call']):
                is_user_response = False
            if message_content.startswith('{') and message_content.endswith('}'):
                is_user_response = False
                
            if is_user_response:
                chat_logger.info(f"📡 [STREAMING] Marking content for streaming from {sender_name}")
                # Mark the next IOStream print() call to be streamed
                streaming_manager.mark_content_for_streaming(sender_name, message_content)
            else:
                chat_logger.debug(f"🔇 [FILTERING] Skipping internal message from {sender_name}")
        
        # === MESSAGE VISIBILITY FILTERING (Legacy approach - keeping for fallback) ===
        # This was the old approach trying to send events directly, keeping as backup
        try:
            # Simple visibility check - default to visible unless clearly internal
            is_visible = 'manager' not in sender_name.lower()
            
            if not is_visible:
                chat_logger.debug(f"� [HIDDEN] Message from {sender_name} filtered from UI (background agent)")
            else:
                chat_logger.debug(f"👁️ [VISIBLE] Message from {sender_name} marked as visible")
        except Exception as e:
            # If anything fails, default to showing messages
            chat_logger.warning(f"⚠️ Visibility check error, defaulting to visible: {e}")
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
        
        # NOTE: Streaming is now handled automatically via the IOStream + mark_content_for_streaming approach
        # No need for complex async event handling here
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
                # Track token usage for this agent message using the correct method
                token_tracker.track_agent_message(
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
    initial_message: Optional[str] = None,
    max_turns: Optional[int] = None,
    workflow_type: str = "unknown",
    communication_channel: Optional['CommunicationChannel'] = None,
):
    """
    Starts a new group chat or resumes an existing one with unified transport support.
    
    This function now uses the centralized AG2ResumeManager for proper state persistence
    and restoration across all transport types (SSE, WebSocket, SimpleTransport).
    
    Key features:
    - Official AG2 resume patterns implementation
    - Transport-agnostic persistence
    - Proper frontend state restoration
    - Connection state tracking
    """
    
    # ------------------------------------------------------------------
    # Check for resumable session (simplified - no centralized manager needed)
    # ------------------------------------------------------------------
    prev_state = await mongodb_manager.load_chat_state(chat_id, enterprise_id)
    can_resume = prev_state is not None and prev_state.get("ag2_groupchat_state", {}).get("messages", [])
    
    if can_resume:
        chat_logger.info(f"📥 Resumable session found for {chat_id}")
        
        # Simple resume logic - restore messages to groupchat
        if hasattr(manager, "groupchat") and prev_state:
            ag2_state = prev_state.get("ag2_groupchat_state", {})
            messages = ag2_state.get("messages", [])
            
            if messages:
                manager.groupchat.messages = messages.copy()
                chat_logger.info(f"✅ Restored {len(messages)} messages to groupchat")
                
                # Send state restoration to frontend if communication channel available
                if communication_channel:
                    try:
                        await communication_channel.send_event(
                            event_type="messages_snapshot",
                            data={
                                "messages": messages,
                                "message_count": len(messages),
                                "chat_id": chat_id
                            }
                        )
                        
                        await communication_channel.send_event(
                            event_type="connection_restored",
                            data={
                                "chat_id": chat_id,
                                "enterprise_id": enterprise_id,
                                "message_count": len(messages),
                                "restored_at": datetime.utcnow().isoformat()
                            }
                        )
                        chat_logger.info(f"📡 Sent restoration events to frontend")
                    except Exception as e:
                        chat_logger.warning(f"⚠️ Failed to send restoration events: {e}")
                
                # Continue with resumed session
                determined_max_turns = max_turns or None
                if determined_max_turns:
                    await manager.a_run_group_chat(max_turns=determined_max_turns)
                else:
                    await manager.a_run_group_chat()
                
                return  # Resume completed successfully
    else:
        chat_logger.info(f"🆕 Starting new session for {chat_id}")
    
    # ------------------------------------------------------------------
    # Continue with original new session logic
    # ------------------------------------------------------------------
    
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
            
            # Register component action handler
            manager.register_tool(
                name="handle_component_action",
                func=handle_component_action,
            )
            
            # Register UI tool action
            manager.register_tool(
                name="send_ui_tool_action",
                func=send_ui_tool_action,
            )
            
            setattr(manager, "_ui_routing_tools_registered", True)
            chat_logger.info("🔧 [CORE] UI routing tools registered (route_to_inline_component, route_to_artifact_component, handle_component_action, send_ui_tool_action)")
            chat_logger.info("🎯 [CORE] Auto-routing enabled - all agent messages will be routed to appropriate UI components")
        except Exception as e:
            chat_logger.error(f"❌ [CORE] Failed to register UI routing tools: {e}")

    # ------------------------------------------------------------------
    # Unified Workflow Configuration Logic (Human-in-the-Loop + Auto-Start)
    # ------------------------------------------------------------------
    # This implements a comprehensive solution that coordinates:
    # 1. human_in_the_loop flag - Controls user interaction capability
    # 2. auto_start flag - Controls whether workflow starts autonomously
    # 3. UserProxyAgent configuration - Matches agent behavior to flags
    # 4. initiating_agent - Ensures proper workflow start based on configuration
    if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
        try:
            from .workflow_config import workflow_config
            
            # Get workflow configuration
            config = workflow_config.get_config(workflow_type)
            human_in_loop = config.get("human_in_the_loop", False)
            auto_start = config.get("auto_start", False)
            initiating_agent_name = config.get("initiating_agent", "user")
            
            chat_logger.info(f"🎯 [CONFIG] Workflow '{workflow_type}' configuration:")
            chat_logger.info(f"   • human_in_the_loop: {human_in_loop}")
            chat_logger.info(f"   • auto_start: {auto_start}")
            chat_logger.info(f"   • initiating_agent: {initiating_agent_name}")
            
            # ------------------------------------------------------------------
            # Auto-Generate UserProxyAgent (if needed)
            # ------------------------------------------------------------------
            
            # Check if UserProxyAgent already exists
            has_user_proxy = False
            user_proxy_agent = None
            
            for agent in manager.groupchat.agents:
                if hasattr(agent, 'human_input_mode') and ('proxy' in agent.name.lower() or 'user' in agent.name.lower()):
                    has_user_proxy = True
                    user_proxy_agent = agent
                    original_mode = getattr(agent, 'human_input_mode', 'UNKNOWN')
                    
                    # Configure human_input_mode based solely on workflow requirements
                    if human_in_loop:
                        # Workflow requires human interaction - UserProxy should prompt for input
                        agent.human_input_mode = "ALWAYS"
                        chat_logger.info(f"👤 [CONFIG] {agent.name}: human_in_the_loop=true → ALWAYS mode (user interaction enabled)")
                    else:
                        # Autonomous workflow - UserProxy should never prompt for input
                        agent.human_input_mode = "NEVER"
                        chat_logger.info(f"🤖 [CONFIG] {agent.name}: human_in_the_loop=false → NEVER mode (autonomous)")
                    
                    chat_logger.info(f"✅ [CONFIG] {agent.name} configured: {original_mode} → {agent.human_input_mode}")
                    
                    # Note: The transport method (communication_channel vs terminal) doesn't affect 
                    # when AutoGen agents ask for input - it only affects how that input is delivered
                    if communication_channel:
                        chat_logger.debug(f"🌐 [CONFIG] Using web transport - user input will be routed via communication_channel")
                    else:
                        chat_logger.debug(f"🖥️ [CONFIG] Using terminal transport - user input will be prompted directly")
                    break
            
            # AUTO-GENERATION LOGIC: Create UserProxyAgent if needed
            if human_in_loop and not has_user_proxy:
                chat_logger.info(f"🚀 [AUTO-GEN] human_in_the_loop=true but no UserProxyAgent found")
                chat_logger.info(f"� [AUTO-GEN] Auto-generating UserProxyAgent for workflow '{workflow_type}'")
                
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 🎯 CUSTOMIZATION POINT #1: UserProxyAgent Creation
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 
                # 📍 WHERE: Modify the UserProxyAgent creation below
                # 
                # 🔧 CUSTOMIZATION OPTIONS:
                #   • Change agent name (e.g., f"{workflow_type}_user", "enterprise_user")
                #   • Modify system_message based on workflow_type, enterprise_id, user_role
                #   • Set different human_input_mode ("ALWAYS", "NEVER", "TERMINATE")
                #   • Add code_execution_config for specific workflows
                #   • Include custom llm_config for enterprise requirements
                #   • Add description field for better agent identification
                #
                # 💡 ENTERPRISE EXAMPLES:
                #   • if enterprise_id == "healthcare": system_message = "You are a healthcare..."
                #   • if workflow_type == "legal": name = "legal_reviewer"
                #   • if user_role == "admin": human_input_mode = "TERMINATE"
                #
                # 🏗️ WORKFLOW-SPECIFIC EXAMPLES:
                #   • if workflow_type == "generator": system_message = "You are creating..."
                #   • if workflow_type == "analyzer": code_execution_config = {"use_docker": True}
                #   • if "secure" in workflow_type: add additional validation
                #
                # 📊 CONDITIONAL LOGIC SUGGESTIONS:
                #   • Check config.get("user_expertise_level") for system_message complexity
                #   • Use config.get("enterprise_settings", {}) for custom configuration
                #   • Apply config.get("security_level") for restricted workflows
                # ═══════════════════════════════════════════════════════════════════════════════════
                
                from autogen import UserProxyAgent
                
                # Default UserProxyAgent configuration (customize above as needed)
                auto_user_proxy = UserProxyAgent(
                    name="user",
                    human_input_mode="ALWAYS",  # Matches human_in_the_loop=true
                    code_execution_config=False,  # Disable code execution by default
                    system_message="You are a user interacting with a multi-agent workflow system. Provide input, feedback, and guidance as needed.",
                    llm_config=False,  # UserProxy doesn't need LLM config
                    # CUSTOMIZE: Add description, max_consecutive_auto_reply, etc.
                )
                
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 🎯 CUSTOMIZATION POINT #2: Agent Registration & Integration  
                # ═══════════════════════════════════════════════════════════════════════════════════
                #
                # 📍 WHERE: Modify how the auto-generated agent is added to the groupchat
                #
                # 🔧 CUSTOMIZATION OPTIONS:
                #   • Change agent position in groupchat (insert at specific index)
                #   • Add agent to specific subgroups or roles
                #   • Set agent as admin or moderator
                #   • Configure agent-specific conversation rules
                #   • Add custom agent metadata or tags
                #
                # 💡 POSITIONING EXAMPLES:
                #   • manager.groupchat.agents.insert(0, auto_user_proxy)  # First agent
                #   • manager.groupchat.agents.insert(-1, auto_user_proxy)  # Before last
                #   • Add after specific agent type (find index by agent role)
                #
                # 🏗️ INTEGRATION EXAMPLES:
                #   • Set as groupchat admin: manager.groupchat.admin_name = "user" 
                #   • Add to speaker_transitions: config["speaker_transitions"]["user"] = [...]
                #   • Configure max_round limits for user agent
                # ═══════════════════════════════════════════════════════════════════════════════════
                
                # Add auto-generated UserProxyAgent to groupchat
                manager.groupchat.agents.append(auto_user_proxy)
                user_proxy_agent = auto_user_proxy
                
                chat_logger.info(f"✅ [AUTO-GEN] UserProxyAgent '{auto_user_proxy.name}' created and added to groupchat")
                chat_logger.info(f"🎯 [AUTO-GEN] Agent configured: human_input_mode='{auto_user_proxy.human_input_mode}'")
                
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 🎯 CUSTOMIZATION POINT #3: Post-Creation Configuration
                # ═══════════════════════════════════════════════════════════════════════════════════
                #
                # 📍 WHERE: Add any post-creation setup logic here
                #
                # 🔧 CUSTOMIZATION OPTIONS:
                #   • Register custom tools with the auto-generated agent
                #   • Set up agent-specific event handlers
                #   • Configure agent relationships or hierarchies  
                #   • Add custom validation or security checks
                #   • Initialize agent-specific state or memory
                #
                # 💡 TOOL REGISTRATION EXAMPLES:
                #   • auto_user_proxy.register_for_execution(name="custom_tool")(custom_function)
                #   • Add workflow-specific tools based on workflow_type
                #   • Register enterprise tools based on enterprise_id
                #
                # 🏗️ SETUP EXAMPLES:
                #   • Initialize agent memory: auto_user_proxy._memory = {}
                #   • Set agent permissions: auto_user_proxy._permissions = config.get("user_permissions")
                #   • Configure logging: auto_user_proxy._logger = custom_logger
                # ═══════════════════════════════════════════════════════════════════════════════════
                
                # CUSTOMIZE: Add any post-creation setup here
                # Example: auto_user_proxy.register_for_execution(name="feedback_tool")(feedback_function)
                
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 🎯 AUTOMATIC TRANSPORT INTEGRATION: UserProxy ↔ CommunicationChannel
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 
                # The auto-generated UserProxy automatically integrates with the transport layer:
                # • AG2's native human_input_mode="ALWAYS" triggers input requests
                # • CommunicationChannel handles transport-agnostic user input (SSE/WebSocket)
                # • No custom a_get_human_input() override needed - AG2 handles it natively
                # • IOStream automatically streams UserProxy responses to frontend
                # 
                # 🔧 HOW IT WORKS:
                # 1. UserProxy calls AG2's native input system when human_input_mode="ALWAYS"
                # 2. Transport layer (ag2_websocket_adapter/ag2_sse_adapter) handles user input
                # 3. Frontend sends user input via WebSocket/SSE message
                # 4. Backend routes input back to waiting UserProxy agent
                # 5. UserProxy continues conversation with user input
                # 
                # 📡 FRONTEND INTEGRATION:
                # • No special component needed for basic UserProxy interaction
                # • UI input automatically routed via CommunicationChannel
                # • UserProxy responses stream to frontend via IOStream
                # • Special UI components only needed for complex user tools
                # ═══════════════════════════════════════════════════════════════════════════════════
                
                chat_logger.info(f"🔗 [AUTO-GEN] UserProxy transport integration: CommunicationChannel-ready")
                chat_logger.info(f"📡 [AUTO-GEN] User input will be handled via {communication_channel.__class__.__name__ if communication_channel else 'terminal'}")
                
                
            elif not human_in_loop:
                chat_logger.debug(f"🤖 [CONFIG] human_in_the_loop=false - no UserProxyAgent needed (autonomous mode)")
            else:
                chat_logger.debug(f"✅ [CONFIG] UserProxyAgent already exists - no auto-generation needed")
            
            # ═══════════════════════════════════════════════════════════════════════════════════
            # 🎯 FINAL VALIDATION: UserProxyAgent Configuration Summary
            # ═══════════════════════════════════════════════════════════════════════════════════
            
            # Validate and log final UserProxyAgent configuration
            if user_proxy_agent:
                proxy_mode = getattr(user_proxy_agent, 'human_input_mode', 'UNKNOWN')
                proxy_name = getattr(user_proxy_agent, 'name', 'UNKNOWN')
                chat_logger.info(f"🎯 [VALIDATION] Final UserProxyAgent: '{proxy_name}' with mode '{proxy_mode}'")
                
                # Validate configuration consistency
                if human_in_loop and proxy_mode != "ALWAYS":
                    chat_logger.warning(f"⚠️ [VALIDATION] Configuration mismatch: human_in_the_loop=true but UserProxy mode='{proxy_mode}'")
                elif not human_in_loop and proxy_mode != "NEVER":
                    chat_logger.warning(f"⚠️ [VALIDATION] Configuration mismatch: human_in_the_loop=false but UserProxy mode='{proxy_mode}'")
                else:
                    chat_logger.info(f"✅ [VALIDATION] UserProxyAgent configuration is consistent with workflow settings")
                    
                # Log initiating agent compatibility
                if initiating_agent_name.lower() in ['user', 'userproxy'] and proxy_name.lower() in ['user', 'userproxy']:
                    if auto_start:
                        chat_logger.warning(f"⚠️ [VALIDATION] Potential auto-start issue: initiating_agent='{initiating_agent_name}' with auto_start=true")
                    else:
                        chat_logger.info(f"✅ [VALIDATION] Manual start with user agent is configured correctly")
            else:
                if human_in_loop:
                    chat_logger.warning(f"⚠️ [VALIDATION] human_in_the_loop=true but no UserProxyAgent found or created")
                else:
                    chat_logger.info(f"✅ [VALIDATION] No UserProxyAgent needed for autonomous workflow")
            
            # Validate initiating_agent configuration
            if auto_start and initiating_agent_name.lower() in ['user', 'userproxy']:
                chat_logger.warning(f"⚠️ [CONFIG] Potential configuration conflict:")
                chat_logger.warning(f"   • auto_start=true but initiating_agent='{initiating_agent_name}'")
                chat_logger.warning(f"   • Auto-starting with user agent may cause issues")
                chat_logger.warning(f"   • Consider using a non-user agent for auto-start workflows")
            
            if not auto_start and initiating_agent_name.lower() not in ['user', 'userproxy']:
                chat_logger.info(f"📋 [CONFIG] Manual start workflow with '{initiating_agent_name}' as initiator")
                chat_logger.info(f"   • Workflow will wait for initial trigger, then '{initiating_agent_name}' will start")
            
            # Log final configuration summary
            if human_in_loop and auto_start:
                config_type = "Hybrid: Auto-start with user interaction capability"
            elif human_in_loop and not auto_start:
                config_type = "Interactive: Manual start with user interaction"
            elif not human_in_loop and auto_start:
                config_type = "Autonomous: Auto-start without user interaction"
            else:
                config_type = "Manual: Manual start without user interaction"
            
            chat_logger.info(f"🎯 [CONFIG] Final configuration: {config_type}")
                
        except Exception as e:
            chat_logger.error(f"❌ [CONFIG] Failed to configure workflow settings for '{workflow_type}': {e}")
            chat_logger.info("🔄 [CONFIG] Proceeding with default agent configuration")

    # ------------------------------------------------------------------
    # Existing logic (unchanged except for minimal variable renames)
    # ------------------------------------------------------------------
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

        # Check budget limits using modular capability (bypass for test mode)
        if enterprise_id == "test_mode_bypass_budget":
            logger.info("🧪 [TEST MODE] Bypassing budget checks for testing")
            budget_check = {"can_continue": True, "message": "Test mode - budget bypassed"}
        else:
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
            
            # Ensure we have a valid initial message
            safe_initial_message = initial_message or "Start the workflow"
            if not isinstance(safe_initial_message, str) or not safe_initial_message.strip():
                safe_initial_message = "Start the workflow"
            
            initiate_kwargs = {
                "recipient": initiating_agent,
                "message":   safe_initial_message,
            }
            if determined_max_turns:
                initiate_kwargs["max_turns"] = determined_max_turns

            chat_logger.info(f"🚀 [CORE] Initiating chat with message: '{safe_initial_message}'")
            
            # Safety check: Ensure all agents have proper initialization
            if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
                for agent in manager.groupchat.agents:
                    if not hasattr(agent, 'chat_messages'):
                        agent.chat_messages = {}
                    # Ensure each agent has an empty message list for other agents if needed
                    for other_agent in manager.groupchat.agents:
                        if other_agent != agent and other_agent not in agent.chat_messages:
                            agent.chat_messages[other_agent] = []
                chat_logger.info(f"🔧 [CORE] Initialized chat_messages for {len(manager.groupchat.agents)} agents")
            
            agent_start_time = time.time()
            chat_logger.info("⏱️ [CORE] Starting agent conversation...")
            
            try:
                # NEW ROBUST APPROACH:
                # Instead of just passing a message string to a_initiate_chat,
                # we will manually add the first message to the history. This
                # ensures the first agent to speak has a message to reply to,
                # preventing the IndexError.
                
                # 1. Add the initial message to the recipient's history
                initiating_agent.send(
                    message=initial_message,
                    recipient=manager,
                    request_reply=False,  # We don't need a reply here, just queuing the message
                    silent=True,          # Prevent this from being printed unnecessarily
                )
                chat_logger.info(f"📨 [CORE] Queued initial message for manager: '{initial_message}'")

                # 2. Initiate the chat without a message, as it's already in the history
                initiate_kwargs['message'] = None
                await manager.a_initiate_chat(**initiate_kwargs)

            except IndexError as e:
                chat_logger.error(f"❌ [CORE] IndexError in agent conversation: {e}")
                chat_logger.error(f"🔍 [CORE] Initiate kwargs: {initiate_kwargs}")
                chat_logger.error(f"🔍 [CORE] Manager chat messages: {getattr(manager, 'chat_messages', 'NOT_SET')}")
                raise

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
            # Mark connection as active (simplified)
            await mongodb_manager.mark_connection_state(
                chat_id=chat_id,
                enterprise_id=enterprise_id,
                state="reconnected",
                transport_type="unified"
            )

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
