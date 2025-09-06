#!/usr/bin/env python3
"""
Test script to diagnose OTEL token tracking issues.

This helps identify why the Performance collection shows zero tokens.
"""

import asyncio
import os
from core.observability.performance_store import debug_span_creation, perf_diagnostics, performance_persistence_enabled, fetch_recent_performance
from core.core_config import get_mongo_client

async def test_otel_token_tracking():
    """Test OTEL token tracking functionality."""
    
    print("🔍 OTEL Token Tracking Diagnostics")
    print("=" * 50)
    
    # 1. Check if performance persistence is enabled
    print(f"Performance persistence enabled: {performance_persistence_enabled()}")
    
    # 2. Show diagnostics
    diagnostics = perf_diagnostics()
    print(f"Diagnostics: {diagnostics}")
    
    # 3. Set debug flag
    os.environ["MOZAIKS_PERF_DEBUG"] = "1"
    
    # 4. Test MongoDB connection
    print("\n🔌 Testing MongoDB connection...")
    try:
        client = get_mongo_client()
        db = client["MozaiksAI"]
        perf_collection = db["Performance"]
        
        # Count existing documents
        existing_count = await perf_collection.count_documents({})
        print(f"Existing Performance documents: {existing_count}")
        
        # Test basic write
        test_doc = {
            "_id": "test_connection_check",
            "test": True,
            "message": "MongoDB connection test"
        }
        await perf_collection.insert_one(test_doc)
        print("✅ MongoDB write test successful")
        
        # Clean up test doc
        await perf_collection.delete_one({"_id": "test_connection_check"})
        
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return
    
    # 5. Test manual span creation with known token values
    print("\n🧪 Testing manual span creation...")
    debug_span_creation(
        chat_id="test_chat_123",
        agent_name="TestAgent", 
        duration_sec=2.5,
        prompt_tokens=1000,
        completion_tokens=500,
        cost_usd=0.05
    )
    
    # 6. Wait longer for async processing and check results
    print("⏳ Waiting for async processing...")
    await asyncio.sleep(3)
    
    # 7. Check if documents were created
    print("\n📊 Checking Performance collection...")
    try:
        # Check for chat-level document
        chat_doc = await perf_collection.find_one({"_id": "perf_test_chat_123"})
        if chat_doc:
            print("✅ Found chat performance document:")
            print(f"  - agent_turns: {chat_doc.get('agent_turns', 0)}")
            print(f"  - total_tokens: {chat_doc.get('total_tokens', 0)}")
            print(f"  - agents: {list(chat_doc.get('agents', {}).keys())}")
        else:
            print("❌ No chat performance document found")
        
        # Check for workflow-level document  
        workflow_doc = await perf_collection.find_one({"_id": "perf_mon_debug_enterprise_debug_workflow"})
        if workflow_doc:
            print("✅ Found workflow performance summary:")
            print(f"  - total_agent_turns: {workflow_doc.get('total_agent_turns', 0)}")
            print(f"  - total_tokens: {workflow_doc.get('total_tokens', 0)}")
            print(f"  - agents: {list(workflow_doc.get('agents', {}).keys())}")
        else:
            print("❌ No workflow performance summary found")
            
        # Show recent documents for debugging
        recent_docs = await fetch_recent_performance(limit=3)
        print(f"\n📋 Recent Performance documents ({len(recent_docs)}):")
        for doc in recent_docs:
            doc_type = doc.get('type', 'unknown')
            doc_id = doc.get('_id', 'no_id')
            print(f"  - {doc_id} (type: {doc_type})")
            
    except Exception as e:
        print(f"❌ Error checking Performance collection: {e}")
    
    print("\n✅ Test completed!")
    print("\n💡 If no documents were found, this suggests:")
    print("   1. The async task scheduling isn't working properly")
    print("   2. OTEL spans aren't being created")
    print("   3. The performance_store filtering is too restrictive")

if __name__ == "__main__":
    # Enable performance persistence for testing
    os.environ["MOZAIKS_PERSIST_PERF"] = "1"
    asyncio.run(test_otel_token_tracking())
