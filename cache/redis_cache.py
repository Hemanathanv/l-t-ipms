"""
Redis Cache Manager for conversation caching
Provides fast access to recent conversation messages
"""

import json
from typing import Any

import redis.asyncio as redis

from config import settings


class RedisCache:
    """Redis cache manager for conversation data"""
    
    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: redis.Redis | None = None
    
    async def connect(self) -> None:
        """Establish Redis connection"""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True
            )
    
    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
    
    async def ping(self) -> bool:
        """Check if Redis is reachable"""
        try:
            if self._client:
                await self._client.ping()
                return True
        except Exception:
            pass
        return False
    
    def _conversation_key(self, thread_id: str) -> str:
        """Generate Redis key for conversation cache"""
        return f"conversation:{thread_id}:messages"
    
    async def get_conversation_cache(
        self, 
        thread_id: str
    ) -> list[dict[str, Any]] | None:
        """
        Get cached conversation messages.
        
        Args:
            thread_id: The conversation thread ID
            
        Returns:
            List of message dicts or None if not cached
        """
        if not self._client:
            return None
        
        try:
            key = self._conversation_key(thread_id)
            data = await self._client.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None
    
    async def set_conversation_cache(
        self,
        thread_id: str,
        messages: list[dict[str, Any]],
        ttl: int | None = None
    ) -> bool:
        """
        Cache conversation messages.
        
        Args:
            thread_id: The conversation thread ID
            messages: List of message dicts to cache
            ttl: Time-to-live in seconds (default from settings)
            
        Returns:
            True if cached successfully
        """
        if not self._client:
            return False
        
        try:
            key = self._conversation_key(thread_id)
            ttl = ttl or settings.CACHE_TTL_SECONDS
            await self._client.setex(key, ttl, json.dumps(messages))
            return True
        except Exception:
            pass
        return False
    
    async def invalidate_cache(self, thread_id: str) -> bool:
        """
        Invalidate (delete) cached conversation.
        
        Args:
            thread_id: The conversation thread ID
            
        Returns:
            True if deleted successfully
        """
        if not self._client:
            return False
        
        try:
            key = self._conversation_key(thread_id)
            await self._client.delete(key)
            return True
        except Exception:
            pass
        return False
    
    async def append_message(
        self,
        thread_id: str,
        message: dict[str, Any]
    ) -> bool:
        """
        Append a message to cached conversation.
        Refreshes TTL on update.
        
        Args:
            thread_id: The conversation thread ID
            message: Message dict to append
            
        Returns:
            True if appended successfully
        """
        messages = await self.get_conversation_cache(thread_id) or []
        messages.append(message)
        return await self.set_conversation_cache(thread_id, messages)


# Singleton instance
_redis_cache: RedisCache | None = None


async def get_redis_cache() -> RedisCache:
    """Get or create Redis cache instance"""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
        await _redis_cache.connect()
    return _redis_cache
