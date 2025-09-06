#!/usr/bin/env python3
"""Debug test to see what's happening in persist_span_summary."""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Enable performance persistence and debug
os.environ["MOZAIKS_PERSIST_PERF"] = "1"
os.environ["MOZAIKS_PERF_DEBUG"] = "1"

async def test_persist_span_directly():
    """Test persist_span_summary directly to see what happens."""
    print("Testing persist_span_summary directly...")
    
    try:
        from core.observability.performance_store import persist_span_summary, performance_persistence_enabled
        
        print(f"Performance persistence enabled: {performance_persistence_enabled()}")
        
        # Test attributes (same as from the working test)
        test_attributes = {
            "chat_id": "direct_test_chat",
            "workflow": "test_workflow",
            "enterprise_id": "test_enterprise", 
            "agent": "DirectTestAgent",
            "model": "gpt-4o",
            "prompt_tokens": 150,
            "completion_tokens": 90,
            "total_tokens": 240,
            "cost_usd": 0.0015
        }
        
        print(f"Calling persist_span_summary with attributes: {test_attributes}")
        
        # Call persist_span_summary directly
        result = persist_span_summary("agent_turn", 2.5, test_attributes)
        print(f"persist_span_summary returned: {result}")
        
        # Wait for async operations
        await asyncio.sleep(2)
        
        # Check if document was created
        from core.core_config import get_mongo_client
        mongo_client = get_mongo_client()
        db = mongo_client.get_database("mozaiks_data")
        performance_coll = db.get_collection("Performance")
        
        # Look for our test document
        test_docs = []
        async for doc in performance_coll.find({"chat_id": "direct_test_chat"}):
            test_docs.append(doc)
        
        if test_docs:
            print(f"Found {len(test_docs)} test documents:")
            for doc in test_docs:
                print(f"  Document: {doc}")
        else:
            print("No test documents found")
            
            # Check all recent documents
            from datetime import datetime, timedelta
            cutoff = datetime.utcnow() - timedelta(minutes=1)
            recent_count = await performance_coll.count_documents({
                "ts": {"$gte": cutoff}
            })
            print(f"Recent documents in last minute: {recent_count}")
        
    except Exception as e:
        print(f"Error in direct test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_persist_span_directly())
