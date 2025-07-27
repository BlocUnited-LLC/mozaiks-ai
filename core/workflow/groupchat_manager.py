# =============================================================================
# FILE: core/groupchat_manager.py
# DESCRIPTION: Core helper for starting or resuming AG2 group chats
#              (now registers the YAML-export tool from core.file_manager)
# =============================================================================
import time
import logging
import asyncio
import inspect
import uuid
from typing import Optional, Any, TYPE_CHECKING, List, Dict
from datetime import datetime
from collections import defaultdict

from ..data.persistence_manager import PersistenceManager

# Initialize persistence manager
mongodb_manager = PersistenceManager()
from ..monitoring.observability import get_observer, get_token_tracker
from ..transport.ag2_iostream import AG2StreamingManager
from .tool_registry import WorkflowToolRegistry, ToolTrigger
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
logger = logging.getLogger(__name__)

# Performance-focused logging - minimal overhead
function_call_logger = logging.getLogger("ag2_function_call_debug")
function_call_logger.setLevel(logging.ERROR)  # Only log critical errors

# Keep minimal deep logging for critical debugging when needed
deep_logger = logging.getLogger("ag2_deep_debug")
deep_logger.setLevel(logging.WARNING)  # Only warnings and errors

# Agent lifecycle logging for tool registration
agent_lifecycle_logger = logging.getLogger("ag2_agent_lifecycle")
agent_lifecycle_logger.setLevel(logging.INFO)  # Keep tool registration info

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
    chat_id: str = "", 
    enterprise_id: str = "", 
    budget_capability = None,
    agents = None,
    streaming_manager: Optional[AG2StreamingManager] = None,
    workflow_name: str = "unknown",
    token_tracker = None
):
    """
    Create core-level hooks for tracking agent response times and streaming via CommunicationChannel.
    
    Args:
        tracker: Agent response time tracker
        chat_id: Chat identifier
        enterprise_id: Enterprise identifier
        budget_capability: Modular budget capability for usage tracking
        agents: List of agents for token tracking
        streaming_manager: AG2 streaming manager for real-time updates
        workflow_name: Type of workflow being executed
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
        
        # Safety check: ensure all messages have valid content
        if isinstance(messages, list):
            for i, msg in enumerate(messages):
                if isinstance(msg, dict) and msg.get('content') is None:
                    messages[i]['content'] = "[No content provided]"
                    chat_logger.warning(f"⚠️ [CORE] Fixed None content in message {i}")
        
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
            # Safety check: ensure content is not None
            if message_content is None:
                message_content = "[No content provided]"
                message['content'] = message_content
                chat_logger.warning(f"⚠️ [CORE] Fixed None content from {sender_name}")
        elif isinstance(message, str):
            message_content = message
        else:
            message_content = str(message)
            
        # Final safety check for None content
        if message_content is None:
            message_content = "[No content provided]"
            chat_logger.warning(f"⚠️ [CORE] Prevented None message from {sender_name}")
            
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
        
        # === MESSAGE VISIBILITY FILTERING ===
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
        
        # NOTE: UI routing is now handled by individual tools (api_manager.py, file_manager.py)
        # Tools emit UI events directly via emit_ui_tool_event() when needed
        
        # Continue with normal message processing (MongoDB save, token tracking, etc.)
        
        # BUDGET CAPABILITY USAGE TRACKING: Update usage via modular capability
        # This works with any budget mode (commercial, opensource, testing)
        if budget_capability and budget_capability.is_enabled() and agents and message_content and sender_name != 'unknown':
            try:
                import asyncio
                
                async def track_capability_usage():
                    try:
                        if budget_capability and hasattr(budget_capability, 'update_usage'):
                            usage_result = await budget_capability.update_usage(agents)
                            if usage_result:
                                chat_logger.debug(f"🪙 [BUDGET] Updated usage for {sender_name}: {usage_result}")
                            else:
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
# Main entry point
# ---------------------------------------------------------------------------
async def _start_or_resume_group_chat(
    manager: Any,
    initiating_agent: Any,
    chat_id: str,
    enterprise_id: str,
    user_id: Optional[str] = None,
    initial_message: Optional[str] = None,
    max_turns: Optional[int] = None,
    workflow_name: str = "unknown",
    context_variables: Optional[Any] = None,  # 🎯 ADD: ContextVariables for contextual UI agents
):
    """
    Starts a new group chat or resumes an existing one with unified transport support.
    
    This function now uses the centralized AG2ResumeManager for proper state persistence
    and restoration across all transport types (WebSocket, SimpleTransport).
    
    Key features:
    - Official AG2 resume patterns implementation
    - Transport-agnostic persistence
    """
    
    # Start orchestration
    chat_logger.info(f"Starting group chat orchestration for {workflow_name}")
    workflow_logger.info(f"Chat: {chat_id} | Enterprise: {enterprise_id}")
    
    orchestration_start_time = time.time()
    
    # VE-style resume check using workflow_name
    can_resume = await mongodb_manager.can_resume_chat(chat_id, enterprise_id, workflow_name)
    
    if can_resume:
        chat_logger.info(f"🔄 Resumable {workflow_name} session found for {chat_id}")
        
        # Load resume data with workflow_name
        success, resume_data = await mongodb_manager.resume_chat(chat_id, enterprise_id, workflow_name)
        
        if success and resume_data:
            # Check if already complete (VE pattern)
            if resume_data.get("already_complete"):
                status = resume_data.get("status", 0)
                chat_logger.info(f"✅ {workflow_name.title()} workflow already completed with status {status}")
                
                # Send completion message to WebSocket if available (VE pattern)
                if hasattr(manager, 'groupchat') and hasattr(manager.groupchat, 'agents'):
                    # Find transport for WebSocket communication
                    from core.transport.simple_transport import SimpleTransport
                    transport = SimpleTransport._get_instance()
                    if transport:
                        await transport.send_simple_text_message(
                            f"{workflow_name.title()} workflow already completed successfully.",
                            "system"
                        )
                return
            
            # Resume active conversation (VE pattern)
            conversation = resume_data.get("conversation", [])
            state = resume_data.get("state", {})
            status = resume_data.get("status", 0)
            
            chat_logger.info(f"🔄 Resuming {workflow_name} conversation with {len(conversation)} messages, status {status}")
            
            # Restore AG2 state if manager available
            if hasattr(manager, "groupchat") and conversation:
                # Convert conversation back to AG2 messages format
                ag2_messages = []
                for msg in conversation:
                    ag2_messages.append({
                        "content": msg.get("content", ""),
                        "role": "assistant",
                        "name": msg.get("sender", "unknown")
                    })
                
                manager.groupchat.messages = ag2_messages
                chat_logger.info(f"✅ Restored {len(ag2_messages)} messages to {workflow_name} groupchat")
                
                # Set current speaker if available (VE pattern)
                current_speaker = state.get("current_speaker")
                if current_speaker and hasattr(manager.groupchat, '_last_speaker_name'):
                    manager.groupchat._last_speaker_name = current_speaker
                    chat_logger.info(f"🎭 Restored last speaker: {current_speaker}")
                
                # Resume with WebSocket consideration (VE pattern)
                determined_max_turns = max_turns or None
                
                # Send resume notification to WebSocket (VE pattern)
                from core.transport.simple_transport import SimpleTransport
                transport = SimpleTransport._get_instance()
                if transport:
                    await transport.send_simple_text_message(
                        f"Resuming {workflow_name} conversation from previous session...",
                        "system"
                    )
                
                # Continue conversation
                if determined_max_turns:
                    await manager.a_run_group_chat(max_turns=determined_max_turns)
                else:
                    await manager.a_run_group_chat()
                
                orchestration_time = (time.time() - orchestration_start_time) * 1000
                chat_logger.info(f"🔄 {workflow_name.title()} resume completed in {orchestration_time:.2f}ms")
                
                return  # Resume completed successfully
        else:
            chat_logger.warning(f"❌ Resume failed for {workflow_name} workflow: {chat_id}")
    
    # New session path (VE pattern - set status to 0 for new workflows)
    chat_logger.info(f"🆕 Starting new {workflow_name} session for {chat_id}")
    
    # Initialize workflow with status 0 (VE pattern)
    await mongodb_manager.update_workflow_status(chat_id, enterprise_id, 0, workflow_name)
    
    # Budget capability initialization
    from ..capabilities import get_budget_capability
    
    budget_capability = get_budget_capability(chat_id, enterprise_id, workflow_name, user_id)
    budget_info = await budget_capability.initialize_budget()
    
    # Extract token_manager if commercial mode
    token_manager = getattr(budget_capability, 'token_manager', None)
    if token_manager:
        chat_logger.debug(f"🪙 [BUDGET] Token manager available: {type(token_manager).__name__}")
    
    # Initialize AG2-native token tracking for observability
    token_tracker = get_token_tracker(chat_id, enterprise_id, user_id or "unknown")
    
    chat_logger.info(f"Budget capability initialized: {budget_info.get('budget_type', 'unknown')}")
    if budget_info.get('is_free_trial'):
        chat_logger.info(f"Free trial: {budget_info.get('free_loops_remaining', 0)} loops remaining")
    else:
        chat_logger.info(f"Mode: {budget_info.get('budget_type', 'unknown')}")

    # Tool registration system
    if (
        hasattr(manager, "register_for_execution")
        and not getattr(manager, "_workflow_tools_registered", False)
    ):
        try:
            # Import our new modular tool registry
            from .tool_registry import WorkflowToolRegistry, ToolTrigger
            
            # Initialize tool registry for this workflow
            tool_registry = WorkflowToolRegistry(workflow_name)
            
            tool_registry.load_configuration()
            
            # Execute pre-groupchat lifecycle tools
            await tool_registry.execute_lifecycle_tools(
                ToolTrigger.BEFORE_GROUPCHAT_START,
                {"chat_id": chat_id, "enterprise_id": enterprise_id, "user_id": user_id}
            )
            
            # Register agent tools automatically from JSON configuration
            if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
                agents_list = manager.groupchat.agents
                
                tool_registry.register_agent_tools(agents_list)
                
                # Store registry for lifecycle management
                setattr(manager, "_tool_registry", tool_registry)
                
                registered_count = sum(len(tools) for tools in tool_registry.agent_tools.values())
                agent_lifecycle_logger.info(f"Tool registration complete: {registered_count} total tools registered")
                
                # Log basic agent tool registration status
                for agent in agents_list:
                    tool_info = tool_registry.get_agent_tool_info(agent)
                    if tool_info['has_registered_tools']:
                        agent_lifecycle_logger.info(f"Agent '{tool_info['agent_name']}': tools registered")
                
                chat_logger.info(f"Tool registration complete: {registered_count} agent tools from workflow.json")
            else:
                workflow_logger.warning("No agents found for tool registration")
            
            setattr(manager, "_workflow_tools_registered", True)
            
        except Exception as e:
            workflow_logger.error(f"Tool registration failed: {e}")
            chat_logger.error(f"Failed to register workflow tools: {e}")
            # Fallback to minimal core functionality
            chat_logger.warning("Proceeding without advanced tool registration")
            setattr(manager, "_workflow_tools_registered", True)
    else:
        logger.debug("Tool registration skipped (already registered or not supported)")

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
            config = workflow_config.get_config(workflow_name)
            human_in_loop = config.get("human_in_the_loop", False)
            auto_start = config.get("auto_start", False)
            initiating_agent_name = config.get("initiating_agent", "user")
            
            chat_logger.info(f"🎯 [CONFIG] Workflow '{workflow_name}' configuration:")
            chat_logger.info(f"   • human_in_the_loop: {human_in_loop}")
            chat_logger.info(f"   • auto_start: {auto_start}")
            chat_logger.info(f"   • initiating_agent: {initiating_agent_name}")
            
            # ------------------------------------------------------------------
            # Auto-Generate UserProxyAgent (if needed)
            # ------------------------------------------------------------------
            
            # Check if UserProxyAgent already exists in GroupChat
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
                    
                    # Note: User input is now handled via WebSocket transport
                    chat_logger.debug(f"🌐 [CONFIG] User input will be routed via WebSocket transport")
                    break
            
            # AUTO-GENERATION LOGIC: Create UserProxyAgent if needed
            # Note: UserProxyAgent may have already been created in orchestration phase for handoffs
            if human_in_loop and not has_user_proxy:
                chat_logger.info(f"🚀 [AUTO-GEN] human_in_the_loop=true but no UserProxyAgent found in GroupChat")
                chat_logger.info(f"🔧 [AUTO-GEN] Auto-generating UserProxyAgent for workflow '{workflow_name}'")
                
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 🎯 CUSTOMIZATION POINT #1: UserProxyAgent Creation
                # ═══════════════════════════════════════════════════════════════════════════════════
                # 
                # 📍 WHERE: Modify the UserProxyAgent creation below
                # 
                # 🔧 CUSTOMIZATION OPTIONS:
                #   • Change agent name (e.g., f"{workflow_name}_user", "enterprise_user")
                #   • Modify system_message based on workflow_name, enterprise_id, user_role
                #   • Set different human_input_mode ("ALWAYS", "NEVER", "TERMINATE")
                #   • Add code_execution_config for specific workflows
                #   • Include custom llm_config for enterprise requirements
                #   • Add description field for better agent identification
                #
                # 💡 ENTERPRISE EXAMPLES:
                #   • if enterprise_id == "healthcare": system_message = "You are a healthcare..."
                #   • if workflow_name == "legal": name = "legal_reviewer"
                #   • if user_role == "admin": human_input_mode = "TERMINATE"
                #
                # 🏗️ WORKFLOW-SPECIFIC EXAMPLES:
                #   • if workflow_name == "generator": system_message = "You are creating..."
                #   • if workflow_name == "analyzer": code_execution_config = {"use_docker": True}
                #   • if "secure" in workflow_name: add additional validation
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
                #   • Add workflow-specific tools based on workflow_name
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
                # • CommunicationChannel handles transport-agnostic user input (WebSocket)
                # • No custom a_get_human_input() override needed - AG2 handles it natively
                # • IOStream automatically streams UserProxy responses to frontend
                # 
                # 🔧 HOW IT WORKS:
                # 1. UserProxy calls AG2's native input system when human_input_mode="ALWAYS"
                # 2. Transport layer (ag2_websocket_adapter) handles user input
                # 3. Frontend sends user input via WebSocket message
                # 4. Backend routes input back to waiting UserProxy agent
                # 5. UserProxy continues conversation with user input
                # 
                # 📡 FRONTEND INTEGRATION:
                # • No special component needed for basic UserProxy interaction
                # • UI input automatically routed via CommunicationChannel
                # • UserProxy responses stream to frontend via IOStream
                # • Special UI components only needed for complex user tools
                # ═══════════════════════════════════════════════════════════════════════════════════
                
                chat_logger.info(f"🔗 [AUTO-GEN] UserProxy transport integration: WebSocket-ready")
                chat_logger.info(f"📡 [AUTO-GEN] User input will be handled via WebSocket transport")
                
                
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
                    
                # Log initiating agent information
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
            chat_logger.error(f"❌ [CONFIG] Failed to configure workflow settings for '{workflow_name}': {e}")
            chat_logger.info("🔄 [CONFIG] Proceeding with default agent configuration")

    # ------------------------------------------------------------------
    # Existing logic
    # ------------------------------------------------------------------
    before_reply_hook   = None
    before_send_hook    = None
    streaming_manager   = None  # Initialize to avoid UnboundLocalError in finally block
    chat_start          = time.time()

    # Initialize lifecycle tool hooks if we have a tool registry
    if hasattr(manager, "_tool_registry"):
        tool_registry = getattr(manager, "_tool_registry")
        
        # Create hooks that call lifecycle tools
        async def lifecycle_before_reply_hook(sender, messages, recipient, silent):
            """Hook that triggers before_agent_speaks lifecycle tools"""
            try:
                # Execute lifecycle tools that expect AG2 hook parameters
                tools = tool_registry.get_lifecycle_tools(ToolTrigger.BEFORE_AGENT_SPEAKS)
                for tool in tools:
                    try:
                        function = tool.load_function()
                        # Call with AG2 hook signature (sender, messages, recipient, silent)
                        if asyncio.iscoroutinefunction(function):
                            await function(sender, messages, recipient, silent)
                        else:
                            function(sender, messages, recipient, silent)
                        logger.debug(f"✅ Executed lifecycle tool '{function.__name__}' for before_agent_speaks")
                    except Exception as e:
                        logger.error(f"❌ Failed to execute lifecycle tool '{tool.path}': {e}")
            except Exception as e:
                logger.error(f"❌ Error executing before_agent_speaks lifecycle tools: {e}")
            return messages
            
        async def lifecycle_before_send_hook(sender, message, recipient, silent):
            """Hook that triggers after_agent_speaks lifecycle tools"""
            try:
                # Execute lifecycle tools that expect AG2 hook parameters
                tools = tool_registry.get_lifecycle_tools(ToolTrigger.AFTER_AGENT_SPEAKS)
                for tool in tools:
                    try:
                        function = tool.load_function()
                        # Call with AG2 hook signature (sender, message, recipient, silent)
                        if asyncio.iscoroutinefunction(function):
                            await function(sender, message, recipient, silent)
                        else:
                            function(sender, message, recipient, silent)
                        logger.debug(f"✅ Executed lifecycle tool '{function.__name__}' for after_agent_speaks")
                    except Exception as e:
                        logger.error(f"❌ Failed to execute lifecycle tool '{tool.path}': {e}")
            except Exception as e:
                logger.error(f"❌ Error executing after_agent_speaks lifecycle tools: {e}")
            return message
        
        # Set the hooks to enable lifecycle tools
        before_reply_hook = lifecycle_before_reply_hook
        before_send_hook = lifecycle_before_send_hook
        chat_logger.info("🎯 [CORE] Lifecycle tool hooks enabled for agent communication tracking")

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
        
        # 📊 Clean summary of tool registration status (always enabled)
        if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
            agents_with_tools = 0
            total_tools = 0
            for agent in manager.groupchat.agents:
                if hasattr(agent, '_function_map') and agent._function_map:
                    agents_with_tools += 1
                    total_tools += len(agent._function_map)
            
            chat_logger.info(f"Tool registration summary: {agents_with_tools}/{len(manager.groupchat.agents)} agents have tools ({total_tools} total)")
        
        # Create AG2 streaming manager for real-time streaming
        # This captures agent output and sends it to WebSocket via SimpleTransport
        streaming_manager = AG2StreamingManager(chat_id, enterprise_id)
        streaming_manager.setup_streaming()  # Sets up global IOStream, no need to store return value
        
        # ═══════════════════════════════════════════════════════════════════════════════════
        # 🎯 HOOK REGISTRATION: Response Time Tracking Hooks
        # ═══════════════════════════════════════════════════════════════════════════════════
        # 
        # ⚠️ CRITICAL: AG2 Hook Registration Best Practices
        # 
        # 🚨 NEVER DO THIS:
        #   agent.register_hook("process_all_messages_before_reply", None)  # ❌ CRASHES!
        #   agent.register_hook("process_message_before_send", None)        # ❌ CRASHES!
        # 
        # ✅ ALWAYS DO THIS:
        #   1. Create actual hook functions FIRST
        #   2. ONLY register non-None hooks
        #   3. Always validate hook functions exist before registration
        # 
        # 🔧 PROPER PATTERN:
        #   hook_func = create_some_hook()
        #   if hook_func is not None:  # ✅ Validate before registering
        #       agent.register_hook("hook_name", hook_func)
        # 
        # 📚 HOOK DOCUMENTATION:
        #   • process_all_messages_before_reply: Called before agent generates reply
        #   • process_message_before_send: Called before agent sends message
        #   • Custom hooks: See AG2 documentation for custom hook patterns
        # ═══════════════════════════════════════════════════════════════════════════════════
        
        # Create response tracking hooks
        before_reply_hook, before_send_hook = create_core_response_tracking_hooks(
            tracker=response_tracker,
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            budget_capability=budget_capability,
            agents=agents_list,
            streaming_manager=streaming_manager,
            workflow_name=workflow_name,
            token_tracker=token_tracker
        )
        chat_logger.debug(f"🔍 [HOOKS] Response tracking hooks enabled")
        # NOTE: before_reply_hook and before_send_hook are set by lifecycle hooks above (if tool registry exists)
        # Only override to None if no lifecycle hooks were created
        if not hasattr(manager, "_tool_registry"):
            before_reply_hook = None
            before_send_hook = None
        
        # Hook registration with proper validation
        if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
            if before_reply_hook is not None and before_send_hook is not None:
                # ✅ SAFE: Register lifecycle tools or response tracking hooks
                for agent in manager.groupchat.agents:
                    if hasattr(agent, "register_hook"):
                        agent.register_hook("process_all_messages_before_reply", before_reply_hook)
                        agent.register_hook("process_message_before_send", before_send_hook)
                        chat_logger.debug(f"🎯 [CORE] AG2 hooks enabled for {agent.name}")
                
                # Determine what type of hooks were registered
                if hasattr(manager, "_tool_registry"):
                    chat_logger.info("🎯 [CORE] Lifecycle tool hooks enabled for agent communication tracking")
                else:
                    chat_logger.info("🎯 [CORE] Core-level response time tracking enabled for all agents")
            else:
                # ✅ SAFE: Skip registration when hooks are None
                chat_logger.info("🔧 [CORE] AG2 hooks disabled - no lifecycle tools or response tracking")
        else:
            chat_logger.warning("⚠️ [CORE] Cannot register hooks - manager missing groupchat or agents")

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
            
            # The initiate_kwargs for the chat. The recipient is passed positionally.
            initiate_kwargs: Dict[str, Any] = {
                "message": initial_message,
            }
            if determined_max_turns:
                initiate_kwargs["max_turns"] = determined_max_turns
            
            # 🎯 CRITICAL: Add ContextVariables for contextual UI agents!
            if context_variables:
                initiate_kwargs["context_variables"] = context_variables
                chat_logger.info(f"🎯 [CORE] ContextVariables attached for contextual UI agents")
            else:
                chat_logger.debug(f"🤖 [CORE] No ContextVariables provided - UI context adjustment disabled")

            chat_logger.info(f"🚀 [CORE] Initiating chat with message: '{initial_message}'")
            
            # Safety check: Ensure all agents have proper initialization
            if hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents"):
                # Message state initialization handled by AG2 internally
                logger.debug("AG2 will handle message state initialization internally")

            # Start agent conversation
            agent_start_time = time.time()
            chat_logger.info("Starting agent conversation...")
            
            # Pre-initiation summary
            agent_count = len(manager.groupchat.agents) if hasattr(manager, 'groupchat') else 0
            chat_logger.info(f"Starting conversation: {initiating_agent.name} → {agent_count} agents (max_turns: {determined_max_turns})")
            
            # � EMERGENCY MESSAGE INITIALIZATION: Prevents IndexError in AG2
            # This ensures all agents have proper message state before AG2 processes them
            emergency_fixes_applied = 0
            for agent in manager.groupchat.agents:
                agent_name = getattr(agent, 'name', 'UNNAMED')
                
                # Ensure chat_messages exists for each agent
                if agent not in manager.chat_messages or not manager.chat_messages[agent]:
                    if agent not in manager.chat_messages:
                        manager.chat_messages[agent] = []
                    emergency_msg = {
                        "role": "user",
                        "content": initial_message or "Start the workflow",
                        "name": "emergency_safety"
                    }
                    manager.chat_messages[agent].append(emergency_msg)
                    emergency_fixes_applied += 1
                    chat_logger.debug(f"🚨 [EMERGENCY] Added safety message for agent: {agent_name}")
                
                # Ensure _oai_messages exists for each agent
                if not hasattr(manager, '_oai_messages'):
                    from collections import defaultdict
                    manager._oai_messages = defaultdict(list)
                
                if agent not in manager._oai_messages or not manager._oai_messages[agent]:
                    if agent not in manager._oai_messages:
                        manager._oai_messages[agent] = []
                    emergency_msg = {
                        "role": "user",
                        "content": initial_message or "Start the workflow",
                        "name": "emergency_safety"
                    }
                    manager._oai_messages[agent].append(emergency_msg)
                    emergency_fixes_applied += 1
            
            if emergency_fixes_applied > 0:
                chat_logger.info(f"� [CORE] Applied {emergency_fixes_applied} message initialization fixes")

            try:
                # Start the agent conversation
                await initiating_agent.a_initiate_chat(
                    recipient=manager,
                    message=initial_message,
                    max_turns=determined_max_turns
                )
                
                chat_logger.info(f"✅ [CORE] Agent conversation completed successfully")
                
            except Exception as e:
                chat_logger.error(f"❌ [CORE] Agent conversation failed: {e}")
                deep_logger.error(f"🔬 [DEEP-LOG] Exception type: {type(e).__name__}")
                deep_logger.error(f"🔬 [DEEP-LOG] Exception details: {str(e)}")
                raise

            # Performance metrics
            agent_response_time = (time.time() - agent_start_time) * 1000
            orchestration_total_time = (time.time() - orchestration_start_time) * 1000
            
            log_performance_metric(
                metric_name="agent_conversation_duration",
                value=agent_response_time,
                unit="ms",
                context={
                    "enterprise_id": enterprise_id,
                    "chat_id": chat_id,
                    "initiating_agent": initiating_agent.name,
                    "max_turns": str(determined_max_turns),
                },
            )
            
            log_performance_metric(
                metric_name="total_orchestration_duration",
                value=orchestration_total_time,
                unit="ms",
                context={
                    "enterprise_id": enterprise_id,
                    "chat_id": chat_id,
                    "workflow_name": workflow_name,
                },
            )
            
            chat_logger.info(f"✅ [ORCHESTRATION] Agent conversation completed in {agent_response_time:.2f}ms (total: {orchestration_total_time:.2f}ms)")
            
            # Save conversation state to database
            try:
                if hasattr(manager, 'groupchat'):
                    await mongodb_manager.save_chat_state(
                        chat_id=chat_id,
                        enterprise_id=enterprise_id,
                        workflow_name=workflow_name,
                        state_data={
                            "groupchat_agents": [agent.name for agent in manager.groupchat.agents if hasattr(agent, 'name')],
                            "conversation_duration_ms": agent_response_time,
                            "max_turns_used": determined_max_turns
                        }
                    )
                    chat_logger.info(f"💾 [PERSISTENCE] Conversation state saved to database")
                    
                    # Save token usage if tracker has data
                    if token_tracker:
                        try:
                            # Get usage data from agents
                            agents_list = manager.groupchat.agents if hasattr(manager.groupchat, 'agents') else []
                            session_usage = token_tracker.get_usage_for_business_logic(agents_list)
                            
                            if session_usage and session_usage.get('total_tokens', 0) > 0:
                                await mongodb_manager.update_token_usage(
                                    chat_id=chat_id,
                                    enterprise_id=enterprise_id,
                                    session_id=session_usage.get('session_id', str(uuid.uuid4())),
                                    usage_data={
                                        **session_usage,
                                        "total_turns": len(manager.groupchat.messages) if hasattr(manager.groupchat, 'messages') else 0,
                                        "conversation_duration_ms": agent_response_time
                                    }
                                )
                                chat_logger.info(f"💰 [TOKEN-USAGE] Token usage saved: {session_usage.get('total_tokens', 0)} tokens, ${session_usage.get('total_cost', 0.0):.4f}")
                            else:
                                chat_logger.info(f"💰 [TOKEN-USAGE] No token usage data to save (0 tokens)")
                        except Exception as token_e:
                            chat_logger.error(f"❌ [TOKEN-USAGE] Failed to save token usage: {token_e}")
                else:
                    chat_logger.warning(f"⚠️ [PERSISTENCE] No groupchat found to save")
            except Exception as e:
                chat_logger.error(f"❌ [PERSISTENCE] Failed to save conversation state: {e}")
            
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

            # State restoration is now handled by the frontend via WebSocket transport

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
            
            # Save resumed conversation state to database
            try:
                if hasattr(manager, 'groupchat'):
                    await mongodb_manager.save_chat_state(
                        chat_id=chat_id,
                        enterprise_id=enterprise_id,
                        workflow_name=workflow_name,
                        state_data={
                            "groupchat_agents": [agent.name for agent in manager.groupchat.agents if hasattr(agent, 'name')],
                            "resume_duration_ms": agent_response_time,
                            "max_turns_used": determined_max_turns,
                            "was_resumed": True
                        }
                    )
                    chat_logger.info(f"💾 [PERSISTENCE] Resumed conversation state saved to database")
                else:
                    chat_logger.warning(f"⚠️ [PERSISTENCE] No groupchat found to save on resume")
            except Exception as e:
                chat_logger.error(f"❌ [PERSISTENCE] Failed to save resumed conversation state: {e}")
            
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
        # Execute end-of-chat lifecycle tools
        if hasattr(manager, "_tool_registry"):
            try:
                from .tool_registry import ToolTrigger
                tool_registry = getattr(manager, "_tool_registry")
                await tool_registry.execute_lifecycle_tools(
                    ToolTrigger.END_OF_CHAT,
                    {
                        "chat_id": chat_id, 
                        "enterprise_id": enterprise_id,
                        "user_id": user_id,
                        "final_state": "completed"
                    }
                )
                chat_logger.info("🏁 [MODULAR] End-of-chat lifecycle tools executed")
            except Exception as e:
                chat_logger.error(f"❌ [MODULAR] Failed to execute end-of-chat tools: {e}")
        
        # Clean up IOStream if it was set up
        if streaming_manager:
            try:
                streaming_manager.restore_original_iostream()
                chat_logger.info("🧹 [CORE] AG2 IOStream restored")
            except Exception as e:
                logger.error(f"❌ [CORE] Error restoring IOStream: {e}")
        
        # ═══════════════════════════════════════════════════════════════════════════════════
        # 🎯 HOOK SETUP: Proper Hook Unregistration
        # ═══════════════════════════════════════════════════════════════════════════════════
        # 
        # ⚠️ CRITICAL: AG2 Hook Cleanup Best Practices
        # 
        # 🚨 NEVER DO THIS:
        #   agent.unregister_hook("hook_name", None)  # ❌ May cause issues!
        # 
        # ✅ ALWAYS DO THIS:
        #   1. Only unregister hooks that were actually registered
        #   2. Validate hooks exist before unregistering
        #   3. Use proper exception handling during cleanup
        # 
        # 🔧 PROPER CLEANUP PATTERN:
        #   if hook_func is not None and hasattr(agent, "unregister_hook"):
        #       try:
        #           agent.unregister_hook("hook_name", hook_func)
        #       except Exception as e:
        #           logger.warning(f"Hook cleanup failed: {e}")
        # ═══════════════════════════════════════════════════════════════════════════════════
        
        # Clean up response tracking hooks (only if they were registered)
        if (before_reply_hook is not None and before_send_hook is not None and 
            hasattr(manager, "groupchat") and hasattr(manager.groupchat, "agents")):
            
            for agent in manager.groupchat.agents:
                if hasattr(agent, "unregister_hook"):
                    try:
                        agent.unregister_hook("process_all_messages_before_reply", before_reply_hook)
                        agent.unregister_hook("process_message_before_send", before_send_hook)
                        chat_logger.debug(f"🧹 [CORE] Response hooks cleaned up for {agent.name}")
                    except Exception as e:
                        chat_logger.warning(f"⚠️ [CORE] Hook cleanup failed for {agent.name}: {e}")
            
            chat_logger.info("🧹 [CORE] Response tracking hooks cleaned up")
        else:
            chat_logger.debug("🧹 [CORE] No hooks to clean up (hooks were None or not registered)")

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
        
        chat_logger.info(f"🎉 [ORCHESTRATION] Group chat orchestration completed successfully")
        chat_logger.info(f"📊 [ORCHESTRATION] Total execution time: {chat_time:.2f}ms")

# ==============================================================================
# WORKFLOW ORCHESTRATION FUNCTIONS
# ==============================================================================

async def run_workflow_orchestration(
    workflow_name: str,
    llm_config: Dict[str, Any],
    enterprise_id: str,
    chat_id: str,
    user_id: Optional[str] = None,
    initial_message: Optional[str] = None,
    agents_factory: Optional[Any] = None,
    context_factory: Optional[Any] = None,
    handoffs_factory: Optional[Any] = None
) -> None:
    """
    Universal workflow orchestration function that handles all the standard workflow setup.
    
    This eliminates repetitive code from OrchestrationPattern.py files by standardizing:
    - Tool discovery and registration  
    - GroupChat/GroupChatManager creation with configurable orchestration patterns
    - Agent setup and configuration
    - Performance logging and metrics
    - Error handling patterns
    
    ORCHESTRATION PATTERNS SUPPORTED:
    - DefaultPattern: Uses "auto" speaker selection with optional handoffs
    - AutoPattern: Uses "auto" speaker selection without handoffs
    - RoundRobinPattern: Sequential agent rotation
    - RandomPattern: Random agent selection
    - ManualPattern: Manual speaker selection
    
    Args:
        workflow_name: Type of workflow (e.g., "generator", "analyzer")
        llm_config: LLM configuration
        enterprise_id: Enterprise identifier
        chat_id: Chat identifier
        user_id: User identifier (optional)
        initial_message: Initial message (optional)
        agents_factory: Function to create agents - must return Dict[str, Agent]
        context_factory: Function to get context - must return context object
        handoffs_factory: Function to wire handoffs - takes agents dict
    """
    
    # SimpleTransport singleton is used for all communication
    from core.transport.simple_transport import SimpleTransport
    transport = SimpleTransport._get_instance()
    if not transport:
        raise RuntimeError(f"SimpleTransport instance not available for {workflow_name} workflow")
    
    if not agents_factory:
        raise ValueError(f"agents_factory is required for {workflow_name} workflow")
    
    start_time = time.time()
    workflow_name_upper = workflow_name.upper()
    
    # Initialize workflow-specific loggers
    from logs.logging_config import get_business_logger
    business_logger = get_business_logger(f"{workflow_name}_orchestration")
    
    try:
        # Get workflow configuration
        from ..workflow.workflow_config import workflow_config
        config = workflow_config.get_config(workflow_name)
        max_turns = config.get("max_turns", 50)
        initiating_agent_name = config.get("initiating_agent", "UserProxyAgent")
        orchestration_pattern = config.get("orchestration_pattern", "AutoPattern")
        initiate_handoffs = config.get("initiate_handoffs", True)
        
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting workflow orchestration:")
        business_logger.info(f"   • max_turns: {max_turns}")
        business_logger.info(f"   • orchestration_pattern: {orchestration_pattern}")
        business_logger.info(f"   • initiate_handoffs: {initiate_handoffs}")

        # Determine final initial message early for accurate logging
        final_initial_message = (
            config.get("initial_message") or 
            initial_message
        )
        
        # If still no message, provide a generic fallback
        if not final_initial_message:
            final_initial_message = "You have been tasked with an assignment. Please proceed per your instructions in your system message within the context of the context_variables."
        
        # Log accurate initial message information
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_STARTED",
            description=f"{workflow_name} workflow orchestration initialized",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "final_message_determined": True,
                "final_message_source": (
                    "workflow_json_initial" if config.get("initial_message") else
                    "user_provided" if initial_message else
                    "fallback_default"
                ),
                "final_message_preview": final_initial_message[:100] + "..." if len(final_initial_message) > 100 else final_initial_message
            }
        )
        
        business_logger.info(f"🚀 [{workflow_name_upper}] Starting workflow orchestration (max_turns: {max_turns})")

        # 1. Load concept from database
        concept_start = time.time()
        business_logger.debug("📊 Loading concept data...")
        
        concept_data = await mongodb_manager.find_latest_concept_for_enterprise(enterprise_id)
        concept_load_time = (time.time() - concept_start) * 1000
        
        log_performance_metric(
            metric_name="concept_data_load_duration",
            value=concept_load_time,
            unit="ms",
            context={
                "enterprise_id": enterprise_id,
                "concept_found": concept_data is not None
            }
        )
        
        if concept_data:
            business_logger.info(f"✅ Concept loaded: {concept_data.get('ConceptCode', 'unknown')}")
        else:
            business_logger.warning("⚠️ No concept data found")

        # 2. Build context (if context factory provided)
        context = None
        if context_factory:
            business_logger.debug("🔧 Building context...")
            context = context_factory(concept_data)
            business_logger.debug(f"✅ Context variables: {list(context.data.keys()) if hasattr(context, 'data') else 'unknown'}")

        # 3. Define agents using provided factory
        agents_start = time.time()
        business_logger.debug(f"🤖 [{workflow_name_upper}] Defining agents...")
        
        agents = await agents_factory()
        
        agents_build_time = (time.time() - agents_start) * 1000
        log_performance_metric(
            metric_name="agents_definition_duration", 
            value=agents_build_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "agent_count": len(agents)}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Agents defined: {len(agents)} total")

        # 4. Register tools using modular tool registry
        tools_start = time.time()
        business_logger.info("🔧 Registering tools using modular tool registry...")
        
        tool_registry = WorkflowToolRegistry(workflow_name)
        tool_registry.load_configuration()
        tool_registry.register_agent_tools(list(agents.values()))
        
        tools_registration_time = (time.time() - tools_start) * 1000
        log_performance_metric(
            metric_name="modular_tools_registration_duration",
            value=tools_registration_time,
            unit="ms",
            context={"workflow_name": workflow_name}
        )
        business_logger.info(f"✅ [{workflow_name_upper}] Modular tool registration completed")

        # 5. Create GroupChatManager using AG2 directly with orchestration pattern
        groupchat_manager_start = time.time()
        business_logger.debug(f"⚙️ [{workflow_name_upper}] Creating GroupChat and GroupChatManager...")
        
        from autogen import GroupChat, GroupChatManager
        
        # Map orchestration patterns to AG2 speaker selection methods
        if orchestration_pattern == "DefaultPattern":
            speaker_selection_method = "auto"           # Uses handoffs + auto selection
        elif orchestration_pattern == "AutoPattern":
            speaker_selection_method = "auto"           # Auto selection without handoffs
        elif orchestration_pattern == "RoundRobinPattern":
            speaker_selection_method = "round_robin"    # Sequential agent rotation
        elif orchestration_pattern == "RandomPattern":
            speaker_selection_method = "random"         # Random agent selection
        elif orchestration_pattern == "ManualPattern":
            speaker_selection_method = "manual"         # Manual speaker selection
        else:
            speaker_selection_method = "auto"           # Default fallback
        
        business_logger.info(f"🎯 [{workflow_name_upper}] Orchestration: {orchestration_pattern} → speaker_selection: {speaker_selection_method}")
        
        # Create the GroupChat with pattern-based configuration
        groupchat = GroupChat(
            agents=list(agents.values()),
            messages=[],
            max_round=max_turns,
            speaker_selection_method=speaker_selection_method
        )
        
        # Register handoffs for DefaultPattern if enabled
        if orchestration_pattern == "DefaultPattern" and initiate_handoffs and handoffs_factory:
            business_logger.info(f"🔄 [{workflow_name}] Initializing handoffs for DefaultPattern orchestration")
            # Use handoffs factory to wire handoffs
            try:
                handoffs_factory(agents)
                business_logger.info(f"✅ [{workflow_name}] Handoffs registered successfully")
            except Exception as e:
                business_logger.warning(f"⚠️ [{workflow_name}] Handoffs registration failed: {e}")
        elif orchestration_pattern == "DefaultPattern" and initiate_handoffs:
            business_logger.info(f"🔄 [{workflow_name}] DefaultPattern orchestration enabled but no handoffs_factory provided")
        
        # Create the GroupChatManager, which will also serve as the chat manager
        # The GroupChatManager is an agent and can be part of the groupchat agents list
        manager = GroupChatManager(
            groupchat=groupchat, 
            llm_config=llm_config
        )
        
        # Add the manager to the list of agents if it's not already there
        # This allows the manager to participate or be addressed in the conversation
        if manager not in groupchat.agents:
            groupchat.agents.append(manager)
            business_logger.info(f"✅ [{workflow_name_upper}] GroupChatManager added to the agent list.")

        groupchat_manager_time = (time.time() - groupchat_manager_start) * 1000
        log_performance_metric(
            metric_name="groupchat_manager_creation_duration",
            value=groupchat_manager_time,
            unit="ms",
            context={"enterprise_id": enterprise_id}
        )
        business_logger.info(f"✅ [{workflow_name}] GroupChat and GroupChatManager created")

        # 6. Always create UserProxyAgent (with startup_mode-based human_input_mode)
        # UserProxyAgent is always needed as the default initiating agent
        user_proxy_exists = any(agent.name == "user" for agent in agents.values() if hasattr(agent, 'name'))
        
        if not user_proxy_exists:
            startup_mode = config.get("startup_mode", "UserDriven")  # UserDriven, AgentDriven, BackendOnly
            
            # Set human_input_mode based on startup_mode
            if startup_mode == "BackendOnly":
                human_input_mode = "NEVER"
                business_logger.info(f"🤖 [{workflow_name}] Creating UserProxyAgent with human_input_mode=NEVER (BackendOnly)")
            elif startup_mode == "AgentDriven":
                human_input_mode = "TERMINATE"  # Only when termination needed
                business_logger.info(f"🤖 [{workflow_name}] Creating UserProxyAgent with human_input_mode=TERMINATE (AgentDriven)")
            else:  # UserDriven (default)
                human_input_mode = "ALWAYS"
                business_logger.info(f"🤖 [{workflow_name}] Creating UserProxyAgent with human_input_mode=ALWAYS (UserDriven)")
            
            from autogen import UserProxyAgent
            
            user_proxy_agent = UserProxyAgent(
                name="user",
                human_input_mode=human_input_mode,
                code_execution_config=False,
                system_message="You are a user interacting with a multi-agent workflow system. Provide input, feedback, and guidance as needed.",
                llm_config=False,
            )
            
            # Add to agents dictionary
            agents["user"] = user_proxy_agent
            business_logger.info(f"✅ [{workflow_name}] UserProxyAgent created with startup_mode={startup_mode}")

        # 7. Wire handoffs (if handoffs factory provided)
        if handoffs_factory:
            business_logger.debug(f"🔗 [{workflow_name_upper}] Wiring handoffs...")
            handoffs_factory(agents)
            business_logger.info(f"✅ [{workflow_name_upper}] Handoffs wired")

        # 8. Get initiating agent and start chat
        # Get initiating agent
        initiating_agent = agents.get(initiating_agent_name)
        if not initiating_agent:
            raise ValueError(f"Critical: {initiating_agent_name} not found, cannot initiate workflow.")
        
        # Log the approach
        if config.get("initial_message"):
            business_logger.info(f"🎯 [{workflow_name_upper}] Starting with {initiating_agent_name} (workflow initial_message)")
        elif initial_message:
            business_logger.info(f"🎯 [{workflow_name_upper}] Starting with {initiating_agent_name} (user-provided message)")
        else:
            business_logger.info(f"🎯 [{workflow_name_upper}] Starting with {initiating_agent_name} (generic fallback prompt)")

        # 9. Start or resume chat (single entry point)
        chat_start = time.time()
        await _start_or_resume_group_chat(
            manager=manager,
            initiating_agent=initiating_agent,
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            user_id=user_id,
            initial_message=final_initial_message,
            max_turns=max_turns,
            workflow_name=workflow_name,
            context_variables=context
        )
        chat_time = (time.time() - chat_start) * 1000
        log_performance_metric(
            metric_name="groupchat_execution_duration",
            value=chat_time,
            unit="ms",
            context={"enterprise_id": enterprise_id, "chat_id": chat_id}
        )
        business_logger.info(f"🎉 [{workflow_name_upper}] Workflow completed in {chat_time:.2f}ms")
        
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_COMPLETED",
            description=f"{workflow_name} workflow orchestration completed successfully",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "total_duration_seconds": (time.time() - start_time),
                "agent_count": len(agents)
            }
        )
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ [{workflow_name_upper}] Workflow orchestration failed after {duration:.2f}s: {e}", exc_info=True)
        log_business_event(
            event_type=f"{workflow_name_upper}_WORKFLOW_FAILED",
            description=f"{workflow_name} workflow orchestration failed",
            context={
                "enterprise_id": enterprise_id,
                "chat_id": chat_id,
                "error": str(e),
                "duration_seconds": duration
            },
            level="ERROR"
        )
        raise
    finally:
        business_logger.debug(f"🧹 [{workflow_name_upper}] Workflow cleanup completed")


# =============================================================================
# END WORKFLOW ORCHESTRATION FUNCTIONS  
# =============================================================================