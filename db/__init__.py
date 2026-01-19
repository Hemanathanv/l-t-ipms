"""
Database module for L&T IPMS Conversational App
Provides Prisma client initialization and access
"""

from prisma import Prisma

# Singleton Prisma client instance
_prisma_client: Prisma | None = None


async def get_prisma() -> Prisma:
    """
    Get or create the Prisma client instance.
    This ensures we reuse the same connection pool.
    """
    global _prisma_client
    if _prisma_client is None:
        _prisma_client = Prisma()
    if not _prisma_client.is_connected():
        await _prisma_client.connect()
    return _prisma_client


async def close_prisma() -> None:
    """Close the Prisma client connection"""
    global _prisma_client
    if _prisma_client is not None and _prisma_client.is_connected():
        await _prisma_client.disconnect()
        _prisma_client = None


# Convenience exports
__all__ = ["get_prisma", "close_prisma", "Prisma"]
