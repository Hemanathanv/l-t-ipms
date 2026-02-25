# redis_client.py
"""
Consolidated Redis client for caching and pub/sub.
Provides conversation caching with 1-hour TTL.
"""

import json
from typing import Any
import redis.asyncio as redis
from config import settings

# Cache TTL: 1 hour
CACHE_TTL = 3600

# Singleton Redis client
_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


async def ping() -> bool:
    """Check if Redis is reachable."""
    try:
        client = await get_redis_client()
        await client.ping()
        return True
    except Exception:
        return False


def _cache_key(thread_id: str) -> str:
    """Generate Redis key for conversation cache."""
    return f"conversation:{thread_id}:messages"


async def get_cache(thread_id: str) -> list[dict[str, Any]] | None:
    """
    Get cached conversation messages.
    Returns None if not cached or on error.
    """
    try:
        client = await get_redis_client()
        data = await client.get(_cache_key(thread_id))
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[CACHE] Error getting cache for {thread_id}: {e}")
    return None


async def set_cache(
    thread_id: str,
    messages: list[dict[str, Any]],
    ttl: int = CACHE_TTL
) -> bool:
    """
    Cache conversation messages with TTL.
    Default TTL is 1 hour (3600 seconds).
    """
    try:
        client = await get_redis_client()
        await client.setex(_cache_key(thread_id), ttl, json.dumps(messages))
        print(f"[CACHE] Cached {len(messages)} messages for {thread_id} (TTL: {ttl}s)")
        return True
    except Exception as e:
        print(f"[CACHE] Error caching {thread_id}: {e}")
    return False


async def append_message(thread_id: str, message: dict[str, Any]) -> bool:
    """
    Append a message to cached conversation.
    Creates cache if not exists, refreshes TTL on update.
    """
    try:
        messages = await get_cache(thread_id) or []
        messages.append(message)
        return await set_cache(thread_id, messages)
    except Exception as e:
        print(f"[CACHE] Error appending to {thread_id}: {e}")
    return False


async def invalidate_cache(thread_id: str) -> bool:
    """Delete cached conversation."""
    try:
        client = await get_redis_client()
        await client.delete(_cache_key(thread_id))
        return True
    except Exception:
        pass
    return False


# ─── Pub/Sub for streaming ───────────────────────────────────────────────────

def stream_channel_key(thread_id: str) -> str:
    """Generate Redis channel name for a streaming session."""
    return f"stream:{thread_id}"


async def publish_stream_event(thread_id: str, event_data: dict) -> bool:
    """
    Publish a stream event to the Redis channel for a thread.
    event_data should be a JSON-serializable dict, e.g.
    {"type": "stream", "content": "...", "agent": "chat", "seq": 0}
    """
    try:
        client = await get_redis_client()
        channel = stream_channel_key(thread_id)
        payload = json.dumps(event_data)
        await client.publish(channel, payload)
        return True
    except Exception as e:
        print(f"[PUBSUB] Error publishing to {thread_id}: {e}")
        return False


async def subscribe_stream(thread_id: str, ready_event: "asyncio.Event | None" = None):
    """
    Async generator that subscribes to the streaming channel for a thread
    and yields parsed event dicts until an 'end' or 'error' event is received.
    
    Args:
        thread_id: conversation thread ID
        ready_event: if provided, this event is SET once the subscription is active.
                     The publisher should await this before starting to publish.
    
    Usage:
        ready = asyncio.Event()
        asyncio.create_task(publisher(ready))
        async for event in subscribe_stream(thread_id, ready_event=ready):
            await websocket.send_json(event)
    """
    import asyncio as _asyncio
    
    client = await get_redis_client()
    channel = stream_channel_key(thread_id)
    pubsub = client.pubsub()
    
    try:
        await pubsub.subscribe(channel)
        print(f"[PUBSUB] Subscribed to {channel}")
        
        # Signal that we're ready to receive
        if ready_event is not None:
            ready_event.set()
        
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            
            try:
                event = json.loads(message["data"])
                yield event
                
                # Stop listening after end or error event
                if event.get("type") in ("end", "error"):
                    break
            except json.JSONDecodeError:
                continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        print(f"[PUBSUB] Unsubscribed from {channel}")
