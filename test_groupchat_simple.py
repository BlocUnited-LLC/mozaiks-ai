# ==============================================================================
# FILE: test_groupchat_simple.py
# DESCRIPTION: Simple test to verify Generator groupchat actually runs
# ==============================================================================

import asyncio
import logging
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.core_config import make_llm_config

# Mock communication channel for testing
class MockCommunicationChannel:
    def __init__(self):
        self.events = []
    
    async def send_event(self, event_type: str, data: dict):
        """Mock send event for testing"""
        self.events.append({"event_type": event_type, "data": data})
        print(f"📡 Mock Event: {event_type}")
        if "content" in data:
            content = data["content"]
            if len(content) > 100:
                content = content[:100] + "..."
            print(f"   Content: {content}")

async def test_generator_groupchat():
    """Test that Generator groupchat can actually start and run"""
    
    print("🧪 Testing Generator Groupchat")
    print("=" * 50)
    
    try:
        # Import Generator workflow
        from workflows.Generator.OrchestrationPattern import run_groupchat
        
        # Get LLM config
        _, llm_config = await make_llm_config()  # Only need the config, not the client
        
        # Mock transport
        mock_channel = MockCommunicationChannel()
        
        # Test parameters - use bypass flag for testing
        enterprise_id = "test_mode_bypass_budget"  # Special enterprise ID to bypass budget checks
        chat_id = "test_chat_simple"
        user_id = "test_user"
        initial_message = "Generate a simple project workflow for a todo app"
        
        print(f"🚀 Starting Generator groupchat...")
        print(f"   Enterprise: {enterprise_id}")
        print(f"   Chat: {chat_id}")
        print(f"   Message: {initial_message}")
        print("   Mode: No human input (testing mode)")
        print()
        
        # Run the groupchat
        await run_groupchat(
            llm_config=llm_config,
            enterprise_id=enterprise_id,
            chat_id=chat_id,
            user_id=user_id,
            initial_message=initial_message,
            communication_channel=mock_channel
        )
        
        print("\n✅ Groupchat completed successfully!")
        print(f"📊 Total events sent: {len(mock_channel.events)}")
        
        # Show event summary
        event_types = {}
        for event in mock_channel.events:
            event_type = event["event_type"]
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        print("\n📈 Event Summary:")
        for event_type, count in event_types.items():
            print(f"   {event_type}: {count}")
            
        return True
        
    except Exception as e:
        print(f"\n❌ Groupchat failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Disable Azure and other noisy loggers
    import logging
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Set up basic logging for our test only
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings and errors
        format='%(message)s'    # Simple format
    )
    
    # Enable only key loggers we care about
    logging.getLogger("workflows.Generator").setLevel(logging.INFO)
    logging.getLogger("business.generator_orchestration").setLevel(logging.INFO)
    
    # Run the test
    success = asyncio.run(test_generator_groupchat())
    
    if success:
        print("\n🎉 Generator groupchat is working!")
    else:
        print("\n💥 Generator groupchat has issues!")
