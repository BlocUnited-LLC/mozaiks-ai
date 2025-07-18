# ==============================================================================
# FILE: core/transport/ag2_iostream.py
# DESCRIPTION: AG2 IOStream implementation for token-by-token streaming like ChatGPT
# ==============================================================================
import asyncio
import uuid
import time
from typing import Optional, Any, List
from datetime import datetime

try:
    from autogen.events.base_event import BaseEvent  # type: ignore
    from autogen.io.base import IOStreamProtocol  # type: ignore
    from autogen.io import IOStream  # type: ignore
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
            # Note: iostream parameter required for interface compatibility
            pass

from ..events.simple_protocols import SimpleCommunicationChannel as CommunicationChannel
from logs.logging_config import get_chat_logger

logger = get_chat_logger("ag2_iostream")


class AG2StreamingIOStream(IOStreamProtocol):
    """
    Proper AG2 IOStream implementation for token-by-token streaming.
    
    This class correctly inherits from AG2's IOStreamProtocol and implements
    true progressive streaming by intercepting print() calls and breaking
    them into streamable chunks like ChatGPT and Claude.
    """
    
    def __init__(self, communication_channel: CommunicationChannel, chat_id: str, enterprise_id: str):
        self.communication_channel = communication_channel
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        
        # Streaming state
        self.current_message_id: Optional[str] = None
        self.current_agent_name: Optional[str] = None
        self.is_streaming = False
        self._stream_next_content = False  # Flag to control what gets streamed
        
        # Streaming configuration
        self.chunk_size = 1  # Stream character by character for maximum effect
        self.stream_delay = 0.01  # Small delay between chunks (10ms)
    
    def print(self, *objects: Any, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
        """
        CORE STREAMING METHOD - This is where the magic happens!
        
        AG2 agents call this method to output text. We intercept it and
        stream the content progressively instead of sending it all at once.
        
        Message filtering is now handled by the transport layer, so this
        method only checks for explicit streaming marks.
        """
        # Convert the print arguments to text (same as standard print)
        content = sep.join(str(obj) for obj in objects) + end
        
        if not content.strip():  # Skip empty content
            return
        
        # Only stream content that is explicitly marked for streaming
        # This prevents internal AutoGen coordination messages from being streamed
        if not hasattr(self, '_stream_next_content') or not self._stream_next_content:
            logger.debug(f"🔇 [IOStream] Skipping non-streamable content: {content[:50]}...")
            return
            
        # Reset the flag after use
        self._stream_next_content = False
            
        logger.info(f"📡 [IOStream] Streaming marked content: {content[:50]}...")
        
        # Start streaming session if not already started
        if not self.is_streaming:
            self._start_streaming_session()
        
        # Stream the content progressively
        asyncio.create_task(self._stream_content_progressively(content))
        
        # Handle flush or end-of-message scenarios
        if flush or end == "\n\n":
            asyncio.create_task(self._complete_streaming_session())
    
    def mark_next_content_for_streaming(self):
        """Mark the next print() call content to be streamed to UI."""
        self._stream_next_content = True
    
    def send(self, message: Any) -> None:
        """
        Handle AG2 BaseEvent objects (like PrintEvent).
        
        This is called by AG2 for structured events. We extract the content
        and stream it using our progressive streaming logic.
        """
        try:
            if hasattr(message, 'content'):
                # Extract content from PrintEvent and stream it
                content = message.content
                self.print(content)
            elif isinstance(message, BaseEvent):
                # For other AG2 events, send them directly
                asyncio.create_task(self.communication_channel.send_event(
                    "ag2_event", 
                    {"event": str(message), "timestamp": datetime.utcnow().isoformat()}
                ))
            else:
                # Handle other message types
                self.print(str(message))
        except Exception as e:
            logger.error(f"[IOStream] Error in send method: {e}")
            # Fallback: just print the message
            self.print(str(message))
    
    async def input(self, prompt: str = "", *, password: bool = False):
        """
        Handle user input requests from AG2 agents for web UI integration.
        
        This is the crucial method that enables UserProxyAgent to work with web UI.
        When the agent needs human input, this method will:
        1. Send a prompt to the web UI
        2. Signal that user input is needed
        3. Return user input response
        """
        logger.info(f"🔄 [IOStream] User input requested with prompt: '{prompt}'")
        
        # Call the async implementation directly
        return await self._handle_input_async(prompt, password)
    
    async def _handle_input_async(self, prompt: str, password: bool) -> str:
        """
        Simplified input handling for AG2 compatibility.
        
        Returns a default response since UI input logic is handled in workflow components.
        This prevents AG2 from crashing when it calls input() internally.
        """
        logger.info(f"🎯 [IOStream] Input request received: prompt='{prompt}', password={password}")
        
        # Return default response since UI logic is handled in workflow components
        default_response = "continue" if not password else "default_key"
        
        logger.info(f"✅ [IOStream] Returning default response: '{default_response}'")
        return default_response
    
    async def _stream_content_progressively(self, content: str):
        """
        Stream content character by character or word by word.
        
        This creates the ChatGPT-like progressive text effect.
        """
        # Break content into chunks based on configuration
        chunks = self._create_chunks(content)
        
        for chunk in chunks:
            if not self.is_streaming:  # Stop if streaming session ended
                break
                
            # Send the chunk immediately
            await self.communication_channel.send_event(
                "text_stream_chunk",
                {
                    "stream_id": self.current_message_id,
                    "chunk": chunk,
                    "timestamp": time.time() * 1000  # Millisecond precision
                },
                agent_name=self.current_agent_name
            )
            
            # Small delay for progressive effect (adjust for desired speed)
            if self.stream_delay > 0:
                await asyncio.sleep(self.stream_delay)
    
    def _create_chunks(self, content: str) -> List[str]:
        """
        Break content into streamable chunks.
        
        Options:
        - Character-by-character (most ChatGPT-like)
        - Word-by-word (faster, still progressive)
        - Sentence-by-sentence (fastest, less progressive)
        """
        if self.chunk_size == 1:
            # Character-by-character streaming
            return list(content)
        else:
            # Word-by-word streaming
            words = content.split(' ')
            return [word + ' ' for word in words[:-1]] + [words[-1]] if words else []
    
    def _start_streaming_session(self):
        """Start a new streaming session."""
        self.current_message_id = str(uuid.uuid4())
        self.is_streaming = True
        
        # Send stream start event
        asyncio.create_task(self.communication_channel.send_event(
            "text_stream_start",
            {
                "stream_id": self.current_message_id,
                "timestamp": time.time() * 1000
            },
            agent_name=self.current_agent_name
        ))
    
    async def _complete_streaming_session(self):
        """Complete the current streaming session."""
        if self.is_streaming:
            await self.communication_channel.send_event(
                "text_stream_end",
                {
                    "stream_id": self.current_message_id,
                    "timestamp": time.time() * 1000
                },
                agent_name=self.current_agent_name
            )
            
            # Reset state
            self.is_streaming = False
            self.current_message_id = None
    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming metadata."""
        self.current_agent_name = agent_name
    
    def configure_streaming(self, chunk_size: int = 1, delay: float = 0.01):
        """Configure streaming behavior."""
        self.chunk_size = chunk_size
        self.stream_delay = delay


class AG2StreamingManager:
    """
    Updated streaming manager using proper AG2 IOStream integration.
    
    This replaces your current AG2StreamingManager with AG2-compliant
    streaming that works with the IOStream protocol.
    """
    
    def __init__(self, communication_channel: CommunicationChannel, chat_id: str, enterprise_id: str):
        self.communication_channel = communication_channel
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.streaming_iostream: Optional[AG2StreamingIOStream] = None
        self._original_iostream = None
    
    def setup_streaming(self, streaming_speed: str = "fast") -> AG2StreamingIOStream:
        """
        Set up AG2 streaming with different speed presets.
        
        Args:
            streaming_speed: "slow" (char-by-char, 50ms delay), 
                           "medium" (word-by-word, 20ms delay),
                           "fast" (word-by-word, 5ms delay)
        """
        # Create the streaming IOStream
        self.streaming_iostream = AG2StreamingIOStream(
            self.communication_channel, 
            self.chat_id, 
            self.enterprise_id
        )
        
        # Configure streaming speed
        speed_configs = {
            "slow": {"chunk_size": 1, "delay": 0.05},    # ChatGPT-like character streaming
            "medium": {"chunk_size": 4, "delay": 0.02},  # Word streaming
            "fast": {"chunk_size": 8, "delay": 0.005}    # Fast word streaming
        }
        
        config = speed_configs.get(streaming_speed, speed_configs["fast"])
        self.streaming_iostream.configure_streaming(**config)
        
        # Store original IOStream for restoration
        try:
            self._original_iostream = IOStream.get_default()
        except:
            self._original_iostream = None
        
        # Set as AG2's global default IOStream
        IOStream.set_global_default(self.streaming_iostream)
        
        logger.info(f"🎯 AG2 Streaming enabled with {streaming_speed} speed")
        return self.streaming_iostream
    
    def set_agent_context(self, agent_name: str):
        """Set the current agent for better streaming context."""
        if self.streaming_iostream:
            self.streaming_iostream.set_agent_context(agent_name)
    
    def mark_content_for_streaming(self, agent_name: str, message_content: str):
        """Mark the next content from this agent to be streamed to UI."""
        if self.streaming_iostream:
            # Mark the next print() call to be streamed
            self.streaming_iostream.mark_next_content_for_streaming()
            self.streaming_iostream.set_agent_context(agent_name)
            logger.info(f"🎯 [STREAMING] Marked content from {agent_name} for streaming: {message_content[:50]}...")
    
    def restore_original_iostream(self):
        """Restore the original IOStream when streaming is complete."""
        if self._original_iostream:
            IOStream.set_global_default(self._original_iostream)
            logger.info("Original IOStream restored")
    
    # Legacy compatibility methods
    def create_iostream(self) -> AG2StreamingIOStream:
        """Create and return an IOStream for AG2 agents."""
        if not self.streaming_iostream:
            self.streaming_iostream = AG2StreamingIOStream(
                self.communication_channel,
                self.chat_id,
                self.enterprise_id
            )
        logger.info(f"[StreamManager] Created IOStream for chat {self.chat_id}")
        return self.streaming_iostream
    
    def setup_global_iostream(self):
        """Set up global IOStream for AG2 agents using AG2's global system."""
        return self.setup_streaming()
    
    def restore_iostream(self):
        """Legacy method - restore the original IOStream."""
        self.restore_original_iostream()
    
    def attach_to_agents(self, agents: List[Any]):
        """
        Set up global IOStream for AG2 agents.
        
        Note: This method now uses AG2's global IOStream system instead of
        trying to attach to individual agents.
        """
        self.setup_streaming()
        logger.info(f"[StreamManager] Set up global IOStream for {len(agents)} agents")
