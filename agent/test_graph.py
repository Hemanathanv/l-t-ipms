"""
Test script for LangGraph Agent with SRA Tools
Run this file to test the agent conversation flow with all tools
"""

import asyncio
import sys
import os

# Fix for Windows: Psycopg requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path so our imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_prisma, close_prisma
from agent.graph import create_agent, create_checkpointer, run_conversation


# Test scenarios for each tool
TEST_SCENARIOS = [
    {
        "name": "1. PEI Status Query",
        "messages": [
            "What is the current PEI for project PRJ_001 on 2025-07-01?"
        ],
        "expected_tool": "sra_status_pei"
    },
    {
        "name": "2. Delay Analysis",
        "messages": [
            "Why is project PRJ_001 delayed? Check from 2025-07-01 to 2025-07-31"
        ],
        "expected_tool": "sra_drill_delay"
    },
    {
        "name": "3. Recovery Advice",
        "messages": [
            "How do we recover project PRJ_001?"
        ],
        "expected_tool": "sra_recovery_advise"
    },
    {
        "name": "4. Simulation",
        "messages": [
            "What if I add 2 shuttering gangs to PRJ_001?"
        ],
        "expected_tool": "sra_simulate"
    },
    {
        "name": "5. Create Action",
        "messages": [
            "Log option 1 for project PRJ_001 and assign to site_planner"
        ],
        "expected_tool": "sra_create_action"
    },
    {
        "name": "6. Explain Formula",
        "messages": [
            "How did you compute SPI for PRJ_001?"
        ],
        "expected_tool": "sra_explain_formula"
    },
    {
        "name": "7. Out of Scope (Should NOT hallucinate)",
        "messages": [
            "What's the weather today?"
        ],
        "expected_tool": None
    }
]


async def run_test_scenario(agent, scenario: dict, thread_id: str):
    """Run a single test scenario"""
    print(f"\n{'='*70}")
    print(f"🧪 TEST: {scenario['name']}")
    print(f"   Expected Tool: {scenario['expected_tool'] or 'None (out of scope)'}")
    print(f"{'='*70}")
    
    for msg in scenario["messages"]:
        print(f"\n👤 USER: {msg}")
        print("-" * 50)
        
        try:
            response = await run_conversation(
                agent=agent,
                message=msg,
                thread_id=thread_id
            )
            print(f"\n🤖 ASSISTANT:\n{response}")
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()


async def run_interactive_mode(agent):
    """Run interactive conversation mode"""
    print("\n" + "="*70)
    print("🎯 INTERACTIVE MODE")
    print("Type your messages to test the agent. Type 'quit' to exit.")
    print("="*70)
    
    thread_id = "interactive_test_session"
    
    while True:
        try:
            user_input = input("\n👤 YOU: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Exiting interactive mode...")
                break
            
            if not user_input:
                continue
            
            print("-" * 50)
            response = await run_conversation(
                agent=agent,
                message=user_input,
                thread_id=thread_id
            )
            print(f"\n🤖 ASSISTANT:\n{response}")
            
        except KeyboardInterrupt:
            print("\n👋 Interrupted. Exiting...")
            break
        except Exception as e:
            print(f"\n❌ ERROR: {e}")


async def main():
    """Main test runner"""
    print("🚀 Starting LangGraph Agent Test Suite")
    print("="*70)
    
    checkpointer_ctx = None
    
    try:
        # Initialize database connection
        print("\n📦 Connecting to database...")
        prisma = await get_prisma()
        print("✅ Database connected")
        
        # Create checkpointer and agent
        print("📦 Creating checkpointer...")
        checkpointer_ctx = create_checkpointer()
        checkpointer = await checkpointer_ctx.__aenter__()
        await checkpointer.setup()
        print("✅ Checkpointer ready")
        
        print("🤖 Creating agent...")
        agent = await create_agent(checkpointer=checkpointer)
        print("✅ Agent ready")
        
        # Ask user for mode
        print("\n" + "="*70)
        print("Choose test mode:")
        print("  1. Run all automated tests")
        print("  2. Interactive conversation mode")
        print("  3. Run both")
        print("="*70)
        
        choice = input("Enter choice (1/2/3): ").strip()
        
        if choice in ['1', '3']:
            # Run automated tests
            print("\n🔬 Running Automated Tests...")
            for i, scenario in enumerate(TEST_SCENARIOS):
                thread_id = f"test_scenario_{i}_{scenario['expected_tool']}"
                await run_test_scenario(agent, scenario, thread_id)
            
            print("\n" + "="*70)
            print("✅ All automated tests completed!")
            print("="*70)
        
        if choice in ['2', '3']:
            await run_interactive_mode(agent)
        
        if choice not in ['1', '2', '3']:
            print("Invalid choice. Running all automated tests by default...")
            for i, scenario in enumerate(TEST_SCENARIOS):
                thread_id = f"test_scenario_{i}_{scenario['expected_tool']}"
                await run_test_scenario(agent, scenario, thread_id)
        
    except Exception as e:
        print(f"\n❌ Error during tests: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        if checkpointer_ctx:
            await checkpointer_ctx.__aexit__(None, None, None)
            print("\n📦 Checkpointer closed")
        await close_prisma()
        print("📦 Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
