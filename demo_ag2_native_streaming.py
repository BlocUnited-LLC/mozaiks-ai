# ==============================================================================
# FILE: demo_ag2_native_streaming.py
# DESCRIPTION: Demo showing AG2's built-in progressive streaming
# ==============================================================================
"""
This demo shows how AG2's native streaming works when you set:
    llm_config = {"config_list": config_list, "stream": True}

AG2 provides:
- Token-by-token streaming from the LLM
- Progressive text appearance (ChatGPT-like effect)  
- Real-time output without custom chunking logic

Run this to see AG2 streaming in action!
"""

import asyncio
from autogen import ConversableAgent
from core.core_config import make_llm_config

async def demo_ag2_streaming():
    """Demonstrate AG2's native streaming capability."""
    print("🎯 AG2 Native Streaming Demo")
    print("=" * 50)
    
    # Create LLM config with streaming enabled
    print("📊 Creating streaming LLM config...")
    _, llm_config_streaming = await make_llm_config(stream=True)
    
    # Create LLM config without streaming for comparison
    _, llm_config_normal = await make_llm_config(stream=False)
    
    print("✅ LLM configs created!")
    print()
    
    # Create agents
    streaming_agent = ConversableAgent(
        name="StreamingAgent",
        system_message="You are a helpful assistant. Provide detailed, informative responses.",
        llm_config=llm_config_streaming,  # This enables AG2's native streaming
        human_input_mode="NEVER"
    )
    
    normal_agent = ConversableAgent(
        name="NormalAgent", 
        system_message="You are a helpful assistant. Provide detailed, informative responses.",
        llm_config=llm_config_normal,  # Regular non-streaming output
        human_input_mode="NEVER"
    )
    
    user_proxy = ConversableAgent(
        name="UserProxy",
        system_message="You are a user proxy.",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
        llm_config=False  # No LLM needed for proxy
    )
    
    print("🤖 Agents created!")
    print()
    
    # Test message
    test_message = "Explain how machine learning works in simple terms, including key concepts like training data, algorithms, and model evaluation. Make it detailed but accessible."
    
    print("📝 Test Message:")
    print(f"   {test_message}")
    print()
    
    # Demo 1: Normal (non-streaming) response
    print("🔸 DEMO 1: Normal Agent Response (no streaming)")
    print("-" * 50)
    user_proxy.initiate_chat(normal_agent, message=test_message)
    print()
    
    # Demo 2: Streaming response  
    print("🔸 DEMO 2: Streaming Agent Response (AG2 native streaming)")
    print("-" * 50)
    print("👀 Watch for progressive text appearance...")
    user_proxy.initiate_chat(streaming_agent, message=test_message)
    print()
    
    print("✅ Demo completed!")
    print()
    print("📋 Key Observations:")
    print("   • Normal agent: Text appears all at once")
    print("   • Streaming agent: Text appears progressively (token-by-token)")
    print("   • AG2 handles all the streaming logic internally")
    print("   • No custom chunking or delays needed!")
    print()
    print("🎯 For web UI integration:")
    print("   • Your IOStream forwards streamed tokens to WebSocket")
    print("   • Frontend receives progressive updates automatically")
    print("   • Same ChatGPT-like experience for users")

if __name__ == "__main__":
    asyncio.run(demo_ag2_streaming())
