# ==============================================================================
# FILE: tests/test_session_manager.py
# DESCRIPTION: Unit tests for session_manager functions
# ==============================================================================

import asyncio
import pytest
import time

pytestmark = pytest.mark.asyncio


class FakeColl:
    """Mock MongoDB collection for testing."""
    def __init__(self):
        self.replaced = []
        self.updated = []
        self.found = []

    async def replace_one(self, query, doc, upsert=False):
        self.replaced.append((query, doc, upsert))
        return {"acknowledged": True}

    async def update_one(self, query, update):
        self.updated.append((query, update))
        return {"acknowledged": True}

    async def find_one(self, query):
        self.found.append(query)
        # Return a fake document for get operations
        if query.get("_id", "").startswith("chat_"):
            return {
                "_id": query["_id"],
                "enterprise_id": query.get("enterprise_id"),
                "status": "IN_PROGRESS",
                "workflow_name": "TestWorkflow"
            }
        elif query.get("_id", "").startswith("artifact_"):
            return {
                "_id": query["_id"],
                "enterprise_id": query.get("enterprise_id"),
                "artifact_type": "ActionPlan",
                "state": {"test": "data"}
            }
        return None


class FakePM:
    """Mock AG2PersistenceManager for testing."""
    def __init__(self, coll_map):
        self._coll_map = coll_map

    async def _coll(self, name: str = "default"):
        c = self._coll_map.get(name)
        if not c:
            c = FakeColl()
            self._coll_map[name] = c
        return c


async def test_session_manager_create_workflow_session(monkeypatch):
    """Test create_workflow_session creates correct document."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    sess = await session_manager.create_workflow_session("ent-abc", "user-1", "Generator")
    
    assert sess["enterprise_id"] == "ent-abc"
    assert sess["user_id"] == "user-1"
    assert sess["workflow_name"] == "Generator"
    assert sess["status"] == "IN_PROGRESS"
    assert sess["_id"].startswith("chat_")
    assert sess["artifact_instance_id"] is None

    wf_coll = coll_map.get("WorkflowSessions")
    assert wf_coll is not None
    assert len(wf_coll.replaced) == 1


async def test_session_manager_multiple_in_progress_sessions(monkeypatch):
    """Test that multiple sessions can exist in IN_PROGRESS state simultaneously."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    # Create first session
    sess1 = await session_manager.create_workflow_session("ent-abc", "user-1", "Generator")
    assert sess1["status"] == "IN_PROGRESS"
    
    # Create second session (both should be IN_PROGRESS simultaneously)
    sess2 = await session_manager.create_workflow_session("ent-abc", "user-1", "Build")
    assert sess2["status"] == "IN_PROGRESS"
    
    # Verify both sessions were created
    wf_coll = coll_map.get("WorkflowSessions")
    assert len(wf_coll.replaced) == 2
    
    # Both should have different chat_ids
    assert sess1["_id"] != sess2["_id"]
    
    # Both should be IN_PROGRESS (no pausing needed)
    assert sess1["status"] == "IN_PROGRESS"
    assert sess2["status"] == "IN_PROGRESS"


async def test_session_manager_complete_workflow_session(monkeypatch):
    """Test complete_workflow_session sets status to COMPLETED."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    sess = await session_manager.create_workflow_session("ent-abc", "user-1", "Generator")
    chat_id = sess["_id"]

    await session_manager.complete_workflow_session(chat_id, "ent-abc")
    
    wf_coll = coll_map.get("WorkflowSessions")
    query, update = wf_coll.updated[-1]
    assert query["_id"] == chat_id
    assert update["$set"]["status"] == "COMPLETED"


async def test_session_manager_create_artifact_instance(monkeypatch):
    """Test create_artifact_instance creates correct document."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    art = await session_manager.create_artifact_instance(
        "ent-abc",
        "Generator",
        "ActionPlan",
        {"foo": "bar"}
    )
    
    assert art["enterprise_id"] == "ent-abc"
    assert art["workflow_name"] == "Generator"
    assert art["artifact_type"] == "ActionPlan"
    assert art["state"] == {"foo": "bar"}
    assert art["_id"].startswith("artifact_")

    art_coll = coll_map.get("ArtifactInstances")
    assert art_coll is not None
    assert len(art_coll.replaced) == 1


async def test_session_manager_attach_artifact_to_session(monkeypatch):
    """Test attach_artifact_to_session updates both collections."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    sess = await session_manager.create_workflow_session("ent-abc", "user-1", "Generator")
    art = await session_manager.create_artifact_instance("ent-abc", "Generator", "ActionPlan")

    await session_manager.attach_artifact_to_session(sess["_id"], art["_id"], "ent-abc")

    sess_coll = coll_map.get("WorkflowSessions")
    art_coll = coll_map.get("ArtifactInstances")
    
    # Both should have update records
    assert len(sess_coll.updated) >= 1
    assert len(art_coll.updated) >= 1
    
    # Verify session update
    sess_query, sess_update = sess_coll.updated[-1]
    assert sess_query["_id"] == sess["_id"]
    assert sess_update["$set"]["artifact_instance_id"] == art["_id"]
    
    # Verify artifact update
    art_query, art_update = art_coll.updated[-1]
    assert art_query["_id"] == art["_id"]
    assert art_update["$set"]["last_active_chat_id"] == sess["_id"]


async def test_session_manager_update_artifact_state(monkeypatch):
    """Test update_artifact_state applies partial updates."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    art = await session_manager.create_artifact_instance("ent-abc", "Generator", "ActionPlan")

    await session_manager.update_artifact_state(
        art["_id"],
        "ent-abc",
        {"player_name": "John", "score": 100}
    )

    art_coll = coll_map.get("ArtifactInstances")
    query, update = art_coll.updated[-1]
    
    assert query["_id"] == art["_id"]
    assert "$set" in update
    assert update["$set"]["state.player_name"] == "John"
    assert update["$set"]["state.score"] == 100


async def test_session_manager_get_functions(monkeypatch):
    """Test get_artifact_instance and get_workflow_session retrieval."""
    from core.workflow import session_manager
    coll_map = {}

    monkeypatch.setattr(
        session_manager,
        "AG2PersistenceManager",
        lambda: FakePM(coll_map)
    )

    # Get workflow session
    sess_doc = await session_manager.get_workflow_session("chat_test123", "ent-abc")
    assert sess_doc is not None
    assert sess_doc["_id"] == "chat_test123"
    assert sess_doc["status"] == "IN_PROGRESS"

    # Get artifact instance
    art_doc = await session_manager.get_artifact_instance("artifact_test456", "ent-abc")
    assert art_doc is not None
    assert art_doc["_id"] == "artifact_test456"
    assert art_doc["artifact_type"] == "ActionPlan"
