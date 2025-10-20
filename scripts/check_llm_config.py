"""
Diagnostic script to check LLMConfig collection in MongoDB
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def check_llm_config():
    """Check what's in the LLMConfig collection"""
    from core.core_config import get_mongo_client
    
    try:
        client = get_mongo_client()
        db = client.autogen_ai_agents
        
        print("=" * 80)
        print("CHECKING LLMConfig COLLECTION")
        print("=" * 80)
        
        # Get the document
        doc = await db.LLMConfig.find_one()
        
        if not doc:
            print("❌ No document found in LLMConfig collection")
            return
        
        print("✅ Found LLMConfig document:")
        print("-" * 80)
        
        # Print the document structure (redacting sensitive fields)
        def redact_secrets(d, indent=0):
            """Recursively print dict with redacted secrets"""
            prefix = "  " * indent
            if isinstance(d, dict):
                for k, v in d.items():
                    if any(s in k.lower() for s in ['api_key', 'apikey', 'secret', 'password', 'token']):
                        if isinstance(v, str) and len(v) > 8:
                            print(f"{prefix}{k}: {v[:4]}***REDACTED***{v[-4:]}")
                        else:
                            print(f"{prefix}{k}: ***REDACTED***")
                    elif isinstance(v, dict):
                        print(f"{prefix}{k}:")
                        redact_secrets(v, indent + 1)
                    elif isinstance(v, list):
                        print(f"{prefix}{k}: [{len(v)} items]")
                        for i, item in enumerate(v):
                            print(f"{prefix}  [{i}]:")
                            if isinstance(item, dict):
                                redact_secrets(item, indent + 2)
                            else:
                                print(f"{prefix}    {item}")
                    else:
                        print(f"{prefix}{k}: {v}")
            else:
                print(f"{prefix}{d}")
        
        redact_secrets(doc)
        
        print("\n" + "=" * 80)
        print("KEY FINDINGS:")
        print("=" * 80)
        
        # Check for model field
        model = doc.get('model') or doc.get('Model') or doc.get('name')
        print(f"Top-level model field: {model}")
        
        # Check for providers array
        providers = doc.get('providers') or doc.get('models')
        if providers:
            print(f"Providers field: Found ({len(providers) if isinstance(providers, list) else 'single object'})")
            if isinstance(providers, list):
                for i, p in enumerate(providers):
                    pmodel = p.get('model') or p.get('Model') or p.get('name')
                    print(f"  Provider[{i}] model: {pmodel}")
        else:
            print("Providers field: Not found")
        
        print("\n" + "=" * 80)
        print("EXPECTED STRUCTURE:")
        print("=" * 80)
        print("The code expects one of these structures:")
        print("1. { model: 'gpt-4.1-nano', api_key: '...', price: [...] }")
        print("2. { providers: [{ model: 'gpt-4.1-nano', ... }] }")
        print("3. { models: [{ model: 'gpt-4.1-nano', ... }] }")
        
    except Exception as e:
        print(f"❌ Error checking LLMConfig: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_llm_config())
