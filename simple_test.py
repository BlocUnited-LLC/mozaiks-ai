#!/usr/bin/env python3
"""Simple test to debug the issue."""
import sys
print("Python executable:", sys.executable)
print("Python version:", sys.version)
print("Current working directory:", __import__('os').getcwd())
print("Script location:", __file__)

# Test basic imports
try:
    import asyncio
    print("✅ asyncio imported successfully")
except Exception as e:
    print(f"❌ asyncio import failed: {e}")

try:
    from pathlib import Path
    print("✅ pathlib imported successfully")
except Exception as e:
    print(f"❌ pathlib import failed: {e}")

# Test project imports
try:
    from core.core_config import get_mongo_client
    print("✅ core.core_config imported successfully")
except Exception as e:
    print(f"❌ core.core_config import failed: {e}")

print("Test completed!")
