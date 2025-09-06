#!/usr/bin/env python3
"""Simplified OTEL test to diagnose token tracking issues."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_basic_functionality():
    """Test basic functionality to identify issues."""
    print("🚀 Starting simplified OTEL diagnostics")
    
    # Test 1: MongoDB connection
    print("🔍 Testing MongoDB...")
    try:
        from core.core_config import get_mongo_client
        mongo_client = get_mongo_client()
        await mongo_client.admin.command('ping')
        print("✅ MongoDB connected")
        
        # Check Performance collection
        db = mongo_client.get_database("mozaiks_data")
        perf_coll = db.get_collection("Performance")
        count = await perf_coll.count_documents({})
        print(f"✅ Performance collection has {count} documents")
        
    except Exception as e:
        print(f"❌ MongoDB error: {e}")
        return False
    
    # Test 2: OTEL environment
    print("🔍 Testing OTEL environment...")
    try:
        import os
        openlit_enabled = os.getenv("OPENLIT_ENABLED", "NOT_SET")
        otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "NOT_SET")
        print(f"OPENLIT_ENABLED: {openlit_enabled}")
        print(f"OTEL_EXPORTER_OTLP_ENDPOINT: {otel_endpoint}")
        
        from core.observability.otel_helpers import ensure_telemetry_initialized
        result = ensure_telemetry_initialized(enabled=True, auto_disable_on_failure=False)
        print(f"✅ OTEL init result: {result}")
        
    except Exception as e:
        print(f"❌ OTEL error: {e}")
        return False
    
    # Test 3: Performance manager
    print("🔍 Testing Performance Manager...")
    try:
        from core.observability.performance_manager import get_performance_manager
        perf_mgr = await get_performance_manager()
        await perf_mgr.initialize()
        print("✅ Performance Manager initialized")
        
    except Exception as e:
        print(f"❌ Performance Manager error: {e}")
        return False
    
    # Test 4: Token tracking
    print("🔍 Testing token tracking...")
    try:
        from core.workflow.orchestration_patterns import track_agent_usage
        
        # Simple test
        test_usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        test_context = {
            "chat_id": "test_chat_simple",
            "enterprise_id": "test_enterprise", 
            "workflow": "test",
            "span_id": "test_span",
            "agent_name": "TestAgent"
        }
        
        track_agent_usage("TestAgent", test_usage, test_context)
        print("✅ Token tracking called successfully")
        
    except Exception as e:
        print(f"❌ Token tracking error: {e}")
        return False
    
    print("🎉 All basic tests passed!")
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_basic_functionality())
        print(f"Final result: {result}")
    except Exception as e:
        print(f"Test execution failed: {e}")
        import traceback
        traceback.print_exc()
