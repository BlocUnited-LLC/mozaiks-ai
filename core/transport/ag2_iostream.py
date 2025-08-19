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

from logs.logging_config import get_chat_logger, get_workflow_logger

# Get loggers (logging setup happens in main app)
# - chat_logger: for conversation transcripts only (no workflow ops)
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
        # Per-instance workflow logger with context
        self.wf_logger = get_workflow_logger(
            workflow_name=self.workflow_name,
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            component="ag2_iostream",
        )
        
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
                self.wf_logger.error(
                    f"❌ Received coroutine object in print(): {obj}. Converting to safe string."
                )
                string_objects.append(
                    f"<coroutine {obj.__name__ if hasattr(obj, '__name__') else 'unknown'}>"
                )
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
        # Enhanced logging for agent conversations (single sink)
        chat_logger.info(f"🤖 [{agent_name}] {preview}")
        
        # CRITICAL: Persistence is now handled by UIEventProcessor.
        # This class is only for forwarding print() calls to the UI.
        
        # Send content to WebSocket (AG2 handles the streaming)
        try:
            # Create task for async WebSocket sending but don't block
            try:
                loop = asyncio.get_running_loop()
                # Create the task and don't await it to avoid blocking AG2
                task = asyncio.create_task(self._send_to_websocket(content))
                # Add error handling callback to the task
                task.add_done_callback(
                    lambda t: self.wf_logger.error(
                        f"WebSocket send failed: {t.exception()}"
                    )
                    if t.exception()
                    else None
                )
            except RuntimeError:
                # No event loop running, skip WebSocket to avoid blocking AG2 flow
                self.wf_logger.debug(
                    "⚠️ No event loop available for WebSocket, skipping message"
                )
        except Exception as e:
            self.wf_logger.error(f"Failed to send content to WebSocket: {e}")
        
        # IMPORTANT: Explicitly return None to ensure AG2 compliance
        return None
    
    async def _send_to_websocket(self, content: str):
        """Send content to WebSocket using SimpleTransport."""
        try:
            # Import SimpleTransport for WebSocket communication
            from .simple_transport import SimpleTransport
            transport = await SimpleTransport.get_instance()
            if transport:
                agent_name = getattr(self, 'current_agent_name', 'Assistant')
                await transport.send_to_ui(
                    message=content.strip(),
                    agent_name=agent_name,
                    chat_id=self.chat_id
                )
            else:
                self.wf_logger.warning(
                    "SimpleTransport not available for WebSocket communication"
                )
        except Exception as e:
            self.wf_logger.error(f"Error sending to WebSocket: {e}")

    def send(self, message: BaseEvent) -> None:
        """
        AG2-compliant send method.
        This is less commonly used than print() for streaming, but is required by the protocol.
        We can forward this data as a generic event to the UI.
        """
        self.wf_logger.debug(
            f"AG2StreamingIOStream.send() called with event: {type(message).__name__}"
        )
        try:
            loop = asyncio.get_running_loop()
            task = asyncio.create_task(self._send_generic_event_to_websocket(message))
            task.add_done_callback(
                lambda t: self.wf_logger.error(
                    f"WebSocket send (generic) failed: {t.exception()}"
                )
                if t.exception()
                else None
            )
        except RuntimeError:
            self.wf_logger.debug(
                "⚠️ No event loop available for WebSocket, skipping generic send"
            )
        except Exception as e:
            self.wf_logger.error(f"Failed to send generic data to WebSocket: {e}")

    async def _send_generic_event_to_websocket(self, event: BaseEvent):
        """Asynchronously sends generic data to the WebSocket."""
        try:
            from .simple_transport import SimpleTransport
            transport = await SimpleTransport.get_instance()
            if transport:
                # Use the send_event_to_ui method for proper serialization
                await transport.send_event_to_ui(
                    event=event,
                    chat_id=self.chat_id
                )
        except Exception as e:
            self.wf_logger.error(f"Error sending generic event to WebSocket: {e}")

    def input(self, prompt: str = "", *, password: bool = False) -> str:
        """
        AG2-compliant input method - request user input via WebSocket.
        
        This is the method that AG2 agents call when they need input from the user.
        It sends a request to the frontend and waits for the user's response.
        This method is synchronous and bridges to the async transport layer.
        """
        if password:
            self.wf_logger.warning(
                "Password-protected input was requested, but this feature is not implemented in the current transport. The input will be treated as regular text."
            )

        input_request_id = str(uuid.uuid4())
        
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self._get_user_input(input_request_id, prompt), loop)
        except RuntimeError:
            self.wf_logger.error(
                "❌ No running event loop to handle user input. This is a critical error in the application's threading model."
            )
            return "Error: Backend misconfiguration - cannot process user input."

        try:
            # Block and wait for the user's input from the event loop thread.
            user_input = future.result()
            self.wf_logger.info(f"✅ Received user input for request {input_request_id}")
            return user_input
        except Exception as e:
            self.wf_logger.error(f"❌ Failed to get user input for {input_request_id}: {e}")
            return "Error: Could not get user input."

    async def _get_user_input(self, input_request_id: str, prompt: str) -> str:
        """Helper async method to handle the full user input flow."""
        try:
            from .simple_transport import SimpleTransport
            transport = await SimpleTransport.get_instance()

            if not transport:
                self.wf_logger.warning(
                    "SimpleTransport not available for user input request"
                )
                return "Error: Transport not available."

            # Send the request to the UI
            await transport.send_user_input_request(
                input_request_id=input_request_id,
                chat_id=self.chat_id,
                payload={"prompt": prompt}
            )

            # Wait for the response from the UI
            user_input = await transport.wait_for_user_input(input_request_id)
            return user_input
        except Exception as e:
            self.wf_logger.error(f"Error during user input flow: {e}")
            return "Error: Failed to receive user input."

    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming metadata."""
        self.current_agent_name = agent_name
        self.wf_logger.debug(
            f"AGENT_CONTEXT | Chat: {self.chat_id} | Agent: {agent_name}"
        )


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
        # Per-manager workflow logger with context
        self.wf_logger = get_workflow_logger(
            workflow_name=self.workflow_name,
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            component="ag2_streaming_manager",
        )
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
            
            self.wf_logger.info(
                f"✅ [AG2StreamingManager] IOStream setup complete for chat {self.chat_id}"
            )
            return self.streaming_iostream
            
        except Exception as e:
            self.wf_logger.error(
                f"❌ [AG2StreamingManager] Failed to setup streaming: {e}"
            )
            raise RuntimeError(f"Failed to setup AG2 streaming: {e}")
    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming context."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            self.wf_logger.warning("Invalid agent name provided to set_agent_context")
            return
            
        if self.streaming_iostream:
            self.streaming_iostream.set_agent_context(agent_name.strip())
        else:
            self.wf_logger.warning(
                "Streaming IOStream not available for agent context setting"
            )
    
    def restore_original_iostream(self):
        """Restore the original IOStream when streaming is complete."""
        try:
            if self._original_iostream:
                IOStream.set_global_default(self._original_iostream)
                self.wf_logger.info("✅ [AG2StreamingManager] Original IOStream restored")
            else:
                self.wf_logger.debug("No original IOStream to restore")
        except Exception as e:
            self.wf_logger.error(
                f"❌ [AG2StreamingManager] Error restoring IOStream: {e}"
            )
    
    def cleanup(self):
        """Cleanup streaming resources."""
        try:
            self.restore_original_iostream()
            self.streaming_iostream = None
            self._is_setup = False
            self.wf_logger.info(
                f"✅ [AG2StreamingManager] Cleanup complete for chat {self.chat_id}"
            )
        except Exception as e:
            self.wf_logger.error(
                f"❌ [AG2StreamingManager] Error during cleanup: {e}"
            )
    
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
        # Per-manager workflow logger with context
        self.wf_logger = get_workflow_logger(
            workflow_name="transport.websocket",
            chat_id=self.chat_id,
            enterprise_id=self.enterprise_id,
            component="ag2_websocket_manager",
        )
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
                self.wf_logger.info(
                    f"🌐 [AG2] WebSocket server started at {self._server_uri} for chat {self.chat_id}"
                )
                return self._server_uri
            else:
                self.wf_logger.error("[AG2] Server context is None")
                return None
                
        except Exception as e:
            self.wf_logger.error(f"❌ [AG2] Failed to start WebSocket server: {e}")
            return None
    
    def stop_server(self):
        """Stop the AG2 WebSocket server."""
        try:
            if self._is_running:
                self.wf_logger.info(
                    f"🛑 [AG2] WebSocket server stopped for chat {self.chat_id}"
                )
                self._is_running = False
                self._server_uri = None
        except Exception as e:
            self.wf_logger.error(f"❌ [AG2] Error stopping WebSocket server: {e}")
    
    def get_server_uri(self) -> Optional[str]:
        """Get the current WebSocket server URI."""
        return self._server_uri
    
    def is_running(self) -> bool:
        """Check if the WebSocket server is running."""
        return self._is_running
