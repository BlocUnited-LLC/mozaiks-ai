# ==============================================================================
# FILE: core/transport/ag2_iostream.py  
# DESCRIPTION: AG2 IOStream implementation aligned with official AG2 documentation
# ==============================================================================
#
# 🎯 AG2 OFFICIAL PATTERN ALIGNMENT:
# ==================================
# Based on AG2 documentation (https://docs.ag2.ai/latest/docs/use-cases/notebooks/notebooks/agentchat_websockets/):
#
# 1. IOWebsockets.run_server_in_thread(on_connect=on_connect, port=8080)
# 2. on_connect function receives IOWebsockets instance automatically  
# 3. iostream.input() to receive client messages
# 4. llm_config = {"stream": True} for agent streaming
# 5. No manual IOStream.set_global_default() needed
#
# IMPORTANT: AG2 manages IOStream automatically within the on_connect context
# ==============================================================================
import asyncio
import json
import uuid
from typing import Optional, Any, List
from datetime import datetime

try:
    from autogen.events.base_event import BaseEvent  # type: ignore
    from autogen.io.base import IOStreamProtocol  # type: ignore
    from autogen.io import IOStream  # type: ignore
    from autogen.io.websockets import IOWebsockets  # type: ignore
    AG2_AVAILABLE = True
except ImportError:
    # Fallback if autogen imports are not available
    AG2_AVAILABLE = False
    class IOStreamProtocol:
        pass
    class BaseEvent:
        pass
    class IOStream:
        @staticmethod
        def get_default():
            return None
        @staticmethod
        def set_global_default(iostream):
            pass
    class IOWebsockets:
        @staticmethod
        def run_server_in_thread(on_connect=None, port=8080):
            return None

from logs.logging_config import get_chat_logger

# Import SimpleTransport for user input collection
try:
    from .simple_transport import SimpleTransport
except ImportError:
    # Will be imported at runtime if needed
    SimpleTransport = None

# Get loggers (logging setup happens in main app)
logger = get_chat_logger("ag2_iostream")
chat_logger = get_chat_logger("agent_output")


def _load_config_list_sync() -> List[dict]:
    """
    Synchronously load LLM config list with robust error handling.
    
    This function handles the async nature of core_config in a sync context,
    with multiple fallback strategies for production reliability.
    
    Returns:
        List[dict]: LLM configuration list with model, api_key, and optional price
    """
    try:
        from core.core_config import _load_raw_config_list
        import asyncio
        import concurrent.futures
        
        try:
            # Method 1: Try to use existing event loop with thread
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug("[AG2] Event loop running, using thread executor")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _load_raw_config_list())
                    config_list = future.result(timeout=10)
                    logger.info(f"[AG2] ✅ Loaded {len(config_list)} models via thread (production config)")
                    return config_list
            else:
                # Method 2: No running loop, safe to use asyncio.run
                logger.debug("[AG2] No running loop, using asyncio.run")
                config_list = asyncio.run(_load_raw_config_list())
                logger.info(f"[AG2] ✅ Loaded {len(config_list)} models via asyncio.run (production config)")
                return config_list
                
        except (RuntimeError, OSError) as e:
            logger.debug(f"[AG2] Event loop issue: {e}, trying fallback")
            # Method 3: Force new event loop
            config_list = asyncio.run(_load_raw_config_list())
            logger.info(f"[AG2] ✅ Loaded {len(config_list)} models (fallback)")
            return config_list
            
    except ImportError as e:
        logger.warning(f"[AG2] Could not import core_config: {e}")
    except Exception as e:
        logger.warning(f"[AG2] Error loading config from database: {e}")
    
    # Fallback 1: Environment variables
    try:
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and api_key.strip():
            config_list = [{"model": "gpt-4o-mini", "api_key": api_key.strip()}]
            logger.info("[AG2] ✅ Using OPENAI_API_KEY environment variable")
            return config_list
    except Exception as e:
        logger.warning(f"[AG2] Environment fallback failed: {e}")
    
    # Fallback 2: Mock config for testing (should not happen in production)
    logger.error("[AG2] ⚠️  Using mock configuration - CHECK YOUR CONFIGURATION!")
    logger.error("[AG2] Make sure Azure Key Vault or OPENAI_API_KEY is properly configured")
    return [{"model": "gpt-4o-mini", "api_key": "mock_key"}]


class AG2StreamingIOStream(IOStreamProtocol):
    """
    AG2-compliant IOStream implementation with TokenManager integration.
    
    IMPORTANT: This class should work WITH AG2's built-in streaming, not replace it.
    AG2's llm_config["stream"] = True handles the LLM streaming, while this handles
    the IO layer to your WebSocket transport and workflow management.
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default"):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_name = workflow_name
        
        # Streaming state - simplified to work with AG2's streaming
        self.current_message_id: Optional[str] = None
        self.current_agent_name: Optional[str] = None
        
        # Initialize TokenManager for workflow integration
        self.token_manager: Optional[Any] = None  # TokenManager will be imported dynamically
        self._initialize_token_manager()
        
        # Remove custom streaming logic - let AG2 handle it
        # AG2 will stream content directly through print() calls when "stream": True
    
    def _initialize_token_manager(self):
        """Initialize TokenManager for workflow integration."""
        try:
            from core.data.token_manager import TokenManager
            self.token_manager = TokenManager(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                user_id=self.user_id,
                workflow_name=self.workflow_name
            )
            logger.info(f"🔧 TokenManager initialized for AG2 iostream: {self.chat_id} ({self.workflow_name})")
        except Exception as e:
            logger.error(f"❌ Failed to initialize TokenManager: {e}")
            self.token_manager = None
    
    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        """
        AG2-compliant print method with TokenManager integration.
        
        When AG2 has "stream": True in llm_config, it will call this method
        with already-streamed content. We forward it to WebSocket and track in TokenManager.
        """
        # Convert the print arguments to text (same as standard print)
        content = sep.join(str(obj) for obj in objects) + end
        
        if not content.strip():  # Skip empty content
            return
        
        # Log agent output for tracking
        agent_name = getattr(self, '_current_agent_name', 'Unknown Agent')
        
        # Track message in TokenManager for workflow management
        if self.token_manager:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.token_manager.add_message(
                        sender=agent_name,
                        content=content.strip(),
                        tokens_used=0,  # Tokens tracked separately via gather_usage_summary
                        cost=0.0
                    ))
            except Exception as e:
                logger.warning(f"Failed to track message in TokenManager: {e}")
        
        # Clean content for readability
        clean_content = content.strip()
        if len(clean_content) > 500:
            # Show beginning and end for long messages
            preview = f"{clean_content[:250]}...{clean_content[-100:]}"
        else:
            preview = clean_content
        
        # Log with readable formatting
        chat_logger.info(f"🤖 AGENT MESSAGE | Chat: {self.chat_id} | Workflow: {self.workflow_name}")
        chat_logger.info(f"   👤 Agent: {agent_name}")
        chat_logger.info(f"   💬 Content: {preview}")
        
        # Log full content if it's JSON or structured data
        if clean_content.startswith('{') and clean_content.endswith('}'):
            try:
                import json
                parsed = json.loads(clean_content)
                if isinstance(parsed, dict):
                    # Log key information from structured responses
                    if 'agent_list' in parsed:
                        agent_count = len(parsed['agent_list'])
                        chat_logger.info(f"   📋 Agent List Generated: {agent_count} agents")
                    elif 'context_variables' in parsed:
                        var_count = len(parsed['context_variables'])
                        chat_logger.info(f"   🎯 Context Variables Generated: {var_count} variables")
            except Exception as e:
                # Catch all JSON-related errors
                logger.warning(f"Error parsing JSON content: {e}")
        
        # Send content directly to WebSocket (AG2 handles the streaming)
        # Use proper async task handling for production
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create task
                asyncio.create_task(self._send_to_websocket(content))
            else:
                # We're not in an async context, run in new loop
                asyncio.run(self._send_to_websocket(content))
        except Exception as e:
            logger.error(f"Failed to send content to WebSocket: {e}")
            # Fallback: log content for debugging
            logger.debug(f"Content that failed to send: {content[:200]}{'...' if len(content) > 200 else ''}")
    
    async def _send_to_websocket(self, content: str):
        """Send content to WebSocket using VE-style integration with visual agent filtering."""
        try:
            # Get the current agent name
            agent_name = getattr(self, '_current_agent_name', 'Unknown Agent')
            
            # Check if this agent should be visible in UI (VE pattern)
            if not self._should_show_agent_message(agent_name, content):
                logger.debug(f"🚫 Filtered message from {agent_name} (not in visual_agents)")
                return
            
            # Get the SimpleTransport singleton instance
            from .simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport:
                # VE-style structured message sending with workflow integration
                await transport.send_simple_text_message(
                    content,
                    self.chat_id,
                    agent_name=agent_name
                )
                logger.debug(f"📤 Sent VE-style message from {agent_name} to WebSocket")
            else:
                logger.warning("❌ SimpleTransport not available for WebSocket sending")
                
        except Exception as e:
            logger.error(f"[IOStream] Error sending to WebSocket: {e}")
            
    def _should_show_agent_message(self, agent_name: str, content: str) -> bool:
        """Check if this agent's message should be shown in UI based on visual_agents config."""
        try:
            # Input validation
            if not isinstance(agent_name, str) or not agent_name.strip():
                logger.debug("🚫 Invalid agent name, filtering message")
                return False
                
            if not isinstance(content, str):
                content = str(content) if content is not None else ""
            
            # Get workflow config to check visual agents
            try:
                from core.workflow.workflow_config import WorkflowConfig
                config_manager = WorkflowConfig()
                visual_agents = config_manager.get_visible_agents("generator")  # Workflow name from workflow.json
                
                if not isinstance(visual_agents, list):
                    logger.warning(f"Invalid visual_agents config: {type(visual_agents)}, defaulting to show message")
                    return True
                    
            except ImportError as e:
                logger.warning(f"WorkflowConfig not available: {e}, defaulting to show message")
                return True
            except Exception as e:
                logger.error(f"Error loading workflow config: {e}, defaulting to show message")
                return True
            
            # Skip user/UserProxy initial messages (they shouldn't show in UI)
            system_agents = ['user', 'UserProxy', 'chat_manager', 'system']
            if agent_name.lower() in [name.lower() for name in system_agents]:
                logger.debug(f"🚫 Skipping system agent message: {agent_name}")
                return False
                
            # Skip empty or system-level content
            if not content.strip():
                logger.debug(f"🚫 Skipping empty content from {agent_name}")
                return False
                
            # Skip AG2 internal coordination messages
            if 'uuid=UUID(' in content and 'sender=' in content:
                logger.debug(f"🚫 Skipping AG2 internal message from {agent_name}")
                return False
            
            # Check if agent is in visual_agents list (case-insensitive)
            visual_agents_lower = [name.lower() for name in visual_agents]
            if agent_name.lower() in visual_agents_lower:
                logger.debug(f"✅ Allowing message from visual agent: {agent_name}")
                return True
            else:
                logger.debug(f"🚫 Filtering out message from non-visual agent: {agent_name} (visual_agents: {visual_agents})")
                return False
                
        except Exception as e:
            logger.error(f"Error checking visual agent status for {agent_name}: {e}")
            # Default to showing message if we can't determine (fail-safe)
            return True
    
    def send(self, message: Any) -> None:
        """
        Handle AG2 BaseEvent objects (like PrintEvent) with production error handling.
        
        This is called by AG2 for structured events. We extract the content
        and stream it using our progressive streaming logic.
        """
        try:
            if not AG2_AVAILABLE:
                # Fallback if AG2 is not available
                self.print(str(message))
                return
                
            if hasattr(message, 'content') and message.content:
                # Extract content from PrintEvent and stream it
                content = message.content
                if isinstance(content, str) and content.strip():
                    self.print(content)
                else:
                    logger.debug(f"Skipping empty or invalid content: {type(content)}")
            elif isinstance(message, BaseEvent):
                # For other AG2 events, send them as backend notifications
                try:
                    from .simple_transport import SimpleTransport
                    transport = SimpleTransport._get_instance()
                    if transport:
                        # Use proper async handling
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(transport.send_backend_notification(
                                    "ag2_event", 
                                    str(message),
                                    {"timestamp": datetime.utcnow().isoformat()}
                                ))
                            else:
                                logger.debug("No running event loop for backend notification")
                        except Exception as e:
                            logger.warning(f"Failed to send backend notification: {e}")
                    else:
                        logger.debug("SimpleTransport not available for backend notification")
                except ImportError:
                    logger.debug("SimpleTransport not available for backend notification")
            else:
                # Handle other message types with validation
                message_str = str(message) if message is not None else ""
                if message_str.strip():
                    self.print(message_str)
                    
        except Exception as e:
            logger.error(f"[IOStream] Error in send method: {e}")
            # Fallback: try to print the message safely
            try:
                fallback_content = str(message) if message is not None else "Unknown message"
                self.print(fallback_content)
            except Exception as fallback_error:
                logger.error(f"[IOStream] Even fallback printing failed: {fallback_error}")
    
    async def input(self, prompt: str = "", *, password: bool = False):
        """
        Handle user input requests from AG2 agents for web UI integration.
        
        This is the crucial method that enables UserProxyAgent to work with web UI.
        When the agent needs human input, this method will:
        1. Send a prompt to the web UI
        2. Signal that user input is needed
        3. Return user input response
        """
        # Input validation
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt is not None else ""
        if not isinstance(password, bool):
            password = bool(password)
            
        logger.info(f"🔄 [IOStream] User input requested with prompt: '{prompt[:100]}{'...' if len(prompt) > 100 else ''}'")
        
        # Call the async implementation directly
        return await self._handle_input_async(prompt, password)
    
    async def _handle_input_async(self, prompt: str, password: bool) -> str:
        """
        Production-ready user input handling for AG2 workflows.
        
        This method integrates with the web UI to collect actual user input
        when agents request it (like UserFeedbackAgent asking for feedback).
        """
        logger.info(f"🎯 [IOStream] Input request received: prompt='{prompt[:50]}{'...' if len(prompt) > 50 else ''}', password={password}")
        
        # Validate chat context
        if not self.chat_id or not self.enterprise_id:
            raise ValueError("IOStream not properly initialized with chat_id and enterprise_id")
        
        # Create unique input request ID
        input_request_id = str(uuid.uuid4())
        
        # Send input request to frontend via WebSocket using tool event
        try:
            from .simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if not transport:
                raise RuntimeError("SimpleTransport not available - cannot collect user input")
                
            await transport.send_tool_event(
                "user_input_request",
                {
                    "input_request_id": input_request_id,
                    "prompt": prompt,
                    "password": password,
                    "agent_name": getattr(self, '_current_agent_name', 'Agent'),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "inline",
                self.chat_id
            )
            
            logger.info(f"📤 [IOStream] Sent user input request {input_request_id} to frontend")
            
        except Exception as e:
            logger.error(f"❌ [IOStream] Failed to send input request: {e}")
            raise RuntimeError(f"Failed to send user input request to frontend: {e}")
        
        # Wait for user input response from the transport layer
        try:
            # Wait for user input with proper error handling
            user_input = await SimpleTransport.wait_for_user_input(input_request_id)
            
            # Validate the response
            if user_input is None:
                raise ValueError("User input was None - this should not happen")
            
            # Convert to string and validate
            user_input_str = str(user_input).strip()
            
            logger.info(f"✅ [IOStream] Received user input for request {input_request_id}")
            chat_logger.info(f"USER_INPUT | Chat: {self.chat_id} | Request: {input_request_id} | Input: {user_input_str[:100]}{'...' if len(user_input_str) > 100 else ''}")
            
            return user_input_str
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ [IOStream] Timeout waiting for user input {input_request_id}")
            raise RuntimeError("Timeout waiting for user input - conversation can be resumed later")
        except Exception as e:
            logger.error(f"❌ [IOStream] Error waiting for user input {input_request_id}: {e}")
            # Don't return a default - let the exception propagate to preserve the conversation state
            # Users can resume the conversation later using the resume functionality
            raise RuntimeError(f"Failed to collect user input: {e}")
    

    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming metadata."""
        self.current_agent_name = agent_name
        # Also store for use in print method logging
        self._current_agent_name = agent_name
        chat_logger.debug(f"AGENT_CONTEXT | Chat: {self.chat_id} | Agent: {agent_name} | Status: Ready for output")


class AG2StreamingManager:
    """
    Production-ready streaming manager using AG2 IOStream integration.
    
    This replaces your current AG2StreamingManager with AG2-compliant
    streaming that works with the IOStream protocol.
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default"):
        # Input validation
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise ValueError("chat_id must be a non-empty string")
        if not isinstance(enterprise_id, str) or not enterprise_id.strip():
            raise ValueError("enterprise_id must be a non-empty string")
            
        self.chat_id = chat_id.strip()
        self.enterprise_id = enterprise_id.strip()
        self.user_id = user_id
        self.workflow_name = workflow_name
        self.streaming_iostream: Optional[AG2StreamingIOStream] = None
        self._original_iostream = None
        self._is_setup = False
    
    def setup_streaming(self, **kwargs) -> AG2StreamingIOStream:
        """
        Set up AG2 streaming with production error handling.
        
        The real streaming happens when you configure your agents with:
        llm_config = {"config_list": config_list, "stream": True}
        """
        try:
            if self._is_setup and self.streaming_iostream is not None:
                logger.warning("Streaming already setup, returning existing IOStream")
                return self.streaming_iostream
                
            # Create the streaming IOStream
            self.streaming_iostream = AG2StreamingIOStream(
                self.chat_id, 
                self.enterprise_id,
                self.user_id,
                self.workflow_name
            )
            
            # Store original IOStream for restoration
            try:
                if AG2_AVAILABLE:
                    self._original_iostream = IOStream.get_default()
                else:
                    logger.warning("AG2 not available, IOStream management disabled")
                    self._original_iostream = None
            except Exception as e:
                logger.warning(f"Could not get default IOStream: {e}")
                self._original_iostream = None
            
            # Set as AG2's global default IOStream
            try:
                if AG2_AVAILABLE:
                    IOStream.set_global_default(self.streaming_iostream)
                    logger.info(f"🎯 AG2 Streaming enabled for chat {self.chat_id}")
                else:
                    logger.warning("AG2 not available, IOStream not set as global default")
            except Exception as e:
                logger.error(f"Failed to set global IOStream: {e}")
                raise RuntimeError(f"Failed to setup AG2 streaming: {e}")
            
            self._is_setup = True
            logger.info(f"🎯 AG2 Streaming enabled - native streaming via llm_config['stream'] = True")
            return self.streaming_iostream
            
        except Exception as e:
            logger.error(f"Failed to setup streaming: {e}")
            raise RuntimeError(f"Streaming setup failed: {e}")
    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming context with validation."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            logger.warning(f"Invalid agent_name provided: {agent_name}")
            return
            
        if self.streaming_iostream:
            self.streaming_iostream.set_agent_context(agent_name.strip())
        else:
            logger.warning("Streaming not setup, cannot set agent context")
    
    def mark_content_for_streaming(self, agent_name: str, message_content: str):
        """Set agent context - AG2 handles the actual streaming."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            logger.warning(f"Invalid agent_name for streaming: {agent_name}")
            return
            
        if self.streaming_iostream:
            self.streaming_iostream.set_agent_context(agent_name.strip())
            logger.info(f"🎯 [STREAMING] Set agent context: {agent_name}")
        else:
            logger.warning("Streaming not setup, cannot mark content for streaming")
    
    def restore_original_iostream(self):
        """Restore the original IOStream when streaming is complete."""
        try:
            if self._original_iostream and AG2_AVAILABLE:
                IOStream.set_global_default(self._original_iostream)
                logger.info("✅ Original IOStream restored")
                self._is_setup = False
            elif not AG2_AVAILABLE:
                logger.debug("AG2 not available, no IOStream to restore")
                self._is_setup = False
            else:
                logger.debug("No original IOStream to restore")
                self._is_setup = False
        except Exception as e:
            logger.error(f"Error restoring original IOStream: {e}")
            self._is_setup = False
    
    def cleanup(self):
        """Cleanup streaming resources."""
        try:
            self.restore_original_iostream()
            self.streaming_iostream = None
            logger.info(f"🧹 Streaming cleanup completed for chat {self.chat_id}")
        except Exception as e:
            logger.error(f"Error during streaming cleanup: {e}")
    
    def is_streaming_active(self) -> bool:
        """Check if streaming is currently active."""
        return self._is_setup and self.streaming_iostream is not None


class AG2AlignedWebSocketManager:
    """
    AG2-aligned WebSocket manager following official AG2 documentation patterns.
    
    This class implements the official AG2 WebSocket server pattern:
    - Uses IOWebsockets.run_server_in_thread()
    - Implements on_connect function that receives IOWebsockets instance
    - Follows AG2's official architecture from documentation
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, port: int = 8080):
        """Initialize AG2-aligned WebSocket manager."""
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise ValueError("chat_id must be a non-empty string")
        if not isinstance(enterprise_id, str) or not enterprise_id.strip():
            raise ValueError("enterprise_id must be a non-empty string")
        if not isinstance(port, int) or port <= 0:
            raise ValueError("port must be a positive integer")
            
        self.chat_id = chat_id.strip()
        self.enterprise_id = enterprise_id.strip()
        self.port = port
        self._server_uri: Optional[str] = None
        self._is_running = False
    
    def create_on_connect_handler(self):
        """
        Create AG2-compliant on_connect handler following official documentation pattern.
        
        Based on: https://docs.ag2.ai/latest/docs/use-cases/notebooks/notebooks/agentchat_websockets/
        """
        def on_connect(iostream) -> None:  # Type annotation removed due to circular import
            """
            AG2 official on_connect pattern handler.
            
            This function is called automatically by AG2 when a client connects.
            The iostream parameter is the IOWebsockets instance managed by AG2.
            """
            logger.info(f"🔗 [AG2] Client connected to chat {self.chat_id}")
            
            try:
                # 1. Receive Initial Message (AG2 official pattern)
                initial_msg = "Hello! How can I help you today?"  # Default message
                try:
                    if hasattr(iostream, 'input') and callable(iostream.input):
                        received_msg = iostream.input()
                        if isinstance(received_msg, str):
                            initial_msg = received_msg
                except Exception as e:
                    logger.warning(f"[AG2] Could not get input from iostream: {e}")
                
                logger.info(f"📥 [AG2] Initial message: {initial_msg[:100]}{'...' if len(initial_msg) > 100 else ''}")
                
                # 2. Get LLM config for streaming (following AG2 docs)
                config_list = _load_config_list_sync()
                
                # 3. Create ConversableAgent with streaming enabled (AG2 official pattern)
                if AG2_AVAILABLE:
                    import autogen
                    agent = autogen.ConversableAgent(
                        name="MozaiksAI_Assistant",
                        system_message="You are a helpful AI assistant. Complete tasks and reply TERMINATE when done.",
                        llm_config={
                            "config_list": config_list,
                            "stream": True,  # AG2 native streaming
                            "timeout": 600
                        }
                    )
                    
                    # 4. Create UserProxyAgent (AG2 official pattern)
                    user_proxy = autogen.UserProxyAgent(
                        name="user_proxy", 
                        system_message="A proxy for the user.",
                        is_termination_msg=lambda x: x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE"),
                        human_input_mode="NEVER",
                        max_consecutive_auto_reply=10,
                        code_execution_config=False
                    )
                    
                    # 5. Register workflow-specific tools (production implementation)
                    try:
                        # Import workflow tool registry for dynamic tool registration
                        from core.workflow.tool_registry import WorkflowToolRegistry
                        
                        # Use "generator" workflow type by default (could be made configurable)
                        tool_registry = WorkflowToolRegistry("generator")
                        tool_registry.load_configuration()
                        
                        # Register tools for the agents based on workflow configuration
                        # This uses your modular tool system from workflow.json
                        tool_registry.register_agent_tools([agent, user_proxy])
                        logger.info(f"[AG2] ✅ Tools registered for agents via WorkflowToolRegistry")
                        
                    except ImportError as e:
                        logger.warning(f"[AG2] WorkflowToolRegistry not available: {e}")
                        logger.info("[AG2] Agents will run without workflow-specific tools")
                    except Exception as e:
                        logger.warning(f"[AG2] Error registering tools: {e}")
                        logger.info("[AG2] Agents will run with basic functionality")
                    
                    # 6. Initiate conversation (AG2 official pattern)
                    logger.info(f"🚀 [AG2] Starting conversation for chat {self.chat_id}")
                    user_proxy.initiate_chat(
                        agent,
                        message=str(initial_msg)  # Ensure string type
                    )
                    
                    logger.info(f"✅ [AG2] Conversation completed for chat {self.chat_id}")
                else:
                    logger.error("[AG2] AG2 not available, cannot create agents")
                    raise RuntimeError("AG2 not available")
                
            except Exception as e:
                logger.error(f"❌ [AG2] Error in on_connect for chat {self.chat_id}: {e}")
                # Send error message to client through AG2's iostream
                try:
                    if hasattr(iostream, 'print') and callable(iostream.print):
                        iostream.print(f"Error: {str(e)}")
                except Exception as print_error:
                    logger.error(f"Failed to send error message through iostream: {print_error}")
                raise e
        
        return on_connect
    
    def start_server(self) -> Optional[str]:
        """
        Start AG2 WebSocket server using official AG2 pattern.
        
        Returns the WebSocket URI that clients should connect to, or None if failed.
        Following: https://docs.ag2.ai/latest/docs/use-cases/notebooks/notebooks/agentchat_websockets/
        """
        if not AG2_AVAILABLE:
            logger.error("AG2 (autogen) not available - cannot start WebSocket server")
            return None
        
        try:
            # Create on_connect handler
            on_connect = self.create_on_connect_handler()
            
            # Start AG2 WebSocket server (official pattern)
            # Note: This is a simplified version for demonstration
            # In production, you'd use the actual AG2 context manager
            try:
                server_context = IOWebsockets.run_server_in_thread(
                    on_connect=on_connect, 
                    port=self.port
                )
                
                if server_context is not None:
                    # AG2's context manager should return a URI
                    self._server_uri = f"ws://localhost:{self.port}"
                    self._is_running = True
                    logger.info(f"🌐 [AG2] WebSocket server started at {self._server_uri} for chat {self.chat_id}")
                    return self._server_uri
                else:
                    logger.error("[AG2] Server context is None")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ [AG2] IOWebsockets.run_server_in_thread failed: {e}")
                return None
            
        except Exception as e:
            logger.error(f"❌ [AG2] Failed to start WebSocket server: {e}")
            return None
    
    def stop_server(self):
        """Stop the AG2 WebSocket server."""
        try:
            if self._is_running:
                # AG2's server context manager handles cleanup automatically
                logger.info(f"🛑 [AG2] WebSocket server stopped for chat {self.chat_id}")
                self._is_running = False
                self._server_uri = None
        except Exception as e:
            logger.error(f"❌ [AG2] Error stopping WebSocket server: {e}")
    
    def get_server_uri(self) -> Optional[str]:
        """Get the current WebSocket server URI."""
        return self._server_uri
    
    def is_running(self) -> bool:
        """Check if the WebSocket server is running."""
        return self._is_running
