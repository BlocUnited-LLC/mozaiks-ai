# ==============================================================================
# FILE: config.py
# DESCRIPTION: Configuration for Azure Key Vault, MongoDB, LLMs, and Tokens API
# ==============================================================================
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from motor.motor_asyncio import AsyncIOMotorClient
from autogen import OpenAIWrapper
from typing import Optional, Type, Tuple, Dict, Any, List
from pydantic import BaseModel
import logging
import json

load_dotenv()
logger = logging.getLogger(__name__)

# Azure Key Vault Setup
KEY_VAULT_NAME = os.getenv("AZURE_KEY_VAULT_NAME")
if not KEY_VAULT_NAME:
    raise ValueError("AZURE_KEY_VAULT_NAME is required")

KEY_VAULT_URI = f"https://{KEY_VAULT_NAME.strip()}.vault.azure.net/"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=KEY_VAULT_URI, credential=credential)

def get_secret(name: str) -> str:
    """Get secret from Azure Key Vault with environment fallback"""
    try:
        value = secret_client.get_secret(name).value
        if value is None:
            raise ValueError(f"Secret '{name}' not found or has no value")
        return value
    except Exception:
        env = os.getenv(name.upper())
        if env:
            return env
        raise ValueError(f"Secret '{name}' not found in Azure Key Vault or environment")

# MongoDB Connection
def get_mongo_client() -> AsyncIOMotorClient:
    """Get MongoDB client with connection string from secrets"""
    try:
        conn_str = get_secret("MongoURI")
    except:
        conn_str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    return AsyncIOMotorClient(conn_str)

# Tokens API Base URL
TOKENS_API_URL = os.getenv("TOKENS_API_URL", "http://localhost:5000")

async def _load_raw_config_list() -> list[dict]:
    """Load LLM configuration from database with fallback"""
    db = get_mongo_client().autogen_ai_agents
    try:
        doc = await db.LLMConfig.find_one()
        if doc:
            model = doc.get("Model", "gpt-4o-mini")
            price_map = {
                "o3-mini": [0.0011, 0.0044],
                "gpt-4.1-nano": [0.0001, 0.0004],
                "gpt-4o-mini": [0.00015, 0.0006],
            }
            price = price_map.get(model, [0.00015, 0.0006])
        else:
            model = "gpt-4o-mini"
            price = [0.00015, 0.0006]
    except Exception as e:
        logger.warning(f"Failed to load LLM config from DB: {e}")
        model = "gpt-4o-mini"
        price = [0.00015, 0.0006]
    
    api_key = get_secret("OpenAIApiKey")
    return [{"model": model, "api_key": api_key, "price": price}]

async def make_llm_config(
    response_format: Optional[Type[BaseModel]] = None,
    stream: bool = False,
    extra_config: Optional[Dict[str, Any]] = None,
    enable_token_tracking: bool = False
) -> Tuple[OpenAIWrapper, Dict[str, Any]]:
    """Create LLM configuration with optional structured output and streaming"""
    config_list = await _load_raw_config_list()
    
    for cfg in config_list:
        if response_format:
            cfg["response_format"] = response_format
        # Note: AG2 streaming is handled by IOStream, not by config_list stream parameter
        if extra_config:
            cfg.update(extra_config)
        
        # Enable token tracking for individual agents (AG2 requirement)
        # Note: AG2 handles token tracking automatically when OpenAI clients are properly configured
        # We just need to ensure the basic config is clean and valid
    
    for i, cfg in enumerate(config_list, start=1):
        redacted = {**cfg}
        redacted["api_key"] = "***REDACTED***"
        if "response_format" in redacted:
            redacted["response_format"] = cfg["response_format"].__name__
        logger.info(f"[LLM CONFIG #{i}] {redacted}")
    
    client = OpenAIWrapper(config_list=config_list)

    # Build LLM runtime configuration
    llm_config = {
        "timeout": 600,
        "cache_seed": 153,
        "config_list": config_list
    }
    
    # Note: Streaming is handled by AG2's IOStream system, not by llm_config
    if stream:
        logger.info("🎯 AG2 streaming enabled - custom IOStream will handle output")
    else:
        logger.info("🎯 AG2 streaming disabled")
    
    # Add token tracking configuration if enabled
    if enable_token_tracking:
        # Note: AG2 handles individual agent token tracking automatically
        # when agents are created with proper OpenAI clients
        logger.debug("🔧 Token tracking enabled - AG2 will handle individual agent tracking automatically")
    
    logger.info("LLM runtime config initialized successfully.")
    
    return client, llm_config

async def make_structured_config(response_format: Type[BaseModel], extra_config: Optional[Dict[str, Any]] = None, enable_token_tracking: bool = False):
    """Create structured output LLM configuration"""
    return await make_llm_config(response_format=response_format, extra_config=extra_config, enable_token_tracking=enable_token_tracking)

# MongoDB Collections
mongo_client = get_mongo_client()
db1 = mongo_client['MozaiksDB']
enterprises_collection = db1['Enterprises']
db2 = mongo_client['autogen_ai_agents']
concepts_collection = db2['Concepts']
workflows_collection = db2['Workflows']

# ==============================================================================
# FREE TRIAL CONFIGURATION
# ==============================================================================

def get_free_trial_config() -> Dict[str, Any]:
    """Get free trial configuration from environment variables"""
    return {
        "enabled": os.getenv("FREE_TRIAL_ENABLED", "true").lower() == "true",
        "default_tokens": int(os.getenv("FREE_TRIAL_DEFAULT_TOKENS", "1000")),
        "auto_upgrade_prompt": os.getenv("AUTO_UPGRADE_PROMPT_ENABLED", "true").lower() == "true",
        "warning_threshold": int(os.getenv("TRIAL_WARNING_THRESHOLD", "100"))
    }

def get_token_config() -> Dict[str, Any]:
    """Get token configuration including available (paid) tokens"""
    return {
        "available_tokens_default": int(os.getenv("AVAILABLE_TOKENS_DEFAULT", "0")),
        "purchase_minimum": int(os.getenv("AVAILABLE_TOKENS_PURCHASE_MINIMUM", "1000"))
    }

def get_token_pricing() -> Dict[str, str]:
    """Get token pricing configuration - AG2 handles actual costs"""
    return {
        "note": "Token costs are handled by AG2 observability system"
    }

def get_rate_limits() -> Dict[str, str]:
    """Get rate limiting configuration - not implemented yet"""
    return {
        "note": "Rate limiting not implemented yet"
    }