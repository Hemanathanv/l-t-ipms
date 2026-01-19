# redis_client.py
import redis.asyncio as redis
from os import getenv

REDIS_URI = getenv("REDIS_URI", "redis://172.22.0.2:6379/0")

# redis_client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
redis_client = redis.from_url(REDIS_URI, decode_responses=True)