# ==============================================================================
# FILE: config.py
# DESCRIPTION: Configuration for Azure Key Vault, MongoDB, LLMs, and Tokens API
# NOTES: Avoid module-level cloud calls; build credentials lazily and prefer
#        environment variables to keep local/dev robust.
# ==============================================================================
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from logs.logging_config import get_core_logger

# Azure SDK imports are kept, but we won't construct credentials at import time
from azure.identity import DefaultAzureCredential
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
logger = get_core_logger("core_config")

# -----------------------------
# Azure Key Vault utilities (lazy, optional)
# -----------------------------
def _get_kv_uri() -> Optional[str]:
    name = os.getenv("AZURE_KEY_VAULT_NAME")
    if name:
        return f"https://{name.strip()}.vault.azure.net/"
    return None

def _build_secret_client() -> Optional[Any]:
    """Create a SecretClient lazily if Key Vault is configured; otherwise return None.

    Note: We import SecretClient inside the function to avoid module import failures
    when azure-keyvault-secrets isn't installed in non-KV environments.
    """
    kv_uri = _get_kv_uri()
    if not kv_uri:
        return None
    try:
        from azure.keyvault.secrets import SecretClient  # type: ignore
    except Exception:
        return None
    try:
        cred = DefaultAzureCredential()
        return SecretClient(vault_url=kv_uri, credential=cred)
    except Exception:
        return None


def get_secret(name: str) -> str:
    """Get a secret value from environment or Key Vault.

    Order:
    1) Environment variable by exact uppercased name (e.g., OpenAIApiKey -> OPENAIAPIKEY)
    2) Common env aliases for well-known secrets (e.g., MongoURI -> MONGO_URI | MONGODB_URI | MONGO_URL)
    3) Azure Key Vault secret by the provided name, if KV is configured
    """
    # 1) Direct env by uppercased name
    env_key = name.upper()
    env_val = os.getenv(env_key)
    if env_val:
        return env_val

    # 2) Common aliases for Mongo
    if name in ("MongoURI", "MONGO_URI", "MONGODB_URI", "MONGO_URL"):
        for alias in ("MONGO_URI", "MONGODB_URI", "MONGO_URL"):
            val = os.getenv(alias)
            if val:
                return val

    # 3) Azure Key Vault fallback
    client = _build_secret_client()
    if client is not None:
        try:
            secret = client.get_secret(name)
            if secret and getattr(secret, "value", None):
                return secret.value  # type: ignore[attr-defined]
        except Exception:
            pass

    raise ValueError(f"Secret '{name}' not found in environment or Key Vault")

# -----------------------------
# MongoDB Connection
# -----------------------------
def get_mongo_client() -> AsyncIOMotorClient:
    """Get MongoDB client using MONGO_URI env or Key Vault secret 'MongoURI'.

    Avoids defaulting to localhost, to prevent accidental local fallbacks.
    """
    conn_str = os.getenv("MONGO_URI")
    if not conn_str:
        # Fall back to KV only if env is missing
        conn_str = get_secret("MongoURI")
    if not conn_str:
        raise ValueError("MONGO_URI is not configured")
    return AsyncIOMotorClient(conn_str)


# MongoDB Collections are obtained via PersistenceManager to avoid early initialization

# ==============================================================================
# FREE TRIAL CONFIGURATION
# ==============================================================================
# NOTE: Subscription/token gating hook points (no-op for now):
# - Start gate (cheap, before allocating resources):
#   Implement checks in shared_app.start_chat to enforce plan/limits before
#   generating chat_id. Examples:
#     * Verify MozaiksDB.Wallets (VE schema: EnterpriseId, UserId, Balance)
#       has sufficient Balance or trial status allows start
#     * Enforce per-plan concurrency and daily session caps
# - Run-time gate (accurate usage control):
#   Implement hard/soft enforcement in AG2PersistenceManager.debit_tokens.
#   When Balance < required delta:
#     * Hard stop: raise INSUFFICIENT_TOKENS to end the session
#     * Soft degrade: switch to cheaper model or reduce max_turns
# - Warnings/UX nudges:
#   Use get_free_trial_config().get("warning_threshold") to emit low-balance
#   warnings via logs or tool-driven UI events without blocking execution.
# - Suggested feature flags (env):
#     ENFORCE_TOKENS=true|false
#     ENFORCE_RATE_LIMITS=true|false
#     ALLOW_FREE_TRIAL=true|false
#     DEGRADE_ON_INSUFFICIENT=true|false
#   These can toggle checks in the two hook points above without redesign.
# - Data model reminder:
#   Wallets collection uses VE uppercase schema by default:
#     { EnterpriseId, UserId, Balance, Transactions, CreatedAt, UpdatedAt }
#   ChatSessions should not mirror balances; only track usage aggregates.
# ------------------------------------------------------------------------------
# Tokens API Base URL
TOKENS_API_URL = os.getenv("TOKENS_API_URL", "http://localhost:5000")
from core.workflow.ui_tools import use_ui_tool

def get_free_trial_config() -> Dict[str, Any]:
    """Get free trial configuration from environment variables"""
    return {
        "enabled": os.getenv("FREE_TRIAL_ENABLED", "true").lower() == "true"
    }

# -----------------------------------------------------------------------------
# Low balance (token) prompt helper (emits standardized UI tool event)
# -----------------------------------------------------------------------------
async def prompt_low_balance(chat_id: str, workflow_name: str, needed_tokens: int, current_balance: int) -> dict:
    """Display a low-balance UI prompt and return user response (single-call helper)."""
    return await use_ui_tool(
        tool_id="token_top_up_prompt",
        payload={
            "needed_tokens": int(needed_tokens),
            "current_balance": int(current_balance),
            "message": "Insufficient balance. Please add funds to continue.",
            "interaction_type": "top_up",
        },
        chat_id=chat_id,
        workflow_name=workflow_name,
        display="inline",
    )

__all__ = [
    "prompt_low_balance",
    "get_secret",
    "get_mongo_client",
]
