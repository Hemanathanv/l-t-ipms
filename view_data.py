"""
Utility script to view stored conversations
Shows data from PostgreSQL (Prisma tables) and Redis cache
"""

import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

from prisma import Prisma
import redis.asyncio as redis
from config import settings


async def view_prisma_data():
    """View conversations and messages from Prisma tables"""
    print("\n" + "="*60)
    print("📊 PRISMA DATABASE (conversations & messages tables)")
    print("="*60)
    
    prisma = Prisma()
    await prisma.connect()
    
    # Get all conversations
    conversations = await prisma.conversation.find_many(
        include={"messages": True},
        order={"createdAt": "desc"}
    )
    
    if not conversations:
        print("❌ No conversations found in Prisma database")
    else:
        for conv in conversations:
            print(f"\n🗨️ Conversation: {conv.threadId}")
            print(f"   Title: {conv.title}")
            print(f"   Created: {conv.createdAt}")
            print(f"   Messages ({len(conv.messages)}):")
            for msg in conv.messages:
                role_icon = "👤" if msg.role == "user" else "🤖"
                content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                print(f"     {role_icon} [{msg.role}]: {content_preview}")
    
    await prisma.disconnect()


async def view_redis_data():
    """View cached conversations from Redis"""
    print("\n" + "="*60)
    print("🔴 REDIS CACHE (conversation:*:messages keys)")
    print("="*60)
    
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    try:
        # Find all conversation keys
        keys = await client.keys("conversation:*:messages")
        
        if not keys:
            print("❌ No cached conversations found in Redis")
        else:
            for key in keys:
                thread_id = key.split(":")[1]
                data = await client.get(key)
                ttl = await client.ttl(key)
                
                print(f"\n🗨️ Thread: {thread_id}")
                print(f"   TTL: {ttl} seconds")
                
                if data:
                    messages = json.loads(data)
                    print(f"   Cached messages ({len(messages)}):")
                    for msg in messages:
                        role_icon = "👤" if msg.get("role") == "user" else "🤖"
                        content = msg.get("content", "")
                        content_preview = content[:100] + "..." if len(content) > 100 else content
                        print(f"     {role_icon} [{msg.get('role')}]: {content_preview}")
    
    except Exception as e:
        print(f"❌ Redis error: {e}")
    finally:
        await client.close()


async def view_checkpoint_tables():
    """View LangGraph checkpoint tables info"""
    print("\n" + "="*60)
    print("🔵 LANGGRAPH CHECKPOINTER (checkpoint_* tables)")
    print("="*60)
    
    prisma = Prisma()
    await prisma.connect()
    
    try:
        # Query checkpoint count
        result = await prisma.execute_raw(
            "SELECT COUNT(*) as count FROM checkpoints"
        )
        print(f"\n📦 Checkpoints count: {result}")
        
        # Get sample checkpoint info
        threads = await prisma.execute_raw(
            "SELECT DISTINCT thread_id FROM checkpoints LIMIT 10"
        )
        print(f"📋 Thread IDs in checkpoints: {threads}")
        
    except Exception as e:
        print(f"❌ Could not query checkpoint tables: {e}")
        print("   (This is normal if the table structure differs)")
    
    await prisma.disconnect()


async def main():
    print("\n🔍 VIEWING ALL STORED CONVERSATION DATA")
    print("="*60)
    
    await view_prisma_data()
    await view_redis_data()
    await view_checkpoint_tables()
    
    print("\n" + "="*60)
    print("✅ Done!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
