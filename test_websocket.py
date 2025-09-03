#!/usr/bin/env python3
"""
Test WebSocket connection to trigger LLM configuration loading.
"""
import asyncio
import websockets
import json

async def test_workflow_connection():
    uri = "ws://localhost:8000/ws/Generator/test_enterprise/bf6a1d20-0754-4582-ad50-d82d894c9655/test_user"
    
    try:
        print(f"Connecting to: {uri}")
        async with websockets.connect(uri) as websocket:
            print("Connected successfully!")
            
            # Send a test message
            test_message = {
                "type": "user_message", 
                "content": "Hello, can you help me generate some code?"
            }
            await websocket.send(json.dumps(test_message))
            print(f"Sent message: {test_message}")
            
            # Wait for response
            print("Waiting for response...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                print(f"Received: {response}")
            except asyncio.TimeoutError:
                print("Timeout waiting for response")
                
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_workflow_connection())