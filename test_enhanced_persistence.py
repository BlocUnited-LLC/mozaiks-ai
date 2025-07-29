#!/usr/bin/env python3
"""
Test enhanced persistence manager with workflow management and AG2 iostream integration
"""
import asyncio
import logging
from datetime import datetime

from core.data.token_manager import TokenManager
from core.transport.ag2_iostream import AG2StreamingManager
from logs.logging_config import get_chat_logger

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = get_chat_logger("test_enhanced_persistence")

# Test data
CHAT_ID = "test_enhanced_chat_001"
ENTERPRISE_ID = "68542c1109381de738222350"  # Real enterprise ID from frontend
USER_ID = "test_user_123"
WORKFLOW_NAME = "Generator"

async def test_enhanced_workflow_management():
    """Test the enhanced workflow management features"""
    logger.info("🧪 Testing Enhanced Workflow Management Features")
    
    try:
        # 1. Create TokenManager with workflow support
        token_manager = TokenManager(
            chat_id=CHAT_ID,
            enterprise_id=ENTERPRISE_ID,
            user_id=USER_ID,
            workflow_name=WORKFLOW_NAME
        )
        
        logger.info(f"✅ Created TokenManager for workflow: {WORKFLOW_NAME}")
        
        # 2. Create AG2 streaming manager with workflow support
        streaming_manager = AG2StreamingManager(
            chat_id=CHAT_ID,
            enterprise_id=ENTERPRISE_ID,
            user_id=USER_ID,
            workflow_name=WORKFLOW_NAME
        )
        
        logger.info(f"✅ Created AG2StreamingManager with TokenManager integration")
        
        # 3. Test workflow status management
        logger.info("📊 Testing workflow status management...")
        
        # Set initial status (0 = in progress)
        await token_manager.update_workflow_status(0)
        status = await token_manager.get_workflow_status()
        logger.info(f"   Initial workflow status: {status}")
        
        # 4. Test workflow state saving
        logger.info("💾 Testing workflow state saving...")
        
        test_state = {
            "current_step": "agent_generation",
            "agents_created": 3,
            "context_variables": ["api_key", "user_preference"],
            "completion_percentage": 45
        }
        
        await token_manager.save_workflow_state(test_state)
        logger.info(f"   Saved workflow state: {test_state}")
        
        # 5. Test message tracking
        logger.info("💬 Testing enhanced message tracking...")
        
        test_messages = [
            ("APIKeyAgent", "Please provide your OpenAI API key for the workflow."),
            ("User", "sk-test-1234567890abcdef"),
            ("AgentsAgent", '{"agent_list": [{"name": "DataAnalyst", "role": "analysis"}, {"name": "Visualizer", "role": "visualization"}]}'),
            ("ContextVariablesAgent", '{"context_variables": {"api_key": "string", "dataset_path": "string"}}')
        ]
        
        for sender, content in test_messages:
            await token_manager.add_message(sender, content)
            logger.info(f"   Added message from {sender}: {len(content)} chars")
        
        # 6. Test chat history retrieval
        logger.info("📜 Testing chat history retrieval...")
        
        history = await token_manager.get_chat_history()
        logger.info(f"   Retrieved {len(history)} messages from history")
        
        for i, msg in enumerate(history[-2:], 1):  # Show last 2 messages
            logger.info(f"   Message {i}: {msg['sender']} -> {msg['content'][:50]}{'...' if len(msg['content']) > 50 else ''}")
        
        # 7. Test connection state management
        logger.info("🔗 Testing connection state management...")
        
        await token_manager.mark_connection_state("connected", {"transport": "ag2_websocket", "client_ip": "127.0.0.1"})
        logger.info("   Marked as connected via AG2 WebSocket")
        
        # 8. Test resume capability
        logger.info("🔄 Testing resume capability...")
        
        can_resume = await token_manager.can_resume_workflow()
        logger.info(f"   Can resume workflow: {can_resume}")
        
        if can_resume:
            resumed, resume_data = await token_manager.resume_workflow()
            if resumed and resume_data:
                logger.info(f"   Resume data available:")
                logger.info(f"     - Status: {resume_data.get('status')}")
                logger.info(f"     - Conversation messages: {len(resume_data.get('conversation', []))}")
                logger.info(f"     - State data: {bool(resume_data.get('state'))}")
        
        # 9. Test workflow progression
        logger.info("⚡ Testing workflow progression...")
        
        # Simulate workflow steps
        workflow_steps = [
            (25, {"current_step": "agents_generation", "agents_created": 5}),
            (50, {"current_step": "context_variables", "variables_created": 8}),
            (75, {"current_step": "handoffs_configuration", "handoffs_created": 3}),
            (100, {"current_step": "workflow_complete", "all_components_ready": True})
        ]
        
        for step_status, step_state in workflow_steps:
            await token_manager.update_workflow_status(step_status)
            await token_manager.save_workflow_state(step_state)
            logger.info(f"   Workflow step: {step_status}% - {step_state.get('current_step')}")
        
        # 10. Test workflow completion
        logger.info("✅ Testing workflow completion...")
        
        # Finalize the session (which calls finalize_conversation internally)
        session_summary = await token_manager.finalize_session()
        logger.info(f"   Session finalized with summary:")
        logger.info(f"     - Total tokens: {session_summary.get('total_tokens', 0)}")
        logger.info(f"     - Total cost: ${session_summary.get('total_cost', 0):.6f}")
        logger.info(f"     - Duration: {session_summary.get('session_duration_ms', 0)}ms")
        
        # 11. Test post-completion resume check
        logger.info("🔍 Testing post-completion resume check...")
        
        can_resume_after = await token_manager.can_resume_workflow()
        logger.info(f"   Can resume after completion: {can_resume_after}")
        
        if not can_resume_after:
            # Try to resume and check for completion status
            resumed, resume_data = await token_manager.resume_workflow()
            if not resumed and resume_data and resume_data.get("already_complete"):
                logger.info(f"   ✅ Workflow properly marked as complete with status: {resume_data.get('status')}")
        
        logger.info("🎉 Enhanced workflow management test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhanced workflow management test failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False

async def test_ag2_iostream_integration():
    """Test AG2 iostream integration with TokenManager"""
    logger.info("🧪 Testing AG2 IOStream Integration")
    
    try:
        # 1. Create AG2 streaming manager
        streaming_manager = AG2StreamingManager(
            chat_id=CHAT_ID + "_iostream",
            enterprise_id=ENTERPRISE_ID,
            user_id=USER_ID,
            workflow_name="TestWorkflow"
        )
        
        # 2. Setup streaming
        iostream = streaming_manager.setup_streaming()
        logger.info("✅ AG2 IOStream setup completed")
        
        # 3. Test agent context setting
        iostream.set_agent_context("TestAgent")
        logger.info("✅ Agent context set for IOStream")
        
        # 4. Test message streaming (simulates AG2 calling print)
        test_outputs = [
            "Hello! I'm starting the workflow.",
            "Processing your request...",
            '{"agents": [{"name": "DataProcessor", "role": "processing"}]}',
            "Workflow completed successfully!"
        ]
        
        for output in test_outputs:
            iostream.print(output)
            await asyncio.sleep(0.1)  # Simulate streaming delay
        
        logger.info(f"✅ Streamed {len(test_outputs)} messages through AG2 IOStream")
        
        # 5. Test TokenManager integration
        if iostream.token_manager:
            history = await iostream.token_manager.get_chat_history()
            logger.info(f"✅ TokenManager integration working: {len(history)} messages tracked")
        else:
            logger.warning("⚠️ TokenManager not initialized in IOStream")
        
        # 6. Cleanup
        streaming_manager.cleanup()
        logger.info("✅ AG2 IOStream cleanup completed")
        
        logger.info("🎉 AG2 IOStream integration test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ AG2 IOStream integration test failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False

async def main():
    """Run all enhanced persistence tests"""
    logger.info("🚀 Starting Enhanced Persistence & AG2 Integration Tests")
    
    # Test 1: Enhanced workflow management
    workflow_test = await test_enhanced_workflow_management()
    
    # Test 2: AG2 iostream integration  
    iostream_test = await test_ag2_iostream_integration()
    
    # Summary
    logger.info("📊 Test Results Summary:")
    logger.info(f"  Enhanced Workflow Management: {'✅ PASS' if workflow_test else '❌ FAIL'}")
    logger.info(f"  AG2 IOStream Integration: {'✅ PASS' if iostream_test else '❌ FAIL'}")
    
    if workflow_test and iostream_test:
        logger.info("🎉 All tests passed! Enhanced persistence system is working correctly.")
    else:
        logger.error("❌ Some tests failed. Check the logs above for details.")

if __name__ == "__main__":
    asyncio.run(main())
