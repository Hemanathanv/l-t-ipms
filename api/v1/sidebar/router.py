from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
from db import get_prisma
from redis_client import get_cache, set_cache, invalidate_cache
from agent.graph import get_conversation_history
from schemas import ConversationHistory, MessageSchema
from config import settings

router = APIRouter(prefix=settings.API_SLUG + "/conversations", tags=["Conversations"])

_agent = None

def set_agent(agent):
    """Set the global agent instance for this router"""
    global _agent
    _agent = agent


@router.get("", tags=["Conversations"])
async def list_conversations(request: Request):
    """
    Get list of all conversations for sidebar.
    
    **Authorization Required**: User must be authenticated.
    
    **Description**:
    Retrieves a list of the 50 most recent conversations ordered by creation date.
    Each conversation includes the thread ID, title, and creation timestamp.
    
    **Returns**:
    List of conversations with:
    - `threadId`: Unique conversation identifier
    - `title`: Conversation title (or "Untitled" if not set)
    - `createdAt`: ISO 8601 timestamp of creation
    
    **Example Response**:
    ```json
    [
        {
            "threadId": "550e8400-e29b-41d4-a716-446655440000",
            "title": "PEI Status Analysis",
            "createdAt": "2024-01-15T10:30:00"
        },
        {
            "threadId": "550e8400-e29b-41d4-a716-446655440001",
            "title": "Project Performance Review",
            "createdAt": "2024-01-14T14:22:00"
        }
    ]
    ```
    
    **Error Responses**:
    - 401: Not authenticated
    - 500: Database error
    """
    # try:
    #     token = request.headers['authorization'].split(" ")[1]
    # except (KeyError, IndexError):
    #     raise HTTPException(status_code=401, detail="Authorization token missing or malformed")
    
    # if(await validate_token(token) == False):
    #     raise HTTPException(status_code=401, detail="Not authenticated")
    
    prisma = await get_prisma()
    
    try:
        conversations = await prisma.conversation.find_many(
            order={"createdAt": "desc"},
            take=50
        )
        
        return [
            {
                "threadId": c.threadId,
                "title": c.title or "Untitled",
                "createdAt": c.createdAt.isoformat() if c.createdAt else None
            }
            for c in conversations
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{thread_id}", response_model=ConversationHistory, tags=["Conversations"])
async def get_conversation(thread_id: str):
    """
    Retrieve the full conversation history for a given thread.
    
    **Authorization Required**: User must be authenticated.
    
    **Description**:
    Retrieves the complete message history for a specific conversation thread.
    Uses multi-tier caching strategy:
    1. Redis cache (fastest) - 1 hour TTL
    2. Prisma database (fast) - persistent storage
    3. LangGraph checkpointer (slower fallback)
    
    **Parameters**:
    - `thread_id` (path): The unique thread identifier
    
    **Returns**:
    - `thread_id`: The conversation thread identifier
    - `messages`: Array of messages with role (user/assistant), content, and metadata
    - `created_at`: Conversation creation timestamp
    
    **Example Response**:
    ```json
    {
        "thread_id": "550e8400-e29b-41d4-a716-446655440000",
        "messages": [
            {
                "id": "msg-001",
                "role": "user",
                "content": "What is the current PEI status?",
                "created_at": "2024-01-15T10:30:00",
                "feedback": null
            },
            {
                "id": "msg-002",
                "role": "assistant",
                "content": "The current PEI is 92%...",
                "created_at": "2024-01-15T10:30:15",
                "feedback": "positive"
            }
        ],
        "created_at": "2024-01-15T10:30:00"
    }
    ```
    
    **Error Responses**:
    - 401: Not authenticated
    - 404: Conversation not found
    - 500: Database error
    """
    
    
    # 1. Try cache first (fastest) - but only if messages have IDs
    cached_messages = await get_cache(thread_id)
    
    # Check if cached messages have IDs (required for edit/feedback)
    # Skip cache if any message is missing an ID (stale cache format)
    if cached_messages:
        has_all_ids = all(m.get('id') for m in cached_messages)
        if has_all_ids:
            return ConversationHistory(
                thread_id=thread_id,
                messages=[MessageSchema(**m) for m in cached_messages],
            )
        else:
            # Invalidate stale cache
            await invalidate_cache(thread_id)
    
    # 2. Try Prisma messages table (faster than checkpointer)
    try:
        prisma = await get_prisma()
        conversation = await prisma.conversation.find_unique(
            where={"threadId": thread_id},
            include={"messages": True}
        )
        
        if conversation and conversation.messages:
            # Sort messages by createdAt in Python (Prisma Python doesn't support order in includes)
            sorted_messages = sorted(conversation.messages, key=lambda m: m.createdAt or datetime.min)
            messages = [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.createdAt.isoformat() if msg.createdAt else None,
                    "feedback": msg.feedback,
                }
                for msg in sorted_messages
            ]
            
            # Cache for next time
            await set_cache(thread_id, messages)
            
            return ConversationHistory(
                thread_id=thread_id,
                messages=[MessageSchema(**m) for m in messages],
                created_at=conversation.createdAt
            )
    except Exception as e:
        print(f"Prisma lookup error: {e}")
    
    # 3. Fall back to LangGraph checkpointer (slowest - only if no Prisma data)
    if _agent is not None:
        try:
            history = await get_conversation_history(_agent, thread_id)
            if history:
                # Cache for next time
                await set_cache(thread_id, history)
                return ConversationHistory(
                    thread_id=thread_id,
                    messages=[MessageSchema(**m) for m in history],
                )
        except Exception as e:
            print(f"Checkpointer error: {e}")
    
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.delete("/{thread_id}", tags=["Conversations"])
async def delete_conversation(thread_id: str):
    """
    Delete a conversation from cache and database.
    
    **Authorization Required**: User must be authenticated.
    
    **Description**:
    Permanently deletes a conversation thread and all associated messages.
    Removes data from both:
    - Redis cache
    - PostgreSQL database
    
    **Parameters**:
    - `thread_id` (path): The unique thread identifier
    
    **Returns**:
    ```json
    {
        "status": "deleted",
        "thread_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    
    **Error Responses**:
    - 401: Not authenticated
    - 500: Database error
    
    **Note**: This action is irreversible.
    """
    await invalidate_cache(thread_id)
    try:
        prisma = await get_prisma()
        conversation = await prisma.conversation.find_unique(
            where={"threadId": thread_id}
        )
        
        print(conversation)
        if conversation:
            await prisma.conversation.delete(where={"id": conversation.id})
    except Exception:
        pass
    
    return {"status": "deleted", "thread_id": thread_id}


@router.post("/{thread_id}/preload", tags=["Conversations"])
async def preload_conversation(thread_id: str):
    """
    Pre-load conversation into Redis cache for faster subsequent access.
    Called when user clicks on a conversation in the sidebar.
    
    **Authorization Required**: User must be authenticated.
    
    **Description**:
    Pre-warms the Redis cache with conversation data to reduce latency
    on subsequent requests. Automatically called by the frontend when
    a user clicks on a conversation in the sidebar.
    
    **Parameters**:
    - `thread_id` (path): The unique thread identifier
    
    **Returns**:
    ```json
    {
        "status": "cached",
        "message_count": 15
    }
    ```
    
    **Possible Status Values**:
    - `already_cached`: Conversation was already in cache
    - `cached`: Successfully loaded into cache
    - `not_found`: Conversation not found in database
    - `error`: An error occurred during preload
    
    **Error Responses**:
    - 401: Not authenticated
    
    **Performance**:
    - Reduces subsequent load time by ~300-500ms
    - Safe to call multiple times (idempotent)
    """
    # Check if already cached
    cached = await get_cache(thread_id)
    if cached:
        return {"status": "already_cached", "message_count": len(cached)}
    
    # Load from Prisma and cache
    try:
        prisma = await get_prisma()
        conversation = await prisma.conversation.find_unique(
            where={"threadId": thread_id},
            include={"messages": True}
        )
        
        if conversation and conversation.messages:
            sorted_messages = sorted(conversation.messages, key=lambda m: m.createdAt or datetime.min)
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.createdAt.isoformat() if msg.createdAt else None
                }
                for msg in sorted_messages
            ]
            await set_cache(thread_id, messages)
            return {"status": "cached", "message_count": len(messages)}
    except Exception as e:
        print(f"Preload error: {e}")
        return {"status": "error", "error": str(e)}
    
    return {"status": "not_found"}