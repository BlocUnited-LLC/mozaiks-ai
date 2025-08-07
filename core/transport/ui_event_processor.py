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
        Handles generic AG2 InputRequestEvents by logging a warning and auto-skipping.
        
        This behavior enforces the architectural decision that all user interactions
        should be handled by specific, defined UI tools (e.g., request_api_key) 
        rather than generic `agent.input()` calls. Our custom `ag2_iostream.py`
        is the designated handler for legitimate, non-tool-based input, so if an
        input request reaches this processor, it's considered an anti-pattern.
        """
        try:
            prompt = event.content.prompt or "Input required:"  # type: ignore[attr-defined]
            
            self.logger.warning(f"⚠️ [{self.chat_id}] Intercepted a generic `input()` call. This is an anti-pattern.")
            self.logger.warning(f"   Prompt: '{prompt[:150]}...'")
            self.logger.warning(f"   Auto-skipping to prevent workflow from hanging. Use a dedicated UI tool instead.")
            
            # Auto-respond with an empty string to prevent the workflow from stalling.
            await event.content.respond("")  # type: ignore[attr-defined]

        except Exception as e:
            self.logger.error(f"❌ [{self.chat_id}] Failed to auto-skip generic input request: {e}")
            self.logger.error(f"   Traceback: {traceback.format_exc()}")
            # Ensure fallback response to prevent AG2 from hanging under any circumstance.
            if not event.content.is_responded:  # type: ignore[attr-defined]
                await event.content.respond("")  # type: ignore[attr-defined]

# End of UIEventProcessor - clean AG2-compliant implementation
