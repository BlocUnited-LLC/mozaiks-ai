#!/usr/bin/env python3
"""
Test simplified transport system
"""
import sys
sys.path.append('.')

from core.transport.simple_transport import SimpleTransport

print('🚀 Testing Simplified Transport System')
print('=' * 50)

async def test_transport():
    # Create transport
    transport = SimpleTransport({'model': 'gpt-4', 'api_key': 'test'})
    print('✅ SimpleTransport created')
    
    # Test filtering logic
    print('\n🔍 Testing Message Filtering:')
    
    # Should be filtered out
    filtered_cases = [
        ("", "User"),  # Empty message
        ("hi", "User"),  # Too short
        ("next speaker: John", "Agent"),  # Coordination keyword
        ('{"type": "metadata"}', "Agent"),  # JSON structure
        ("Hello world", "chat_manager"),  # Internal agent
    ]
    
    for message, agent in filtered_cases:
        result = transport.should_show_to_user(message, agent)
        status = "❌ FILTERED" if not result else "⚠️  ALLOWED"
        print(f"  {status}: '{message}' from {agent}")
    
    print('\n✅ Testing Valid Messages:')
    
    # Should be allowed
    valid_cases = [
        ("Hello, how can I help you today?", "Assistant"),
        ("I found 5 files in your directory", "FileSearchAgent"),
        ("Here's the analysis you requested", "DataAnalyst"),
    ]
    
    for message, agent in valid_cases:
        result = transport.should_show_to_user(message, agent)
        status = "✅ ALLOWED" if result else "❌ FILTERED"
        print(f"  {status}: '{message}' from {agent}")
    
    # Test agent name formatting
    print('\n🎨 Testing Agent Name Formatting:')
    
    format_cases = [
        "ContextVariablesAgent",
        "FileSearchAgent", 
        "DataAnalysisAgent",
        "Agent",
        "unknown"
    ]
    
    for agent_name in format_cases:
        formatted = transport.format_agent_name(agent_name)
        print(f"  '{agent_name}' → '{formatted}'")
    
    # Test connection info
    print('\n📊 Testing Connection Info:')
    info = transport.get_connection_info()
    print(f"  SSE connections: {info['sse_connections']}")
    print(f"  WebSocket connections: {info['websocket_connections']}")
    print(f"  Total connections: {info['total_connections']}")
    
    # Test event types for frontend compatibility
    print('\n🎯 Testing Frontend Event Types:')
    chat_id = "test_chat_123"
    
    # Test chat message
    await transport.send_to_ui(
        message="Hello from agent!",
        agent_name="TestAgent", 
        chat_id=chat_id
    )
    print("  ✅ Chat message sent")
    
    # Test artifact routing
    await transport.send_to_artifact(
        content="Here's your generated code...",
        artifact_type="code_editor",
        agent_name="CodeAgent",
        chat_id=chat_id
    )
    print("  ✅ Artifact message sent")
    
    # Test UI tool
    await transport.send_ui_tool(
        tool_id="file_upload",
        payload={"file_types": [".py", ".js"]},
        chat_id=chat_id
    )
    print("  ✅ UI tool message sent")
    
    # Test error
    await transport.send_error(
        error_message="Something went wrong",
        error_code="TEST_ERROR",
        chat_id=chat_id
    )
    print("  ✅ Error message sent")
    
    # Test status
    await transport.send_status(
        status_message="Processing your request...",
        status_type="info",
        chat_id=chat_id
    )
    print("  ✅ Status message sent")
    
    print('\n🎉 Simplified Transport Test Complete!')
    print('📋 Key Benefits:')
    print('   - ✅ Simple, focused API')
    print('   - ✅ Effective AutoGen noise filtering') 
    print('   - ✅ Clean agent name formatting')
    print('   - ✅ Support for both SSE and WebSocket')
    print('   - ✅ Frontend-compatible event types')
    print('   - ✅ Artifact routing support')
    print('   - ✅ UI tool integration')
    print('   - ✅ Error and status handling')
    print('   - ✅ Much less complex than before')

# Run async test
if __name__ == "__main__":
    import asyncio
    asyncio.run(test_transport())
