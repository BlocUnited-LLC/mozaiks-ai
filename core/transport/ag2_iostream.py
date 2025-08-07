# ==============================================================================
# FILE: core/transport/ag2_iostream.py  
# DESCRIPTION: Clean AG2 IOStream implementation following official AG2 documentation
# ==============================================================================
#
# 🎯 AG2 OFFICIAL PATTERN ALIGNMENT:
# ==================================
# Based on AG2 documentation:
# - https://docs.ag2.ai/latest/docs/use-cases/notebooks/notebooks/agentchat_websockets/
# - https://docs.ag2.ai/latest/docs/_blogs/2025-01-10-WebSockets/
#
# SIMPLIFIED RESPONSIBILITIES:
# 1. ✅ AG2 Native Streaming - Forward llm_config={"stream": True} tokens to WebSocket
# 2. ✅ AG2 Official WebSocket Architecture - IOWebsockets.run_server_in_thread()
# 3. ✅ Official on_connect Pattern - Simple iostream setup only
# 4. ❌ NO groupchat creation (belongs in groupchat_manager.py)
# 5. ❌ NO TokenManager integration (not needed for streaming)
# ==============================================================================
import asyncio
import uuid
from typing import Optional, Any
from datetime import datetime

# AG2 (autogen) imports - core dependency
from autogen.events.base_event import BaseEvent
from autogen.io.base import InputStream, OutputStream
from autogen.io import IOStream
from autogen.io.websockets import IOWebsockets

from logs.logging_config import get_chat_logger

# Get loggers (logging setup happens in main app)
logger = get_chat_logger("ag2_iostream")
chat_logger = get_chat_logger("agent_output")


class AG2StreamingIOStream(InputStream, OutputStream):
    """
    Clean AG2-compliant IOStream implementation for token forwarding only.
    
    RESPONSIBILITIES:
    - Forward AG2's llm_config["stream"] = True tokens to WebSocket
    - Handle user input requests from AG2 agents
    - NO groupchat creation (belongs in groupchat_manager.py)
    - NO TokenManager integration (not needed for streaming)
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default"):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.user_id = user_id
        self.workflow_name = workflow_name
        
        # Minimal streaming state
        self.current_agent_name: Optional[str] = None
    
    def print(self, *objects: Any, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
        """
        AG2-compliant print method - forward tokens to WebSocket only.
        
        When AG2 has "stream": True in llm_config, it will call this method
        with already-streamed content. We simply forward it to WebSocket.
        
        CRITICAL: This method MUST be synchronous and return None to comply with AG2.
        """
        # Validate and convert objects to strings, checking for coroutines
        string_objects = []
        for obj in objects:
            if asyncio.iscoroutine(obj):
                logger.error(f"❌ Received coroutine object in print(): {obj}. Converting to safe string.")
                string_objects.append(f"<coroutine {obj.__name__ if hasattr(obj, '__name__') else 'unknown'}>")
            else:
                string_objects.append(str(obj))
        
        # Convert the print arguments to text (same as standard print)
        content = sep.join(string_objects) + end
        
        if not content.strip():  # Skip empty content
            return None
        
        # Get agent name for logging
        agent_name = getattr(self, 'current_agent_name', 'Unknown Agent')
        
        # Clean content for readability
        clean_content = content.strip()
        if len(clean_content) > 500:
            preview = f"{clean_content[:250]}...{clean_content[-100:]}"
        else:
            preview = clean_content
        
        # Enhanced logging for agent conversations
        chat_logger.info(f"🤖 [{agent_name}] {preview}")
        
        # ALSO log to the main agent chat log for debugging
        import logging
        agent_logger = logging.getLogger('chat.agent_messages')
        agent_logger.info(f"AGENT_OUTPUT | Chat: {self.chat_id} | Agent: {agent_name} | Content: {clean_content}")
        
        # CRITICAL: Persist message to database in real-time (not just at end of workflow)
        try:
            # Create task for async persistence but don't block - ensure the coroutine is properly handled
            try:
                loop = asyncio.get_running_loop()
                # Create the task and don't await it to avoid blocking AG2
                task = asyncio.create_task(self._persist_message_to_db_async(agent_name, clean_content))
                # Add error handling callback to the task
                task.add_done_callback(lambda t: logger.error(f"DB persistence failed: {t.exception()}") if t.exception() else None)
            except RuntimeError:
                # No event loop running, skip persistence to avoid blocking AG2 flow
                logger.debug(f"⚠️ No event loop available for persistence, skipping: {agent_name}")
        except Exception as e:
            logger.error(f"Failed to persist message to database: {e}")
        
        # Send content to WebSocket (AG2 handles the streaming)
        try:
            # Create task for async WebSocket sending but don't block
            try:
                loop = asyncio.get_running_loop()
                # Create the task and don't await it to avoid blocking AG2
                task = asyncio.create_task(self._send_to_websocket(content))
                # Add error handling callback to the task
                task.add_done_callback(lambda t: logger.error(f"WebSocket send failed: {t.exception()}") if t.exception() else None)
            except RuntimeError:
                # No event loop running, skip WebSocket to avoid blocking AG2 flow
                logger.debug(f"⚠️ No event loop available for WebSocket, skipping message")
        except Exception as e:
            logger.error(f"Failed to send content to WebSocket: {e}")
        
        # IMPORTANT: Explicitly return None to ensure AG2 compliance
        return None
    
    async def _send_to_websocket(self, content: str):
        """Send content to WebSocket using SimpleTransport."""
        try:
            # Import SimpleTransport for WebSocket communication
            from .simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()
            if transport:
                agent_name = getattr(self, 'current_agent_name', 'Assistant')
                await transport.send_to_ui(
                    message=content.strip(),
                    agent_name=agent_name,
                    chat_id=self.chat_id
                )
            else:
                logger.warning("SimpleTransport not available for WebSocket communication")
        except Exception as e:
            logger.error(f"Error sending to WebSocket: {e}")
    
    async def _persist_message_to_db_async(self, agent_name: str, content: str) -> None:
        """Persist agent message to database in real-time during AG2 execution."""
        try:
            # Import chat manager for database persistence
            from core.data.persistence_manager import WorkflowChatManager
            
            # Extract actual agent name from AG2 UUID-formatted content
            actual_agent_name = self._extract_agent_name_from_content(content)
            if not actual_agent_name or actual_agent_name == 'system':
                actual_agent_name = agent_name  # fallback to passed agent name
            
            logger.debug(f"🔍 [AG2 Persistence] Extracted agent: '{actual_agent_name}' from content: {content[:100]}...")
            logger.info(f"🔍 [AG2 Persistence] DEBUG: Extracted agent: '{actual_agent_name}' from content: {content[:100]}...")
            
            # Create chat manager instance with current context
            chat_manager = WorkflowChatManager(
                workflow_name=self.workflow_name,
                enterprise_id=self.enterprise_id,
                chat_id=self.chat_id,
                user_id=self.user_id
            )
            
            # Store message immediately to database using async method with correct agent name
            await chat_manager.add_message_to_history(
                sender=actual_agent_name,
                content=content,
                role="assistant"
            )
            
            logger.debug(f"✅ Persisted message from {agent_name} to database: {len(content)} chars")
                
        except Exception as e:
            logger.error(f"❌ Failed to persist message to database: {e}")
            # Don't raise - persistence failure shouldn't break AG2 flow
    
    def _extract_agent_name_from_content(self, content: str) -> str:
        """Extract actual agent name from AG2 UUID-formatted message content."""
        import re
        
        # AG2 format: "uuid=UUID('...') content='...' sender='AgentName' recipient='...'"
        # Look for sender='AgentName' pattern
        sender_match = re.search(r"sender='([^']+)'", content)
        if sender_match:
            agent_name = sender_match.group(1)
            # Filter out non-agent senders
            if agent_name not in ['user', 'chat_manager', 'system']:
                return agent_name
        
        # Fallback patterns if above doesn't work
        sender_match_quotes = re.search(r'sender="([^"]+)"', content)
        if sender_match_quotes:
            agent_name = sender_match_quotes.group(1)
            if agent_name not in ['user', 'chat_manager', 'system']:
                return agent_name
        
        return "system"  # fallback
    
    def send(self, message: Any) -> None:
        """
        Handle AG2 BaseEvent objects - forward to print method.
        
        CRITICAL: This method MUST be synchronous and return None to comply with AG2.
        """
        try:
            # Check if message has content attribute
            if hasattr(message, 'content') and message.content is not None:
                content = message.content
                
                # Validate that content is not a coroutine
                if asyncio.iscoroutine(content):
                    logger.error(f"❌ Received coroutine object in send(): {content}. Converting to safe string.")
                    content = f"<coroutine {content.__name__ if hasattr(content, '__name__') else 'unknown'}>"
                
                self.print(content)
            else:
                # Convert entire message to string
                message_str = str(message)
                
                # Validate that message_str is not somehow a coroutine
                if asyncio.iscoroutine(message):
                    logger.error(f"❌ Received coroutine object as message in send(): {message}. Converting to safe string.")
                    message_str = f"<coroutine {message.__name__ if hasattr(message, '__name__') else 'unknown'}>"
                
                self.print(message_str)
        except Exception as e:
            logger.error(f"Error in send method: {e}")
        
        # IMPORTANT: Explicitly return None to ensure AG2 compliance
        return None
    
    def input(self, prompt: str = "", *, password: bool = False) -> str:
        """
        Handle user input requests from AG2 agents for web UI integration.
        
        This is the crucial method that enables UserProxyAgent to work with web UI.
        Note: This must be synchronous to match IOStreamProtocol, but we handle async internally.
        """
        # Input validation
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt is not None else ""
        if not isinstance(password, bool):
            password = bool(password)
            
        logger.info(f"🔄 [IOStream] User input requested with prompt: '{prompt[:100]}{'...' if len(prompt) > 100 else ''}'")
        
        # Run the async implementation synchronously
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._handle_input_async(prompt, password))
                    return future.result()
            else:
                # We can use asyncio.run directly
                return asyncio.run(self._handle_input_async(prompt, password))
        except Exception as e:
            logger.error(f"❌ [IOStream] Error in synchronous input method: {e}")
            raise RuntimeError(f"Failed to collect user input: {e}")
    
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
                
            # NEW ARCHITECTURE: Send a dedicated user_input_request event, not a generic ui_tool_event.
            # This decouples standard agent input from custom UI components.
            await transport.send_user_input_request(
                input_request_id=input_request_id,
                chat_id=self.chat_id,
                payload={
                    "prompt": prompt,
                    "password": password,
                    "agent_name": getattr(self, 'current_agent_name', 'Agent'),
                }
            )
            
            logger.info(f"📤 [IOStream] Sent user input request {input_request_id} to frontend")
            
        except Exception as e:
            logger.error(f"❌ [IOStream] Failed to send input request: {e}")
            raise RuntimeError(f"Failed to send user input request to frontend: {e}")
        
        # Wait for user input response from the transport layer
        try:
            user_input = await SimpleTransport.wait_for_user_input(input_request_id)
            
            if user_input is None:
                raise ValueError("User input was None")
            
            user_input_str = str(user_input).strip()
            
            logger.info(f"✅ [IOStream] Received user input for request {input_request_id}")
            chat_logger.info(f"USER_INPUT | Chat: {self.chat_id} | Input: {user_input_str[:100]}{'...' if len(user_input_str) > 100 else ''}")
            
            return user_input_str
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ [IOStream] Timeout waiting for user input {input_request_id}")
            raise RuntimeError("Timeout waiting for user input - conversation can be resumed later")
        except Exception as e:
            logger.error(f"❌ [IOStream] Error waiting for user input {input_request_id}: {e}")
            raise RuntimeError(f"Failed to collect user input: {e}")
    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming metadata."""
        self.current_agent_name = agent_name
        chat_logger.debug(f"AGENT_CONTEXT | Chat: {self.chat_id} | Agent: {agent_name}")


class AG2StreamingManager:
    """
    Clean AG2 streaming manager - only handles IOStream setup.
    
    NO groupchat creation - that belongs in groupchat_manager.py
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, user_id: str = "unknown", workflow_name: str = "default"):
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
        Set up AG2 streaming with IOStream only.
        
        The real streaming happens when you configure your agents with:
        llm_config = {"config_list": config_list, "stream": True}
        """
        try:
            # Store original IOStream if it exists
            self._original_iostream = IOStream.get_default()
            
            # Create our custom streaming IOStream
            self.streaming_iostream = AG2StreamingIOStream(
                chat_id=self.chat_id,
                enterprise_id=self.enterprise_id,
                user_id=self.user_id,
                workflow_name=self.workflow_name
            )
            
            # Set as the global default for AG2
            IOStream.set_global_default(self.streaming_iostream)
            self._is_setup = True
            
            logger.info(f"✅ [AG2StreamingManager] IOStream setup complete for chat {self.chat_id}")
            return self.streaming_iostream
            
        except Exception as e:
            logger.error(f"❌ [AG2StreamingManager] Failed to setup streaming: {e}")
            raise RuntimeError(f"Failed to setup AG2 streaming: {e}")
    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming context."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            logger.warning("Invalid agent name provided to set_agent_context")
            return
            
        if self.streaming_iostream:
            self.streaming_iostream.set_agent_context(agent_name.strip())
        else:
            logger.warning("Streaming IOStream not available for agent context setting")
    
    def restore_original_iostream(self):
        """Restore the original IOStream when streaming is complete."""
        try:
            if self._original_iostream:
                IOStream.set_global_default(self._original_iostream)
                logger.info("✅ [AG2StreamingManager] Original IOStream restored")
            else:
                logger.debug("No original IOStream to restore")
        except Exception as e:
            logger.error(f"❌ [AG2StreamingManager] Error restoring IOStream: {e}")
    
    def cleanup(self):
        """Cleanup streaming resources."""
        try:
            self.restore_original_iostream()
            self.streaming_iostream = None
            self._is_setup = False
            logger.info(f"✅ [AG2StreamingManager] Cleanup complete for chat {self.chat_id}")
        except Exception as e:
            logger.error(f"❌ [AG2StreamingManager] Error during cleanup: {e}")
    
    def is_streaming_active(self) -> bool:
        """Check if streaming is currently active."""
        return self._is_setup and self.streaming_iostream is not None


class AG2AlignedWebSocketManager:
    """
    Clean AG2-aligned WebSocket manager following official AG2 documentation patterns.
    
    ONLY handles WebSocket server setup - NO groupchat creation.
    The on_connect function will be called by groupchat_manager.py
    """
    
    def __init__(self, chat_id: str, enterprise_id: str, port: int = 8080):
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
    
    def start_server(self, on_connect_func) -> Optional[str]:
        """
        Start AG2 WebSocket server using official AG2 pattern.
        
        The on_connect_func should be provided by groupchat_manager.py
        and handle the actual groupchat creation.
        """
        try:
            # Start AG2 WebSocket server (official pattern)
            server_context = IOWebsockets.run_server_in_thread(
                on_connect=on_connect_func, 
                port=self.port
            )
            
            if server_context is not None:
                self._server_uri = f"ws://localhost:{self.port}"
                self._is_running = True
                logger.info(f"🌐 [AG2] WebSocket server started at {self._server_uri} for chat {self.chat_id}")
                return self._server_uri
            else:
                logger.error("[AG2] Server context is None")
                return None
                
        except Exception as e:
            logger.error(f"❌ [AG2] Failed to start WebSocket server: {e}")
            return None
    
    def stop_server(self):
        """Stop the AG2 WebSocket server."""
        try:
            if self._is_running:
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
