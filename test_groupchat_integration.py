#!/usr/bin/env python3
"""
Test groupchat manager VE-style termination integration
"""
import asyncio
from core.workflow.groupchat_manager import create_termination_handler

async def test_groupchat_integration():
    print('🧪 Testing Groupchat Manager VE-Style Integration')
    
    # Use existing enterprise ID
    enterprise_id = '68542c1109381de738222350'
    chat_id = 'test_groupchat_integration_001'
    workflow_name = 'Generator'
    
    # Test creating termination handler from groupchat manager
    handler = create_termination_handler(
        chat_id=chat_id,
        enterprise_id=enterprise_id,
        workflow_name=workflow_name
    )
    
    print('✅ Termination handler created successfully')
    
    # Test VE-style conversation lifecycle
    await handler.on_conversation_start()
    status = await handler.check_completion_status()
    print(f'📊 Initial status: {status["current_status"]} (should be 0)')
    
    # Test termination
    result = await handler.on_conversation_end('completed')
    print(f'🎯 Final status: {result.final_status} (should be 1)')
    
    print('✨ Groupchat integration test complete!')

if __name__ == "__main__":
    asyncio.run(test_groupchat_integration())
