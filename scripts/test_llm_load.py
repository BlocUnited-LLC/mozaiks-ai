"""
Test the LLM config loading logic directly
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.workflow.llm_config import _load_raw_config_list, clear_llm_caches

async def test_load():
    """Test loading config from DB"""
    # Clear any cache
    clear_llm_caches(raw=True, built=True)
    
    # Force reload
    config_list = await _load_raw_config_list(force=True)
    
    print("\n" + "=" * 80)
    print("LOADED CONFIG LIST")
    print("=" * 80)
    print(f"Count: {len(config_list)}")
    
    for i, entry in enumerate(config_list):
        print(f"\n[{i}] Model: {entry.get('model')}")
        print(f"    Has API Key: {'yes' if entry.get('api_key') else 'no'}")
        print(f"    Price: {entry.get('price', 'not set')}")

if __name__ == "__main__":
    asyncio.run(test_load())
