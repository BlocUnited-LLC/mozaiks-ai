import pytest
from uuid import uuid4

from core.data.persistence.persistence_manager import AG2PersistenceManager
from core.core_config import get_mongo_client


async def _cleanup_general_docs(general_chat_id: str, enterprise_id: str, user_id: str) -> None:
    client = get_mongo_client()
    db = client["MozaiksAI"]
    await db["GeneralChatSessions"].delete_one({"_id": general_chat_id})
    await db["GeneralChatCounters"].delete_one({"enterprise_id": enterprise_id, "user_id": user_id})


@pytest.mark.asyncio
async def test_general_chat_session_creation_and_persistence():
    pm = AG2PersistenceManager()
    enterprise_id = f"test-ent-{uuid4().hex[:8]}"
    user_id = f"user-{uuid4().hex[:8]}"

    session_info = await pm.create_general_chat_session(enterprise_id=enterprise_id, user_id=user_id)
    general_chat_id = session_info["chat_id"]

    assert general_chat_id.startswith("generalchat-"), "General chat id should use the new prefix"
    assert session_info["label"].startswith("General Chat #")

    await pm.append_general_message(
        general_chat_id=general_chat_id,
        enterprise_id=enterprise_id,
        role="user",
        content="Hello Ask Mozaiks",
        user_id=user_id,
        metadata={"source": "general_agent"},
    )

    coll = await pm._general_coll()  # type: ignore[attr-defined]
    stored = await coll.find_one({"_id": general_chat_id})
    assert stored is not None
    assert stored.get("last_sequence") == 1
    assert stored.get("messages", [])
    assert stored["messages"][0]["metadata"]["source"] == "general_agent"

    await _cleanup_general_docs(general_chat_id, enterprise_id, user_id)


@pytest.mark.asyncio
async def test_general_chat_listing_and_transcript_filters():
    pm = AG2PersistenceManager()
    enterprise_id = f"test-ent-{uuid4().hex[:8]}"
    user_id = f"user-{uuid4().hex[:8]}"

    session_info = await pm.create_general_chat_session(enterprise_id=enterprise_id, user_id=user_id)
    general_chat_id = session_info["chat_id"]

    await pm.append_general_message(
        general_chat_id=general_chat_id,
        enterprise_id=enterprise_id,
        role="user",
        content="Hello",
        user_id=user_id,
    )
    await pm.append_general_message(
        general_chat_id=general_chat_id,
        enterprise_id=enterprise_id,
        role="assistant",
        content="Hi there",
        user_id=user_id,
    )

    sessions = await pm.list_general_chats(enterprise_id=enterprise_id, user_id=user_id)
    assert sessions, "Expected at least one general session"
    assert sessions[0]["chat_id"] == general_chat_id
    assert sessions[0]["last_sequence"] == 2

    transcript_full = await pm.fetch_general_chat_transcript(
        general_chat_id=general_chat_id,
        enterprise_id=enterprise_id,
    )
    assert transcript_full is not None
    assert len(transcript_full["messages"]) == 2

    transcript_filtered = await pm.fetch_general_chat_transcript(
        general_chat_id=general_chat_id,
        enterprise_id=enterprise_id,
        after_sequence=1,
    )
    assert transcript_filtered is not None
    assert len(transcript_filtered["messages"]) == 1
    assert transcript_filtered["messages"][0]["role"] == "assistant"

    await _cleanup_general_docs(general_chat_id, enterprise_id, user_id)
