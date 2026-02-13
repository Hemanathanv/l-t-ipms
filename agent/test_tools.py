"""
Test script for SRA Tools
Run this file to test the tools individually
"""

import asyncio
import sys
import os

# Add parent directory to path so our imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_prisma, close_prisma
from agent.tools import *


async def test_sra_status_pei():
    """Test the sra_status_pei tool"""
    print("\n" + "="*60)
    print("Testing sra_status_pei")
    print("="*60)
    
    # Test: With project_id and date
    print("\n--- Test: With project_id and date ---")
    result = await sra_status_pei.ainvoke({
        "project_id": "PRJ_1076",
        "start_date": "2024-12-25"
    })
    print(result)


async def test_sra_drill_delay():
    """Test the sra_drill_delay tool"""
    print("\n" + "="*60)
    print("Testing sra_drill_delay")
    print("="*60)
    
    # Test: With project_id and date range
    print("\n--- Test: With project_id and date range ---")
    result = await sra_drill_delay.ainvoke({
        "project_id": "PRJ_001",
        "start_date": "2025-07-01",
        "end_date": "2025-07-31"
    })
    print(result)


async def test_sra_recovery_advise():
    """Test the sra_recovery_advise tool"""
    print("\n" + "="*60)
    print("Testing sra_recovery_advise")
    print("="*60)
    
    # Test: Get recovery advice for a project
    print("\n--- Test: Get recovery advice ---")
    result = await sra_recovery_advise.ainvoke({
        "project_id": "PRJ_001",
        "resource_type": "labor"
    })
    print(result)


async def test_sra_simulate():
    """Test the sra_simulate tool"""
    print("\n" + "="*60)
    print("Testing sra_simulate")
    print("="*60)
    
    # Test: Simulate adding shuttering gangs
    print("\n--- Test: Simulate adding 2 shuttering gangs ---")
    result = await sra_simulate.ainvoke({
        "project_id": "PRJ_001",
        "resource_type": "shuttering_gang",
        "value_amount": 2,
        "date_range": "2025-07-15 to 2025-07-20"
    })
    print(result)


async def test_sra_create_action():
    """Test the sra_create_action tool"""
    print("\n" + "="*60)
    print("Testing sra_create_action")
    print("="*60)
    
    # Test: Create an action item
    print("\n--- Test: Create action item ---")
    result = await sra_create_action.ainvoke({
        "project_id": "PRJ_001",
        "user_id": "site_planner_01",
        "action_choice": "Approve Option 1 - Add resources"
    })
    print(result)


async def test_sra_explain_formula():
    """Test the sra_explain_formula tool"""
    print("\n" + "="*60)
    print("Testing sra_explain_formula")
    print("="*60)
    
    # Test: Explain SPI formula
    print("\n--- Test: Explain SPI formula ---")
    result = await sra_explain_formula.ainvoke({
        "project_id": "PRJ_001",
        "metric": "SPI"
    })
    print(result)


async def main():
    """Main test runner"""
    print("🚀 Starting SRA Tools Test Suite")
    print("="*60)
    
    try:
        # Initialize database connection
        print("\n📦 Connecting to database...")
        prisma = await get_prisma()
        print("✅ PostgreSQL (Prisma) connected")
        
        # Run tests for all 6 tools
        await test_sra_status_pei()
        # await test_sra_drill_delay()
        # await test_sra_recovery_advise()
        # await test_sra_simulate()
        # await test_sra_create_action()
        # await test_sra_explain_formula()
        
        print("\n" + "="*60)
        print("✅ All tests completed!")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error during tests: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        await close_prisma()
        print("\n📦 Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
