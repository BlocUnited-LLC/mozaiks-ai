#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final test to validate OTEL token tracking with correct environment settings."""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Fix Windows Unicode encoding for emojis
import builtins
_original_print = builtins.print

def safe_print(*args, **kwargs):
    """Print function that handles Unicode properly on Windows."""
    try:
        _original_print(*args, **kwargs)
    except UnicodeEncodeError:
        # Fallback: replace emojis with text equivalents
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                # Replace common emojis with text
                text = arg.replace('🚀', '[ROCKET]')
                text = text.replace('🔧', '[WRENCH]') 
                text = text.replace('🔍', '[MAGNIFY]')
                text = text.replace('✅', '[CHECK]')
                text = text.replace('❌', '[X]')
                text = text.replace('⚠️', '[WARNING]')
                text = text.replace('⏳', '[HOURGLASS]')
                text = text.replace('🎉', '[PARTY]')
                text = text.replace('💥', '[EXPLOSION]')
                text = text.replace('🎯', '[TARGET]')
                text = text.replace('📊', '[CHART]')
                safe_args.append(text)
            else:
                safe_args.append(arg)
        _original_print(*safe_args, **kwargs)

# Override print globally
builtins.print = safe_print

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Enable performance persistence for this test
os.environ["MOZAIKS_PERSIST_PERF"] = "1"
os.environ["MOZAIKS_PERF_DEBUG"] = "1"

async def test_complete_pipeline():
    """Test the complete OTEL token tracking pipeline."""
    print("🚀 Testing complete OTEL token tracking pipeline")
    print("🔧 Environment: MOZAIKS_PERSIST_PERF=1, MOZAIKS_PERF_DEBUG=1")
    
    # Test 1: Check performance persistence is enabled
    print("\n🔍 Test 1: Checking performance persistence setting...")
    try:
        from core.observability.performance_store import performance_persistence_enabled
        enabled = performance_persistence_enabled()
        if enabled:
            print("✅ Performance persistence is ENABLED")
        else:
            print("❌ Performance persistence is still DISABLED")
            return False
    except Exception as e:
        print(f"❌ Failed to check persistence setting: {e}")
        return False
    
    # Test 2: Initialize OTEL
    print("\n🔍 Test 2: Initializing OTEL...")
    try:
        from core.observability.otel_helpers import ensure_telemetry_initialized
        result = ensure_telemetry_initialized(enabled=True, auto_disable_on_failure=False)
        if result:
            print("✅ OTEL initialized successfully")
        else:
            print("⚠️ OTEL initialization returned False")
    except Exception as e:
        print(f"❌ OTEL initialization failed: {e}")
        return False
    
    # Test 3: Initialize Performance Manager
    print("\n🔍 Test 3: Initializing Performance Manager...")
    try:
        from core.observability.performance_manager import get_performance_manager
        perf_mgr = await get_performance_manager()
        await perf_mgr.initialize()
        print("✅ Performance Manager initialized")
    except Exception as e:
        print(f"❌ Performance Manager initialization failed: {e}")
        return False
    
    # Test 4: Create a test span with token attributes (simulating agent turn)
    print("\n🔍 Test 4: Creating test span with token attributes...")
    try:
        from core.observability.otel_helpers import timed_span
        
        test_attributes = {
            "chat_id": f"test_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "workflow": "test_workflow",
            "enterprise_id": "test_enterprise",
            "agent": "TestAgent",
            "model": "gpt-4o",
            "prompt_tokens": 120,
            "completion_tokens": 80,
            "total_tokens": 200,
            "cost_usd": 0.001
        }
        
        print(f"🔧 Creating agent_turn span with attributes: {test_attributes}")
        
        with timed_span("agent_turn", attributes=test_attributes):
            # Simulate some agent work
            await asyncio.sleep(0.1)
        
        print("✅ Test span created and completed successfully")
        
    except Exception as e:
        print(f"❌ Test span creation failed: {e}")
        return False
    
    # Test 5: Wait for async persistence and check MongoDB
    print("\n🔍 Test 5: Checking MongoDB document creation...")
    try:
        from core.core_config import get_mongo_client
        
        # Wait for async persistence
        print("⏳ Waiting 3 seconds for async persistence...")
        await asyncio.sleep(3)
        
        mongo_client = get_mongo_client()
        db = mongo_client.get_database("mozaiks_data")
        performance_coll = db.get_collection("Performance")
        
        # Look for documents created in the last 30 seconds
        cutoff_time = datetime.utcnow() - timedelta(seconds=30)
        
        recent_docs = []
        async for doc in performance_coll.find({
            "ts": {"$gte": cutoff_time},
            "key": "agent_turn"
        }).sort("ts", -1):
            doc_info = {
                "_id": str(doc["_id"]),
                "key": doc.get("key"),
                "duration_sec": doc.get("duration_sec"),
                "chat_id": doc.get("chat_id"),
                "agent": doc.get("agent"),
                "prompt_tokens": doc.get("attrs", {}).get("prompt_tokens", 0),
                "completion_tokens": doc.get("attrs", {}).get("completion_tokens", 0),
                "total_tokens": doc.get("attrs", {}).get("total_tokens", 0),
                "cost_usd": doc.get("attrs", {}).get("cost_usd", 0.0),
            }
            recent_docs.append(doc_info)
        
        if recent_docs:
            print(f"✅ Found {len(recent_docs)} recent agent_turn spans:")
            for doc in recent_docs:
                print(f"  📊 {doc['_id'][:8]}... - {doc['agent']}: "
                      f"{doc['total_tokens']} tokens, ${doc['cost_usd']:.6f}")
        else:
            print("❌ No recent agent_turn spans found in Performance collection")
            return False
            
    except Exception as e:
        print(f"❌ MongoDB document check failed: {e}")
        return False
    
    print("\n🎉 Complete pipeline test PASSED!")
    print("✅ OTEL token tracking is working correctly!")
    return True

async def main():
    """Run the complete pipeline test."""
    try:
        success = await test_complete_pipeline()
        if success:
            print("\n🎯 CONCLUSION: OTEL token tracking is fully functional.")
            print("🔧 Make sure to set MOZAIKS_PERSIST_PERF=1 in production environment.")
        else:
            print("\n💥 CONCLUSION: OTEL token tracking has issues that need fixing.")
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
