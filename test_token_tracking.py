#!/usr/bin/env python3
"""
Test script to validate improved AG2 token counting and logging functionality.

Usage:
    python test_token_tracking.py

This script tests:
1. AG2 runtime logging setup and token capture
2. Enhanced logging with gather_usage_summary
3. WorkflowStats persistence of usage and duration
4. Database persistence of token counts

Run this after implementing the AG2 logging improvements to validate functionality.
"""

import asyncio
import os
import sys
import uuid
import logging
from datetime import datetime
from typing import Dict, Any

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_ag2_token_tracking():
    """Test the enhanced AG2 token tracking capabilities."""
    
    print("🧪 Testing Enhanced AG2 Token Tracking")
    print("=" * 50)
    
    # Test 1: AG2 Runtime Logger Setup
    print("\n1. Testing AG2 Runtime Logger Setup...")
    try:
        from core.observability.ag2_runtime_logger import get_ag2_runtime_logger
        
        logger = get_ag2_runtime_logger()
        test_chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"
        test_workflow = "test_token_tracking"
        
        # Test logging session
        started = logger.start_session(test_chat_id, test_workflow, "test_enterprise")
        print(f"   ✅ AG2 runtime logger started: {started}")
        
        if started:
            # Simulate some logging activity
            print(f"   📁 Log file: {logger.log_file_path}")
            
            # Stop and get summary
            stopped = logger.stop_session() 
            print(f"   ⏹️ AG2 runtime logger stopped: {stopped}")
        else:
            print("   ⚠️ AG2 runtime logging disabled or unavailable")
            
    except Exception as e:
        print(f"   ❌ AG2 runtime logger test failed: {e}")
    
    # Test 2: Performance Manager Integration  
    print("\n2. Testing Performance Manager Token Recording...")
    try:
        from core.observability.performance_manager import get_performance_manager
        
        perf_mgr = await get_performance_manager()
        test_chat_id = f"test_perf_{uuid.uuid4().hex[:8]}"
        
        # Initialize a workflow session
        await perf_mgr.record_workflow_start(
            test_chat_id, "test_enterprise", "test_workflow", "test_user"
        )
        print("   ✅ Workflow session started")
        
        # Record some agent turns with token usage
        test_turns = [
            {"agent": "test_agent_1", "prompt": 100, "completion": 50, "cost": 0.001},
            {"agent": "test_agent_2", "prompt": 200, "completion": 75, "cost": 0.002},
            {"agent": "test_agent_1", "prompt": 150, "completion": 25, "cost": 0.0015},
        ]
        
        for turn in test_turns:
            await perf_mgr.record_agent_turn(
                chat_id=test_chat_id,
                agent_name=turn["agent"], 
                duration_sec=1.5,
                model="gpt-4",
                prompt_tokens=turn["prompt"],
                completion_tokens=turn["completion"],
                cost=turn["cost"]
            )
            print(f"   💰 Recorded turn: {turn['agent']} -> {turn['prompt']+turn['completion']} tokens, ${turn['cost']}")
        
        # Get session snapshot
        snapshot = await perf_mgr.snapshot_chat(test_chat_id)
        if snapshot:
            print(f"   📊 Session snapshot: {snapshot['prompt_tokens']} prompt + {snapshot['completion_tokens']} completion = {snapshot['prompt_tokens']+snapshot['completion_tokens']} total tokens, ${snapshot['cost']:.6f}")
        else:
            print("   ⚠️ No session snapshot available")
            
        # Finalize workflow
        from core.data.models import WorkflowStatus
        await perf_mgr.record_workflow_end(test_chat_id, WorkflowStatus.COMPLETED)
        print("   ✅ Workflow session completed")
        
    except Exception as e:
        print(f"   ❌ Performance manager test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Database Token Storage
    print("\n3. Testing Database Token Storage...")
    try:
        from core.data.persistence_manager import AG2PersistenceManager
        
        pm = AG2PersistenceManager()
        test_chat_id = f"test_db_{uuid.uuid4().hex[:8]}"
        
        # Create a test session
        await pm.create_chat_session(test_chat_id, "test_enterprise", "test_workflow", "test_user")
        print("   ✅ Chat session created")
        
        # Update session metrics multiple times
        await pm.update_session_metrics(
            chat_id=test_chat_id,
            enterprise_id="test_enterprise", 
            user_id="test_user",
            workflow_name="test_workflow",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
            agent_name="test_agent",
            duration_sec=1.2
        )
        print("   💰 First metrics update: 100+50 tokens, $0.001")
        
        await pm.update_session_metrics(
            chat_id=test_chat_id,
            enterprise_id="test_enterprise",
            user_id="test_user", 
            workflow_name="test_workflow",
            prompt_tokens=75,
            completion_tokens=25,
            cost_usd=0.0008,
            agent_name="test_agent_2",
            duration_sec=0.8
        )
        print("   💰 Second metrics update: 75+25 tokens, $0.0008")
        
        # Check if metrics were persisted
        print("   📊 Metrics should be visible in ChatSessions collection")
        
    except Exception as e:
        print(f"   ❌ Database token storage test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Environment Configuration Check
    print("\n4. Testing Environment Configuration...")
    
    env_vars = [
        "AG2_RUNTIME_LOGGING",
        "AG2_RUNTIME_LOG_FILE",
        "LOGS_BASE_DIR", 
        "LOGS_AS_JSON"
    ]
    
    for var in env_vars:
        value = os.getenv(var, "<not set>")
        status = "✅" if value != "<not set>" else "⚠️"
        print(f"   {status} {var}: {value}")
    
    # Test 5: AG2 Gather Usage Summary (if available)
    print("\n5. Testing AG2 gather_usage_summary...")
    try:
        from autogen import gather_usage_summary
        print("   ✅ autogen.gather_usage_summary is available")
        
        # Note: Can't easily test without actual agents, but import succeeded
        print("   📝 gather_usage_summary can be used for final reconciliation")
        
    except ImportError as e:
        print(f"   ❌ autogen.gather_usage_summary not available: {e}")
    except Exception as e:
        print(f"   ⚠️ gather_usage_summary import issue: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 AG2 Token Tracking Test Complete!")
    print("\nNext steps:")
    print("1. Check logs/logs/ag2_runtime.log for AG2 runtime logging output")
    print("2. Verify ChatSessions collection in MongoDB for token metrics")
    print("3. Inspect WorkflowStats (mon_<enterprise>_<workflow>) for real-time usage/duration")
    print("4. Test with actual workflow execution to see full integration")

if __name__ == "__main__":
    # Configure basic logging to see test output
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(test_ag2_token_tracking())