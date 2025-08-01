#!/usr/bin/env python3
"""
Test script to verify all agents are loading correctly with their system messages
"""

import asyncio
from core.workflow.agents import define_agents

async def test_agents():
    """Test that all agents load correctly with their system messages"""
    print("Testing agent loading for Generator workflow...")
    
    agents = await define_agents('Generator')
    
    print(f"\nTotal agents count: {len(agents)}")
    print("\nAll agents:")
    
    for i, (agent_name, agent) in enumerate(agents.items(), 1):
        print(f"  {i}. {agent_name}")
        print(f"      Name: {agent.name}")
        print(f"      Human Input Mode: {agent.human_input_mode}")
        print(f"      Max Auto Reply: {agent.max_consecutive_auto_reply}")
        
        # Show first 100 characters of system message
        system_msg = agent.system_message or "No system message"
        if len(system_msg) > 100:
            system_msg_preview = system_msg[:100] + "..."
        else:
            system_msg_preview = system_msg
        
        print(f"      System Message: {system_msg_preview}")
        print()

if __name__ == "__main__":
    asyncio.run(test_agents())
