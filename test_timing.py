#!/usr/bin/env python3
"""Better test with proper async waiting and debug logging."""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Enable performance persistence and debug
os.environ["MOZAIKS_PERSIST_PERF"] = "1"
os.environ["MOZAIKS_PERF_DEBUG"] = "1"

async def test_with_proper_timing():
    """Test with proper timing for async operations."""
    print("Testing OTEL token tracking with proper async timing...")
    
    # Step 1: Test direct persist call
    print("\n1. Testing persist_span_summary directly...")
    from core.observability.performance_store import persist_span_summary, performance_persistence_enabled
    
    print(f"Performance persistence enabled: {performance_persistence_enabled()}")
    
    test_attributes = {
        "chat_id": "timing_test_chat",
        "workflow": "test_workflow", 
        "enterprise_id": "test_enterprise",
        "agent": "TimingTestAgent",
        "model": "gpt-4o",
        "prompt_tokens": 200,
        "completion_tokens": 100,
        "total_tokens": 300,
        "cost_usd": 0.002
    }
    
    print(f"Calling persist_span_summary with: {test_attributes}")
    result = persist_span_summary("agent_turn", 1.5, test_attributes)
    print(f"persist_span_summary returned: {result}")
    
    # Step 2: Wait longer for async task completion
    print("\n2. Waiting 10 seconds for async task completion...")
    await asyncio.sleep(10)
    
    # Step 3: Check MongoDB
    print("\n3. Checking MongoDB for documents...")
    from core.core_config import get_mongo_client
    mongo_client = get_mongo_client()
    db = mongo_client.get_database("mozaiks_data")
    performance_coll = db.get_collection("Performance")
    
    # Look for our specific test document
    test_doc = await performance_coll.find_one({"_id": "perf_timing_test_chat"})
    if test_doc:
        print(f"✅ Found chat-level document: {test_doc}")
        tokens = test_doc.get("total_tokens", 0)
        print(f"   Total tokens: {tokens}")
    else:
        print("❌ No chat-level document found")
    
    # Look for workflow aggregate
    workflow_doc = await performance_coll.find_one({"_id": "perf_mon_test_enterprise_test_workflow"})
    if workflow_doc:
        print(f"✅ Found workflow-level document: {workflow_doc}")
        tokens = workflow_doc.get("total_tokens", 0)
        print(f"   Total tokens: {tokens}")
    else:
        print("❌ No workflow-level document found")
    
    # Check any recent documents
    cutoff = datetime.utcnow() - timedelta(minutes=2)
    recent_docs = []
    async for doc in performance_coll.find({"ts": {"$gte": cutoff}}).limit(5):
        recent_docs.append({
            "_id": str(doc["_id"]),
            "key": doc.get("key"),
            "total_tokens": doc.get("total_tokens", 0),
            "agent_turns": doc.get("agent_turns", 0)
        })
    
    if recent_docs:
        print(f"\n✅ Found {len(recent_docs)} recent documents:")
        for doc in recent_docs:
            print(f"   {doc}")
    else:
        print("\n❌ No recent documents found at all")
    
    # Step 4: Test via timed_span (the real path)
    print("\n4. Testing via timed_span (real execution path)...")
    from core.observability.otel_helpers import timed_span
    
    span_attributes = {
        "chat_id": "timed_span_test_chat",
        "workflow": "test_workflow",
        "enterprise_id": "test_enterprise", 
        "agent": "TimedSpanTestAgent",
        "model": "gpt-4o",
        "prompt_tokens": 180,
        "completion_tokens": 120,
        "total_tokens": 300,
        "cost_usd": 0.0025
    }
    
    print(f"Creating timed_span with: {span_attributes}")
    with timed_span("agent_turn", attributes=span_attributes):
        await asyncio.sleep(0.2)  # Simulate work
    
    print("Waiting 10 seconds for timed_span persistence...")
    await asyncio.sleep(10)
    
    # Check for timed_span document  
    timed_doc = await performance_coll.find_one({"_id": "perf_timed_span_test_chat"})
    if timed_doc:
        print(f"✅ Found timed_span document: {timed_doc}")
        tokens = timed_doc.get("total_tokens", 0)
        print(f"   Total tokens: {tokens}")
    else:
        print("❌ No timed_span document found")

if __name__ == "__main__":
    asyncio.run(test_with_proper_timing())
