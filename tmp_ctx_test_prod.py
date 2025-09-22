import asyncio, os
from core.workflow.context_variables import _load_context_async

async def run():
    ctx = await _load_context_async('Generator','507f1f77bcf86cd799439011')
    print('PRODUCTION MODE keys:', sorted(ctx.data.keys()))

asyncio.run(run())
