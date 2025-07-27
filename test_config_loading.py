#!/usr/bin/env python3

from core.transport.ag2_iostream import _load_config_list_sync

try:
    config = _load_config_list_sync()
    print(f"✅ Config loaded successfully: {len(config)} models")
    if config:
        print(f"   Model: {config[0].get('model', 'unknown')}")
        api_key = config[0].get('api_key', '')
        print(f"   API Key: {'***' if api_key and api_key != 'mock_key' else 'missing/mock'}")
    print("🎯 Production config loading is working!")
except Exception as e:
    print(f"❌ Error testing config loader: {e}")
    import traceback
    traceback.print_exc()
