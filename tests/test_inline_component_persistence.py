"""
Test inline component persistence across WebSocket reconnections.

This test simulates:
1. Agent invoking an inline UI tool
2. User responding to the tool
3. UI tool completion event
4. WebSocket disconnect/reconnect
5. Message replay with persisted completion state

No LLM or AG2 required - pure runtime persistence testing.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, UTC
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data.persistence.persistence_manager import AG2PersistenceManager
from core.transport.resume_groupchat import GroupChatResumer
from core.core_config import get_mongo_client


# Global persistence manager instance
_pm_instance = None


async def get_pm():
    """Get or create AG2PersistenceManager instance."""
    global _pm_instance
    if _pm_instance is None:
        _pm_instance = AG2PersistenceManager()
        # _coll() will call _ensure_client() internally
    return _pm_instance


async def cleanup_test_data(chat_id: str, enterprise_id: str):
    """Clean up test chat session."""
    try:
        client = get_mongo_client()
        db = client["MozaiksAI"]
        await db["ChatSessions"].delete_one({"_id": chat_id, "enterprise_id": enterprise_id})
        print(f"✅ Cleaned up test chat: {chat_id}")
    except Exception as e:
        print(f"⚠️ Cleanup failed: {e}")


async def test_inline_component_persistence():
    """Test complete inline component persistence flow."""
    
    print("\n" + "="*80)
    print("INLINE COMPONENT PERSISTENCE TEST")
    print("="*80 + "\n")
    
    # Test data
    chat_id = f"test-chat-{uuid4().hex[:8]}"
    enterprise_id = "test-enterprise-123"
    workflow_name = "TestWorkflow"
    tool_id = "ActionPlanApprovalForm"
    event_id = f"tool-evt-{uuid4().hex[:8]}"
    
    print(f"📝 Test Setup:")
    print(f"   Chat ID: {chat_id}")
    print(f"   Enterprise ID: {enterprise_id}")
    print(f"   Tool ID: {tool_id}")
    print(f"   Event ID: {event_id}\n")
    
    try:
        # ===================================================================
        # STEP 1: Create chat session and simulate agent message
        # ===================================================================
        print("📌 STEP 1: Creating chat session with agent message...")
        
        pm = await get_pm()
        coll = await pm._coll()
        
        # Create chat session
        chat_doc = {
            "_id": chat_id,
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "user_id": "test-user-123",
            "status": 0,  # IN_PROGRESS (0 = in progress, 1 = completed)
            "cache_seed": 12345,
            "created_at": datetime.now(UTC),
            "last_updated_at": datetime.now(UTC),
            "last_sequence": 1,
            "messages": [
                {
                    "role": "assistant",
                    "agent_name": "ActionPlanArchitect",
                    "content": "Please review and approve the action plan.",
                    "event_id": f"msg-{uuid4().hex[:8]}",
                    "sequence": 1,
                    "timestamp": datetime.now(UTC),
                    "event_type": "message.created"
                }
            ]
        }
        
        await coll.insert_one(chat_doc)
        print(f"   ✅ Created chat session with 1 agent message\n")
        
        # ===================================================================
        # STEP 2: Attach UI tool metadata (simulates tool invocation)
        # ===================================================================
        print("📌 STEP 2: Attaching UI tool metadata (tool invocation)...")
        
        ui_tool_payload = {
            "title": "Approve Action Plan",
            "description": "Review the action plan and select an option",
            "options": ["Approve", "Request Revisions"],
            "agent_name": "ActionPlanArchitect"
        }
        
        await pm.attach_ui_tool_metadata(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            event_id=event_id,
            metadata={
                "ui_tool_id": tool_id,
                "event_id": event_id,
                "display": "inline",
                "ui_tool_completed": False,
                "payload": ui_tool_payload,
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        
        print(f"   ✅ Attached UI tool metadata to last message\n")
        
        # Verify metadata was attached
        doc = await coll.find_one({"_id": chat_id}, {"messages": 1})
        last_msg = doc["messages"][-1]
        
        if "metadata" in last_msg and "ui_tool" in last_msg["metadata"]:
            ui_tool_meta = last_msg["metadata"]["ui_tool"]
            print(f"   ✓ Metadata verification:")
            print(f"      ui_tool_id: {ui_tool_meta.get('ui_tool_id')}")
            print(f"      event_id: {ui_tool_meta.get('event_id')}")
            print(f"      display: {ui_tool_meta.get('display')}")
            print(f"      ui_tool_completed: {ui_tool_meta.get('ui_tool_completed')}")
            print()
        else:
            print(f"   ❌ ERROR: Metadata not found in message!")
            return False
        
        # ===================================================================
        # STEP 3: Simulate user response and mark as completed
        # ===================================================================
        print("📌 STEP 3: Simulating user response and marking as completed...")
        
        await pm.update_ui_tool_completion(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            event_id=event_id,
            completed=True,
            status="completed"
        )
        
        print(f"   ✅ Updated UI tool completion status\n")
        
        # Verify completion was updated
        doc = await coll.find_one({"_id": chat_id}, {"messages": 1})
        last_msg = doc["messages"][-1]
        ui_tool_meta = last_msg["metadata"]["ui_tool"]
        
        if ui_tool_meta.get("ui_tool_completed") is True:
            print(f"   ✓ Completion verification:")
            print(f"      ui_tool_completed: {ui_tool_meta.get('ui_tool_completed')}")
            print(f"      ui_tool_status: {ui_tool_meta.get('ui_tool_status')}")
            print(f"      completed_at: {ui_tool_meta.get('completed_at')}")
            print()
        else:
            print(f"   ❌ ERROR: Completion status not updated!")
            return False
        
        # ===================================================================
        # STEP 4: Simulate resume flow (message replay)
        # ===================================================================
        print("📌 STEP 4: Simulating WebSocket reconnect and message replay...")
        
        resumer = GroupChatResumer()
        
        # Fetch messages from persistence (simulates resume)
        messages = await pm.resume_chat(
            chat_id=chat_id,
            enterprise_id=enterprise_id
        )
        
        if not messages:
            print(f"   ❌ ERROR: No messages returned from resume_chat!")
            return False
        
        print(f"   ✓ Fetched {len(messages)} message(s) from persistence")
        
        # Build text events (simulates _replay_messages logic)
        replayed_events = []
        for idx, msg in enumerate(messages):
            event = resumer._build_text_event(
                message=msg,
                index=idx,
                chat_id=chat_id
            )
            replayed_events.append(event)
        
        print(f"   ✓ Built {len(replayed_events)} text event(s) for replay\n")
        
        # ===================================================================
        # STEP 5: Verify UI tool state in replayed event
        # ===================================================================
        print("📌 STEP 5: Verifying UI tool state restoration in replayed event...")
        
        # Find the event with UI tool metadata
        ui_tool_event = None
        for event in replayed_events:
            if "uiToolEvent" in event:
                ui_tool_event = event
                break
        
        if not ui_tool_event:
            print(f"   ❌ ERROR: No uiToolEvent found in replayed events!")
            print(f"   📄 Replayed events: {replayed_events}")
            return False
        
        print(f"   ✓ Found UI tool event in replayed messages")
        print(f"   ✓ Event structure:")
        print(f"      kind: {ui_tool_event.get('kind')}")
        print(f"      agent: {ui_tool_event.get('agent')}")
        print(f"      replay: {ui_tool_event.get('replay')}")
        print()
        
        # Check uiToolEvent reconstruction
        ui_tool_obj = ui_tool_event.get("uiToolEvent", {})
        print(f"   ✓ uiToolEvent object:")
        print(f"      ui_tool_id: {ui_tool_obj.get('ui_tool_id')}")
        print(f"      eventId: {ui_tool_obj.get('eventId')}")
        print(f"      display: {ui_tool_obj.get('display')}")
        print(f"      payload: {ui_tool_obj.get('payload', {}).get('title')}")
        print()
        
        # CRITICAL CHECK: Verify completion state is surfaced
        ui_tool_completed = ui_tool_event.get("ui_tool_completed")
        ui_tool_status = ui_tool_event.get("ui_tool_status")
        
        print(f"   ✓ Completion state (passed to frontend):")
        print(f"      ui_tool_completed: {ui_tool_completed}")
        print(f"      ui_tool_status: {ui_tool_status}")
        print()
        
        # ===================================================================
        # STEP 6: Final validation
        # ===================================================================
        print("📌 STEP 6: Final validation...")
        
        success = True
        errors = []
        
        # Check 1: uiToolEvent exists
        if "uiToolEvent" not in ui_tool_event:
            errors.append("uiToolEvent object not reconstructed")
            success = False
        
        # Check 2: ui_tool_completed is True
        if ui_tool_completed is not True:
            errors.append(f"ui_tool_completed should be True, got {ui_tool_completed}")
            success = False
        
        # Check 3: ui_tool_status is 'completed'
        if ui_tool_status != "completed":
            errors.append(f"ui_tool_status should be 'completed', got {ui_tool_status}")
            success = False
        
        # Check 4: uiToolEvent has all required fields
        required_fields = ["ui_tool_id", "eventId", "display", "payload"]
        for field in required_fields:
            if field not in ui_tool_obj:
                errors.append(f"uiToolEvent missing required field: {field}")
                success = False
        
        if success:
            print("   ✅ ALL CHECKS PASSED!")
            print()
            print("   📋 Summary:")
            print("      ✓ UI tool metadata persisted to MongoDB")
            print("      ✓ Completion state updated after user response")
            print("      ✓ uiToolEvent reconstructed during resume")
            print("      ✓ Completion state surfaced to frontend (ui_tool_completed=True)")
            print()
            print("   🎉 Frontend will render: '✓ ActionPlanApprovalForm completed'")
            print("   🎉 Instead of: Interactive form component")
        else:
            print("   ❌ TEST FAILED!")
            print()
            print("   📋 Errors:")
            for error in errors:
                print(f"      ✗ {error}")
        
        print()
        return success
        
    except Exception as e:
        print(f"\n❌ TEST EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        print("\n📌 Cleaning up test data...")
        await cleanup_test_data(chat_id, enterprise_id)
        print()


async def test_inline_component_in_progress():
    """Test that in-progress (non-completed) UI tools also restore correctly."""
    
    print("\n" + "="*80)
    print("IN-PROGRESS INLINE COMPONENT TEST")
    print("="*80 + "\n")
    
    chat_id = f"test-chat-{uuid4().hex[:8]}"
    enterprise_id = "test-enterprise-456"
    workflow_name = "TestWorkflow"
    tool_id = "RevisionRequestForm"
    event_id = f"tool-evt-{uuid4().hex[:8]}"
    
    print(f"📝 Test Setup:")
    print(f"   Chat ID: {chat_id}")
    print(f"   Tool ID: {tool_id} (in-progress, not completed)")
    print()
    
    try:
        pm = await get_pm()
        coll = await pm._coll()
        
        # Create chat with agent message
        chat_doc = {
            "_id": chat_id,
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "user_id": "test-user-456",
            "status": 0,  # IN_PROGRESS
            "cache_seed": 54321,
            "created_at": datetime.now(UTC),
            "last_updated_at": datetime.now(UTC),
            "last_sequence": 1,
            "messages": [
                {
                    "role": "assistant",
                    "agent_name": "ActionPlanArchitect",
                    "content": "Please provide your revision feedback.",
                    "event_id": f"msg-{uuid4().hex[:8]}",
                    "sequence": 1,
                    "timestamp": datetime.now(UTC),
                    "event_type": "message.created"
                }
            ]
        }
        
        await coll.insert_one(chat_doc)
        
        # Attach UI tool metadata (NOT completed)
        await pm.attach_ui_tool_metadata(
            chat_id=chat_id,
            enterprise_id=enterprise_id,
            event_id=event_id,
            metadata={
                "ui_tool_id": tool_id,
                "event_id": event_id,
                "display": "inline",
                "ui_tool_completed": False,  # Still in-progress
                "payload": {
                    "title": "Request Revisions",
                    "fields": ["feedback_text"]
                },
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        
        print("📌 Attached UI tool metadata (ui_tool_completed=False)")
        
        # Simulate resume
        resumer = GroupChatResumer()
        messages = await pm.resume_chat(chat_id=chat_id, enterprise_id=enterprise_id)
        
        replayed_events = []
        for idx, msg in enumerate(messages):
            event = resumer._build_text_event(message=msg, index=idx, chat_id=chat_id)
            replayed_events.append(event)
        
        # Find UI tool event
        ui_tool_event = None
        for event in replayed_events:
            if "uiToolEvent" in event:
                ui_tool_event = event
                break
        
        if not ui_tool_event:
            print("   ❌ ERROR: No uiToolEvent found!")
            return False
        
        ui_tool_completed = ui_tool_event.get("ui_tool_completed")
        
        print(f"📌 Verification:")
        print(f"   ui_tool_completed: {ui_tool_completed}")
        
        if ui_tool_completed is False:
            print()
            print("   ✅ CORRECT BEHAVIOR!")
            print("   🎉 Frontend will render: Interactive form (user can still complete)")
            print()
            return True
        else:
            print(f"   ❌ ERROR: Expected ui_tool_completed=False, got {ui_tool_completed}")
            return False
        
    except Exception as e:
        print(f"\n❌ TEST EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await cleanup_test_data(chat_id, enterprise_id)


async def main():
    """Run all tests."""
    print("\n" + "🧪 " * 40)
    print("INLINE COMPONENT PERSISTENCE TEST SUITE")
    print("🧪 " * 40)
    
    results = []
    
    # Test 1: Completed inline component
    result1 = await test_inline_component_persistence()
    results.append(("Completed inline component persistence", result1))
    
    # Test 2: In-progress inline component
    result2 = await test_inline_component_in_progress()
    results.append(("In-progress inline component persistence", result2))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80 + "\n")
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"   {status}  {test_name}")
    
    print()
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("🎉 ALL TESTS PASSED! 🎉")
        print()
        print("✅ Inline component persistence is working correctly!")
        print("✅ Ready for integration testing with real workflows!")
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("Review the errors above and fix the issues.")
    
    print()
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
