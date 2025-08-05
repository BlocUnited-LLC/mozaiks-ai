# ==============================================================================
# FILE: core/transport/ui_event_processor.py
# DESCRIPTION: AG2-compliant event processor following AsyncEventProcessorProtocol
# ==============================================================================

import logging
import asyncio
import traceback
import uuid
from typing import TYPE_CHECKING, Any, Union, Optional
from autogen.events.agent_events import InputRequestEvent
from autogen.events.base_event import BaseEvent
from datetime import datetime

if TYPE_CHECKING:
    from autogen.io.run_response import AsyncRunResponseProtocol

from logs.logging_config import get_business_logger

class UIEventProcessor:
    """
    AG2-compliant event processor that follows AsyncEventProcessorProtocol pattern.
    Routes input requests to our UI instead of console, following AG2 best practices.
    """
    
    def __init__(self, chat_id: str, enterprise_id: str):
        self.chat_id = chat_id
        self.enterprise_id = enterprise_id
        self.logger = get_business_logger("ui_event_processor")
        
    async def process(self, response: "AsyncRunResponseProtocol") -> None:
        """
        Process AG2 events - follows AG2's AsyncEventProcessorProtocol pattern.
        This is the main entry point called by AG2's run response system.
        """
        async for event in response.events:
            await self.process_event(event)
    
    async def process_event(self, event: BaseEvent) -> None:
        """
        Process individual AG2 events.
        Following AG2's AsyncConsoleEventProcessor pattern but routing to UI.
        """
        if isinstance(event, InputRequestEvent):
            await self._handle_input_request(event)
        else:
            # For non-input events, just print them (same as AG2's console processor)
            event.print()
    
    async def _handle_input_request(self, event: InputRequestEvent) -> None:
        """
        Handle AG2 InputRequestEvent by routing to our UI transport system.
        This follows AG2's input handling pattern but integrates with our UI.
        """
        try:
            # Import transport layer locally to avoid circular dependency at startup
            from .simple_transport import SimpleTransport
            transport = SimpleTransport._get_instance()

            if not transport:
                self.logger.error(f"❌ [{self.chat_id}] SimpleTransport not available, cannot handle input request.")
                # Fallback response to prevent AG2 from hanging
                await event.content.respond("continue")  # type: ignore[attr-defined]
                return

            # Extract prompt and password from the event content, following AG2's pattern.
            prompt = event.content.prompt or "Input required:"  # type: ignore[attr-defined]
            is_password = event.content.password or False  # type: ignore[attr-defined]
            
            self.logger.info(f"🎯 [{self.chat_id}] AG2 input request: {prompt[:100]}...")
            
            # Generate unique request ID for tracking
            input_request_id = str(uuid.uuid4())
            
            # Send UI tool event for input request
            await transport.send_ui_tool_event(
                ui_tool_id="user_input_request",
                payload={
                    "input_request_id": input_request_id,
                    "prompt": prompt,
                    "password": is_password,
                    "chat_id": self.chat_id,
                    "enterprise_id": self.enterprise_id,
                    "timestamp": datetime.utcnow().isoformat()
                },
                display="inline",
                chat_id=self.chat_id
            )
            
            self.logger.info(f"📬 [{self.chat_id}] Sent input request {input_request_id} to UI")
            
            # Wait for user response via transport layer
            user_response = await transport.wait_for_user_input(input_request_id)
            
            self.logger.info(f"✅ [{self.chat_id}] Received user response for {input_request_id}")
            
            # Respond to AG2 event
            await event.content.respond(user_response)  # type: ignore[attr-defined]
            self.logger.info(f"✅ [{self.chat_id}] Responded to AG2 input request")

        except Exception as e:
            self.logger.error(f"❌ [{self.chat_id}] Failed to handle input via UI: {e}")
            self.logger.error(f"❌ [{self.chat_id}] Traceback: {traceback.format_exc()}")
            # Fallback response to prevent AG2 from hanging
            await event.content.respond("continue")  # type: ignore[attr-defined]

# End of UIEventProcessor - clean AG2-compliant implementation
