#!/usr/bin/env python3
"""
Quick integration test for termination handler and orchestration patterns alignment.
"""
import asyncio
import sys
import os
import logging
from unittest.mock import AsyncMock, MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test_termination_handler_integration():
    """Test that termination handler integrates properly with orchestration patterns."""
    try:
        from core.workflow.termination_handler import AG2TerminationHandler, TerminationResult
        from core.data.persistence_manager import AG2PersistenceManager
        
        print("✅ Imports successful")
        
        # Mock persistence manager
        mock_persistence = AsyncMock(spec=AG2PersistenceManager)
        mock_persistence.create_chat_session = AsyncMock()
        mock_persistence.mark_chat_completed = AsyncMock(return_value=True)
        
        # Create termination handler
        handler = AG2TerminationHandler(
            chat_id="test_chat_123",
            enterprise_id="test_enterprise_456", 
            workflow_name="test_workflow",
            persistence_manager=mock_persistence,
            transport=None
        )
        
        print("✅ Termination handler created")
        
        # Test conversation start
        await handler.on_conversation_start("test_user")
        print("✅ Conversation start completed")
        
        # Verify attributes are properly initialized
        assert handler.conversation_active == True
        assert handler.start_time is not None
        assert handler._ended == False
        assert handler._last_result is None
        print("✅ Handler state verified after start")
        
        # Test conversation end
        result = await handler.on_conversation_end("completed", False)
        print(f"✅ Conversation end completed: {result}")
        
        # Verify termination result
        assert isinstance(result, TerminationResult)
        assert result.terminated == True
        assert result.status == "completed"
        assert result.workflow_complete == True
        assert result.session_summary is not None
        print("✅ Termination result verified")
        
        # Test idempotency - second call should return cached result
        result2 = await handler.on_conversation_end("completed", False)
        assert result2 is result  # Same object reference
        print("✅ Idempotency verified")
        
        # Verify persistence calls
        mock_persistence.create_chat_session.assert_called_once()
        mock_persistence.mark_chat_completed.assert_called_once()
        print("✅ Persistence integration verified")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_orchestration_imports():
    """Test that orchestration patterns can import and use termination handler."""
    try:
        from core.workflow.orchestration_patterns import create_orchestration_pattern
        from core.workflow.termination_handler import create_termination_handler
        
        print("✅ Orchestration imports successful")
        
        # Test factory function
        handler = create_termination_handler(
            chat_id="test_chat",
            enterprise_id="test_enterprise", 
            workflow_name="test_workflow"
        )
        
        assert handler is not None
        assert handler.chat_id == "test_chat"
        assert handler.enterprise_id == "test_enterprise"
        assert handler.workflow_name == "test_workflow"
        print("✅ Termination handler factory verified")
        
        return True
        
    except Exception as e:
        print(f"❌ Orchestration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all integration tests."""
    print("🧪 Testing termination handler and orchestration integration...\n")
    
    results = []
    
    print("1. Testing termination handler core functionality...")
    results.append(await test_termination_handler_integration())
    
    print("\n2. Testing orchestration pattern integration...")
    results.append(await test_orchestration_imports())
    
    print(f"\n📊 Test Results: {sum(results)}/{len(results)} passed")
    
    if all(results):
        print("🎉 All tests passed! Termination handler is properly aligned with orchestration patterns.")
        return 0
    else:
        print("❌ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
