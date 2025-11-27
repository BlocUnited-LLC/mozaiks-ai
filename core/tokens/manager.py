import os
from typing import Optional, Dict, Any
from datetime import datetime, UTC
from core.core_config import MONETIZATION_ENABLED, FREE_TRIAL_ENABLED, TOKEN_WARNING_THRESHOLD
from core.events.unified_event_dispatcher import get_event_dispatcher
from logs.logging_config import get_workflow_logger

logger = get_workflow_logger("token_manager")

class InsufficientTokensError(Exception):
    pass

class TokenManager:
    @staticmethod
    async def ensure_can_start_chat(
        user_id: str, 
        enterprise_id: str, 
        workflow_name: str, 
        persistence_manager: Any
    ) -> Dict[str, Any]:
        if not MONETIZATION_ENABLED:
            return {"allowed": True}
            
        if FREE_TRIAL_ENABLED:
            return {"allowed": True, "free_trial": True}
            
        balance = await persistence_manager.get_wallet_balance(user_id, enterprise_id)
        if balance <= 0:
            raise InsufficientTokensError("Insufficient tokens to start chat")
            
        return {"allowed": True, "balance": balance}

    @staticmethod
    async def handle_turn_usage(
        chat_id: str,
        enterprise_id: str,
        user_id: str,
        workflow_name: str,
        usage_snapshot: Dict[str, int], # prompt_tokens, completion_tokens, total_tokens
        persistence_manager: Any
    ) -> None:
        if not MONETIZATION_ENABLED:
            return

        if FREE_TRIAL_ENABLED:
            return

        total_tokens = usage_snapshot.get("total_tokens", 0)
        if total_tokens <= 0:
            return

        # Debit tokens
        new_balance = await persistence_manager.debit_tokens(
            user_id, 
            enterprise_id, 
            total_tokens, 
            reason="realtime_usage", 
            strict=False,
            meta={"chat_id": chat_id, "workflow": workflow_name}
        )

        dispatcher = get_event_dispatcher()

        if new_balance is None:
            # Exhausted
            logger.warning(f"Tokens exhausted for chat {chat_id}")
            # Pause chat
            await TokenManager._pause_chat(chat_id, enterprise_id, "insufficient_tokens", persistence_manager)
            
            await dispatcher.emit("runtime.token.exhausted", {
                "chat_id": chat_id,
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "workflow_name": workflow_name
            })
        else:
            # Check warning threshold if needed
            pass

    @staticmethod
    async def handle_auto_reply_limit(
        chat_id: str,
        enterprise_id: str,
        workflow_name: str,
        limit: int,
        persistence_manager: Any
    ) -> None:
        logger.info(f"Auto-reply limit {limit} reached for chat {chat_id}")
        
        # Update WorkflowStats
        try:
            stats_coll = await persistence_manager._workflow_stats_coll()
            summary_id = f"mon_{enterprise_id}_{workflow_name}"
            await stats_coll.update_one(
                {"_id": summary_id},
                {"$inc": {"auto_reply_hits": 1}, "$set": {"auto_reply_limit": limit}},
                upsert=True
            )
        except Exception as e:
            logger.warning(f"Failed to update WorkflowStats for auto_reply_limit: {e}")

        # Emit event
        dispatcher = get_event_dispatcher()
        await dispatcher.emit("runtime.token.auto_reply_limit", {
            "chat_id": chat_id,
            "enterprise_id": enterprise_id,
            "workflow_name": workflow_name,
            "limit": limit
        })
        
        await TokenManager._pause_chat(chat_id, enterprise_id, "auto_reply_limit", persistence_manager)

    @staticmethod
    async def resume_after_topup(
        chat_id: str,
        enterprise_id: str,
        persistence_manager: Any
    ) -> None:
        # Clear pause
        coll = await persistence_manager._coll()
        await coll.update_one(
            {"_id": chat_id, "enterprise_id": enterprise_id},
            {"$set": {"paused": False, "pause_reason": None, "paused_at": None}}
        )
        
        dispatcher = get_event_dispatcher()
        await dispatcher.emit("runtime.token.resumed", {
            "chat_id": chat_id,
            "enterprise_id": enterprise_id
        })

    @staticmethod
    async def _pause_chat(chat_id: str, enterprise_id: str, reason: str, persistence_manager: Any):
        coll = await persistence_manager._coll()
        await coll.update_one(
            {"_id": chat_id, "enterprise_id": enterprise_id},
            {"$set": {
                "paused": True, 
                "pause_reason": reason, 
                "paused_at": datetime.now(UTC)
            }}
        )
