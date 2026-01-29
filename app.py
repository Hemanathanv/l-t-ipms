"""
L&T IPMS Conversational API
FastAPI application with LangGraph agent, Redis caching, and PostgreSQL persistence
"""

import uuid
import json
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
import redis.asyncio as redis_async
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr

from config import settings
from db import get_prisma, close_prisma
from redis_client import get_redis_client, close_redis, get_cache, set_cache, append_message as cache_append_message, ping as redis_ping
from agent import create_agent, create_checkpointer
from agent.graph import run_conversation, get_conversation_history
from auth.utils import hash_password, verify_password, create_session_token
from auth.dependencies import get_current_user, get_optional_user, get_session_token
from schemas import (
    ChatRequest,
    ChatResponse,
    ConversationHistory,
    HealthResponse,
    MessageSchema,
)


# Global agent instance
_agent = None
_checkpointer_cm = None  # Context manager
_checkpointer = None  # Actual checkpointer instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Initializes and cleans up database, cache, and agent connections.
    """
    global _agent, _checkpointer_cm, _checkpointer
    
    print("🚀 Starting L&T IPMS Conversational API...")
    
    # Initialize Prisma client
    prisma = await get_prisma()
    print("✅ PostgreSQL (Prisma) connected")
    
    # Initialize Redis client
    redis_client = await get_redis_client()
    await redis_client.ping()
    print("✅ Redis connected")
    
    # Initialize PostgreSQL checkpointer (async context manager)
    _checkpointer_cm = create_checkpointer()
    _checkpointer = await _checkpointer_cm.__aenter__()
    
    # Setup checkpointer tables
    await _checkpointer.setup()
    print("✅ LangGraph checkpointer initialized")
    
    # Initialize LangGraph agent with checkpointer
    _agent = await create_agent(checkpointer=_checkpointer)
    print("✅ LangGraph agent compiled")
    
    print(f"🌐 API ready at http://localhost:8000")
    
    yield  # Application runs here
    
    # Cleanup on shutdown
    print("🛑 Shutting down...")
    await close_prisma()
    await close_redis()
    if _checkpointer_cm:
        await _checkpointer_cm.__aexit__(None, None, None)
    print("✅ All connections closed")


# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="Conversational AI API powered by LangGraph with Redis caching and PostgreSQL persistence",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CORS is configured to allow requests from Next.js frontend
# Note: Static files are now served by the Next.js frontend
# The old static file routes have been removed


# ============================================================================
# Auth Pydantic Models
# ============================================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    systemRole: str
    isActive: bool


class SessionResponse(BaseModel):
    user: UserResponse
    token: str


# ============================================================================
# Auth Endpoints
# ============================================================================

@app.post("/auth/login", tags=["Auth"])
async def login(request: LoginRequest, response: Response):
    """
    Authenticate user and create a session.
    Returns session token and sets cookie.
    """
    prisma = await get_prisma()
    
    # Find user by email
    user = await prisma.user.find_unique(
        where={"email": request.email.lower()}
    )
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not verify_password(request.password, user.passwordHash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check if user is active
    if not user.isActive:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    # Create session
    token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    await prisma.session.create(
        data={
            "userId": user.id,
            "token": token,
            "expiresAt": expires_at,
        }
    )
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )
    
    return {
        "status": "success",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "systemRole": user.systemRole,
            "isActive": user.isActive,
        },
        "token": token,
    }


@app.post("/auth/logout", tags=["Auth"])
async def logout(
    response: Response,
    token: Optional[str] = Depends(get_session_token)
):
    """
    Invalidate the current session.
    """
    if token:
        prisma = await get_prisma()
        try:
            await prisma.session.delete_many(
                where={"token": token}
            )
        except Exception:
            pass  # Session might not exist
    
    # Clear cookie
    response.delete_cookie(key="session_token")
    
    return {"status": "success", "message": "Logged out"}


@app.get("/auth/session", tags=["Auth"])
async def get_session(user = Depends(get_optional_user)):
    """
    Get the current user session.
    Returns null if not authenticated.
    """
    if not user:
        return {"user": None}
    
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "systemRole": user.systemRole,
            "isActive": user.isActive,
        }
    }


@app.post("/auth/change-password", tags=["Auth"])
async def change_password(
    request: ChangePasswordRequest,
    user = Depends(get_current_user)
):
    """
    Change the current user's password.
    Requires old password for verification.
    """
    prisma = await get_prisma()
    
    # Verify old password
    if not verify_password(request.old_password, user.passwordHash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Validate new password
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    
    if len(request.new_password) > 50:
        raise HTTPException(status_code=400, detail="New password is too long")
    
    # Hash and save new password
    new_hash = hash_password(request.new_password)
    
    await prisma.user.update(
        where={"id": user.id},
        data={"passwordHash": new_hash}
    )
    
    return {"status": "success", "message": "Password changed successfully"}


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/projects", tags=["Projects"])
async def get_projects():
    """
    Get list of projects from SraTable with date range.
    """
    prisma = await get_prisma()
    
    try:
        # Get distinct projects using Prisma ORM
        all_projects = await prisma.sraactivitytable.find_many(
            distinct=["projectId", "projectName"],
            order={"projectName": "asc"}
        )
        
        # Get date range
        date_stats = await prisma.sraactivitytable.find_first(
            order={"date": "asc"}
        )
        date_stats_max = await prisma.sraactivitytable.find_first(
            order={"date": "desc"}
        )
        
        # Build unique projects list
        seen = set()
        projects = []
        for row in all_projects:
            if row.projectId not in seen:
                seen.add(row.projectId)
                projects.append({
                    "id": row.projectId,
                    "name": row.projectName
                })
        
        date_from = date_stats.date if date_stats else None
        date_to = date_stats_max.date if date_stats_max else None
        
        return {
            "projects": projects,
            "dateRange": {
                "from": date_from.strftime("%b %Y") if date_from else "N/A",
                "to": date_to.strftime("%b %Y") if date_to else "N/A"
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "projects": [],
            "dateRange": {"from": "N/A", "to": "N/A"},
            "error": str(e)
        }


@app.get("/api/conversations", tags=["Conversations"])
async def list_conversations():
    """
    Get list of all conversations for sidebar.
    """
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

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Check the health status of all services.
    """
    # Check Redis
    try:
        cache = await get_redis_cache()
        redis_ok = await cache.ping()
        redis_status = "connected" if redis_ok else "disconnected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    # Check PostgreSQL via Prisma
    try:
        prisma = await get_prisma()
        await prisma.execute_raw("SELECT 1")
        postgres_status = "connected"
    except Exception as e:
        postgres_status = f"error: {str(e)}"
    
    # Check LLM endpoint
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.BASE_URL}/v1/models",
                timeout=5.0
            )
            llm_status = "connected" if response.status_code == 200 else f"status: {response.status_code}"
    except Exception as e:
        llm_status = f"error: {str(e)}"
    
    # Determine overall status
    overall = "healthy"
    if "error" in redis_status or "error" in postgres_status:
        overall = "degraded"
    if "error" in redis_status and "error" in postgres_status:
        overall = "unhealthy"
    
    return HealthResponse(
        status=overall,
        redis=redis_status,
        postgres=postgres_status,
        llm=llm_status,
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Send a message and receive a response from the AI assistant.
    
    - If `thread_id` is not provided, a new conversation will be started.
    - If `thread_id` is provided, the conversation will continue from where it left off.
    - If `project_id` is provided, it will be used to filter SRA tool queries.
    """
    global _agent
    
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    # Generate thread_id if not provided
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # Get cache instance
    cache = await get_redis_cache()
    
    # Get project context if project_id is provided
    project_context = None
    if request.project_id:
        prisma = await get_prisma()
        try:
            # Get project info and date range
            project_data = await prisma.sraactivitytable.find_first(
                where={"projectId": request.project_id}
            )
            date_stats = await prisma.sraactivitytable.find_first(
                where={"projectId": request.project_id},
                order={"date": "asc"}
            )
            date_stats_max = await prisma.sraactivitytable.find_first(
                where={"projectId": request.project_id},
                order={"date": "desc"}
            )
            
            if project_data:
                date_from = date_stats.date.strftime("%Y-%m-%d") if date_stats else "N/A"
                date_to = date_stats_max.date.strftime("%Y-%m-%d") if date_stats_max else "N/A"
                project_context = {
                    "project_id": request.project_id,
                    "project_name": project_data.projectName,
                    "date_range": f"{date_from} to {date_to}",
                    "date_from": date_from,
                    "date_to": date_to
                }
        except Exception as e:
            print(f"Error getting project context: {e}")
    
    try:
        # Run conversation with the agent (with project context)
        response = await run_conversation(_agent, request.message, thread_id, project_context)
        
        # Get updated message count
        history = await get_conversation_history(_agent, thread_id)
        message_count = len(history)
        
        # Cache the updated conversation
        await cache.set_conversation_cache(thread_id, history)
        
        # Also persist to Prisma for custom metadata
        await _persist_message_to_db(thread_id, "user", request.message)
        await _persist_message_to_db(thread_id, "assistant", response)
        
        return ChatResponse(
            response=response,
            thread_id=thread_id,
            message_count=message_count,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(request: ChatRequest):
    """
    Stream a chat response using Server-Sent Events (SSE).
    Uses direct LangGraph streaming with Redis caching.
    
    Returns a stream of events:
    - init: Thread ID
    - stream: Incremental content chunks
    - tool_call: Tool invocation
    - tool_result: Tool output  
    - end: Stream finished
    """
    global _agent
    from langchain_core.messages import HumanMessage
    
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    # Generate thread_id if not provided
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # Get project context if project_id is provided
    project_context = None
    if request.project_id:
        prisma = await get_prisma()
        try:
            project_data = await prisma.sraactivitytable.find_first(
                where={"projectId": request.project_id}
            )
            date_stats = await prisma.sraactivitytable.find_first(
                where={"projectId": request.project_id},
                order={"date": "asc"}
            )
            date_stats_max = await prisma.sraactivitytable.find_first(
                where={"projectId": request.project_id},
                order={"date": "desc"}
            )
            
            if project_data:
                date_from = date_stats.date.strftime("%Y-%m-%d") if date_stats else "N/A"
                date_to = date_stats_max.date.strftime("%Y-%m-%d") if date_stats_max else "N/A"
                project_context = {
                    "project_id": request.project_id,
                    "project_name": project_data.projectName,
                    "date_range": f"{date_from} to {date_to}",
                    "date_from": date_from,
                    "date_to": date_to
                }
        except Exception as e:
            print(f"Error getting project context: {e}")
    
    # Build enhanced message with project context
    if project_context:
        context_info = (
            f"\n\n[CONTEXT]\n"
            f"Selected Project: {project_context.get('project_name', 'Unknown')} ({project_context.get('project_id', 'N/A')})\n"
            f"Available Date Range: {project_context.get('date_range', 'N/A')}\n"
            f"When calling tools, use project_id='{project_context.get('project_id', '')}' to filter results.\n"
            f"[/CONTEXT]"
        )
        enhanced_message = request.message + context_info
    else:
        enhanced_message = request.message
    
    async def event_generator():
        """Generate SSE events from LangGraph streaming."""
        
        # Persist user message to DB
        try:
            await _persist_message_to_db(thread_id, "user", request.message)
        except Exception as e:
            print(f"Error persisting user message: {e}")
        
        # Cache user message
        try:
            await cache_append_message(thread_id, {"role": "user", "content": request.message})
        except Exception:
            pass  # Ignore cache errors
        
        # Yield initial event with thread_id
        yield f"data: {json.dumps({'type': 'init', 'thread_id': thread_id})}\n\n"
        
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {
            "messages": [HumanMessage(content=enhanced_message)],
            "thread_id": thread_id
        }
        
        seq = 0
        streamed_content = ""
        final_sent = False
        
        try:
            async for event in _agent.astream_events(initial_state, version="v2", config=config):
                event_type = event.get("event", "")
                meta = event.get("metadata", {}) or {}
                agent_name = meta.get("langgraph_node") or "agent"
                
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, 'content') and chunk.content:
                        streamed_content += chunk.content
                        yield f"data: {json.dumps({'type': 'stream', 'content': chunk.content, 'agent': agent_name, 'seq': seq})}\n\n"
                        seq += 1
                
                elif event_type == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if output and hasattr(output, "tool_calls") and output.tool_calls:
                        for tool_call in output.tool_calls:
                            tool_name = tool_call.get('name', 'unknown') if isinstance(tool_call, dict) else getattr(tool_call, 'name', 'unknown')
                            yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'seq': seq})}\n\n"
                            seq += 1
                
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'seq': seq})}\n\n"
                    seq += 1
                
                elif event_type == "on_chain_end" and agent_name == "chat" and not final_sent:
                    out = event.get("data", {}).get("output")
                    if out is None:
                        continue
                    
                    msgs = out.get("messages") if isinstance(out, dict) else out if isinstance(out, list) else []
                    
                    for m in reversed(msgs):
                        content = getattr(m, "content", None)
                        has_tool_calls = hasattr(m, "tool_calls") and m.tool_calls
                        
                        if content and not has_tool_calls:
                            if content != streamed_content:
                                final_sent = True
                                try:
                                    await _persist_message_to_db(thread_id, "assistant", content)
                                    await cache_append_message(thread_id, {"role": "assistant", "content": content})
                                except Exception as e:
                                    print(f"Error persisting AI message: {e}")
                                
                                yield f"data: {json.dumps({'type': 'stream', 'content': content, 'agent': agent_name, 'seq': seq})}\n\n"
                                seq += 1
                            break
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



@app.get("/conversations/{thread_id}", response_model=ConversationHistory, tags=["Conversations"])
async def get_conversation(thread_id: str):
    """
    Retrieve the full conversation history for a given thread.
    
    Checks: Redis cache -> Prisma messages (faster) -> LangGraph checkpointer (slower)
    """
    global _agent
    
    # 1. Try cache first (fastest)
    cached_messages = await get_cache(thread_id)
    
    if cached_messages:
        return ConversationHistory(
            thread_id=thread_id,
            messages=[MessageSchema(**m) for m in cached_messages],
        )
    
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
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.createdAt.isoformat() if msg.createdAt else None
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


@app.delete("/conversations/{thread_id}", tags=["Conversations"])
async def delete_conversation(thread_id: str):
    """
    Delete a conversation from cache and database.
    """
    # Clear from cache
    from redis_client import invalidate_cache
    await invalidate_cache(thread_id)
    
    # Clear from Prisma
    try:
        prisma = await get_prisma()
        conversation = await prisma.conversation.find_unique(
            where={"threadId": thread_id}
        )
        if conversation:
            await prisma.conversation.delete(where={"id": conversation.id})
    except Exception:
        pass  # Conversation might not exist in Prisma
    
    return {"status": "deleted", "thread_id": thread_id}


@app.post("/conversations/{thread_id}/preload", tags=["Conversations"])
async def preload_conversation(thread_id: str):
    """
    Pre-load conversation into Redis cache for faster subsequent access.
    Called when user clicks on a conversation in the sidebar.
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


async def _persist_message_to_db(
    thread_id: str, 
    role: str, 
    content: str,
    *,
    input_tokens: int = None,
    output_tokens: int = None,
    total_tokens: int = None,
    tool_calls: list = None,
    tool_name: str = None,
    model: str = None,
    metadata: dict = None
):
    """
    Persist a message to the Prisma database with optional metadata.
    Creates the conversation if it doesn't exist.
    
    Args:
        thread_id: The conversation thread ID
        role: Message role ('user', 'assistant', 'system', 'tool')
        content: Message content
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        total_tokens: Total tokens used
        tool_calls: List of tool calls [{name, args, result}]
        tool_name: Name of tool (for tool result messages)
        model: Model name used for this response
        metadata: Additional metadata dict {latency_ms, finish_reason, etc.}
    """
    from datetime import datetime
    import json as json_lib
    
    prisma = await get_prisma()
    
    # Find or create conversation
    conversation = await prisma.conversation.find_unique(
        where={"threadId": thread_id}
    )
    
    if not conversation:
        conversation = await prisma.conversation.create(
            data={
                "threadId": thread_id,
                "title": content[:50] + "..." if len(content) > 50 else content,
            }
        )
    else:
        # Update the conversation's updated_at timestamp
        await prisma.conversation.update(
            where={"id": conversation.id},
            data={"updatedAt": datetime.utcnow()}
        )
    
    # Build message data
    message_data = {
        "conversationId": conversation.id,
        "role": role,
        "content": content,
    }
    
    # Add optional fields if provided
    if input_tokens is not None:
        message_data["inputTokens"] = input_tokens
    if output_tokens is not None:
        message_data["outputTokens"] = output_tokens
    if total_tokens is not None:
        message_data["totalTokens"] = total_tokens
    if tool_calls is not None:
        message_data["toolCalls"] = json_lib.dumps(tool_calls) if isinstance(tool_calls, list) else tool_calls
    if tool_name is not None:
        message_data["toolName"] = tool_name
    if model is not None:
        message_data["model"] = model
    if metadata is not None:
        message_data["metadata"] = json_lib.dumps(metadata) if isinstance(metadata, dict) else metadata
    
    # Create the message
    await prisma.message.create(data=message_data)


@app.websocket("/ws/chat/{thread_id}")
async def websocket_chat(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for real-time chat streaming.
    Uses direct astream_events for reliable streaming.
    Caches messages with 1-hour TTL.
    
    Path parameter: thread_id - use "new" for a new conversation, or an existing thread_id
    Client sends: {"message": "...", "project_id": "..." (optional)}
    Server sends: StreamEvent JSON objects
    """
    global _agent
    from langchain_core.messages import HumanMessage
    
    # Handle "new" as a special case to generate a new thread_id
    if thread_id == "new":
        thread_id = str(uuid.uuid4())
    
    await websocket.accept()
    
    # Send init event immediately with the thread_id
    await websocket.send_json({"type": "init", "thread_id": thread_id})
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")
            project_id = data.get("project_id")
            
            if not message:
                await websocket.send_json({"type": "error", "error": "No message provided"})
                continue
            
            if _agent is None:
                await websocket.send_json({"type": "error", "error": "Agent not initialized"})
                continue
            
            # Build project context
            project_context = None
            if project_id:
                try:
                    prisma = await get_prisma()
                    project_data = await prisma.sraactivitytable.find_first(where={"projectId": project_id})
                    date_stats = await prisma.sraactivitytable.find_first(where={"projectId": project_id}, order={"date": "asc"})
                    date_stats_max = await prisma.sraactivitytable.find_first(where={"projectId": project_id}, order={"date": "desc"})
                    
                    if project_data:
                        date_from = date_stats.date.strftime("%Y-%m-%d") if date_stats else "N/A"
                        date_to = date_stats_max.date.strftime("%Y-%m-%d") if date_stats_max else "N/A"
                        project_context = {
                            "project_id": project_id,
                            "project_name": project_data.projectName,
                            "date_range": f"{date_from} to {date_to}",
                            "date_from": date_from,
                            "date_to": date_to,
                        }
                except Exception as e:
                    print(f"Error getting project context: {e}")
            
            # Build enhanced message with project context
            if project_context:
                context_info = (
                    f"\n\n[CONTEXT]\n"
                    f"Selected Project: {project_context.get('project_name', 'Unknown')} ({project_context.get('project_id', 'N/A')})\n"
                    f"Available Date Range: {project_context.get('date_range', 'N/A')}\n"
                    f"When calling tools, use project_id='{project_context.get('project_id', '')}' to filter results.\n"
                    f"[/CONTEXT]"
                )
                enhanced_message = message + context_info
            else:
                enhanced_message = message
            
            # Persist user message to DB
            try:
                await _persist_message_to_db(thread_id, "user", message)
            except Exception as e:
                print(f"Error persisting user message: {e}")
            
            try:
                await cache_append_message(thread_id, {"role": "user", "content": message})
            except Exception as e:
                print(f"Error caching user message: {e}")
            
            # Stream directly from LangGraph
            config = {"configurable": {"thread_id": thread_id}}
            initial_state = {
                "messages": [HumanMessage(content=enhanced_message)],
                "thread_id": thread_id
            }
            
            seq = 0
            streamed_content = ""
            final_sent = False
            assistant_message_saved = False
            
            # Track metadata for persistence
            collected_tool_calls = []
            usage_info = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            model_name = None
            start_time = asyncio.get_event_loop().time()
            
            try:
                async for event in _agent.astream_events(initial_state, version="v2", config=config):
                    event_type = event.get("event", "")
                    meta = event.get("metadata", {}) or {}
                    agent_name = meta.get("langgraph_node") or "agent"
                    
                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, 'content') and chunk.content:
                            streamed_content += chunk.content
                            await websocket.send_json({
                                "type": "stream",
                                "content": chunk.content,
                                "agent": agent_name,
                                "seq": seq
                            })
                            seq += 1
                    
                    elif event_type == "on_chat_model_end":
                        output = event.get("data", {}).get("output")
                        
                        # Debug: show actual values to diagnose token extraction
                        if output:
                            print(f"[DEBUG] usage_metadata = {getattr(output, 'usage_metadata', None)}")
                            print(f"[DEBUG] response_metadata = {getattr(output, 'response_metadata', None)}")
                        
                        # Extract usage info - check multiple sources for compatibility
                        # Source 1: usage_metadata (OpenAI, Gemini, LM Studio)
                        if output and hasattr(output, "usage_metadata") and output.usage_metadata:
                            usage = output.usage_metadata
                            # Handle both dict and object types
                            if isinstance(usage, dict):
                                usage_info["input_tokens"] += usage.get("input_tokens", 0) or 0
                                usage_info["output_tokens"] += usage.get("output_tokens", 0) or 0
                                usage_info["total_tokens"] += usage.get("total_tokens", 0) or 0
                            else:
                                usage_info["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
                                usage_info["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
                                usage_info["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
                            print(f"[DEBUG] Token usage: input={usage_info['input_tokens']}, output={usage_info['output_tokens']}, total={usage_info['total_tokens']}")
                        
                        # Extract response metadata
                        if output and hasattr(output, "response_metadata") and output.response_metadata:
                            resp_meta = output.response_metadata
                            print(f"[DEBUG] Response metadata keys: {list(resp_meta.keys())}")
                            
                            # Extract model name
                            if "model_name" in resp_meta:
                                model_name = resp_meta["model_name"]
                            elif "model" in resp_meta:
                                model_name = resp_meta["model"]
                            
                            # Source 2: response_metadata.token_usage (LM Studio, some local LLMs)
                            if "token_usage" in resp_meta and usage_info["total_tokens"] == 0:
                                token_usage = resp_meta["token_usage"]
                                if isinstance(token_usage, dict):
                                    usage_info["input_tokens"] = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0) or 0
                                    usage_info["output_tokens"] = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0) or 0
                                    usage_info["total_tokens"] = token_usage.get("total_tokens", 0) or (usage_info["input_tokens"] + usage_info["output_tokens"])
                                    print(f"[DEBUG] Token usage (token_usage): input={usage_info['input_tokens']}, output={usage_info['output_tokens']}, total={usage_info['total_tokens']}")
                            
                            # Source 3: response_metadata.usage (some providers)
                            if "usage" in resp_meta and usage_info["total_tokens"] == 0:
                                usage = resp_meta["usage"]
                                if isinstance(usage, dict):
                                    usage_info["input_tokens"] = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
                                    usage_info["output_tokens"] = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
                                    usage_info["total_tokens"] = usage.get("total_tokens", 0) or (usage_info["input_tokens"] + usage_info["output_tokens"])
                                    print(f"[DEBUG] Token usage (usage): input={usage_info['input_tokens']}, output={usage_info['output_tokens']}, total={usage_info['total_tokens']}")
                        
                        # Handle tool calls
                        if output and hasattr(output, "tool_calls") and output.tool_calls:
                            for tool_call in output.tool_calls:
                                tool_name = tool_call.get('name', 'unknown') if isinstance(tool_call, dict) else getattr(tool_call, 'name', 'unknown')
                                tool_args = tool_call.get('args', {}) if isinstance(tool_call, dict) else getattr(tool_call, 'args', {})
                                collected_tool_calls.append({
                                    "name": tool_name,
                                    "args": tool_args,
                                    "result": None  # Will be filled by on_tool_end
                                })
                                await websocket.send_json({
                                    "type": "tool_call",
                                    "tool": tool_name,
                                    "seq": seq
                                })
                                seq += 1
                    
                    elif event_type == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        tool_output = event.get("data", {}).get("output", "")
                        
                        # Update the collected tool call with result
                        for tc in collected_tool_calls:
                            if tc["name"] == tool_name and tc["result"] is None:
                                tc["result"] = str(tool_output)[:500]  # Truncate large results
                                break
                        
                        await websocket.send_json({
                            "type": "tool_result",
                            "tool": tool_name,
                            "seq": seq
                        })
                        seq += 1
                    
                    elif event_type == "on_chain_end":
                        # Debug: log all chain_end events
                        print(f"[DEBUG] on_chain_end: agent={agent_name}, final_sent={final_sent}")
                        
                        if agent_name == "chat" and not final_sent:
                            out = event.get("data", {}).get("output")
                            if out is None:
                                continue
                            
                            msgs = out.get("messages") if isinstance(out, dict) else out if isinstance(out, list) else []
                            
                            for m in reversed(msgs):
                                content = getattr(m, "content", None)
                                has_tool_calls = hasattr(m, "tool_calls") and m.tool_calls
                                
                                if content and not has_tool_calls:
                                    final_sent = True
                                    # Use the final message content (may be same as streamed)
                                    final_content = content if content else streamed_content
                                    
                                    if final_content and not assistant_message_saved:
                                        assistant_message_saved = True
                                        latency_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
                                        
                                        try:
                                            await _persist_message_to_db(
                                                thread_id, 
                                                "assistant", 
                                                final_content,
                                                input_tokens=usage_info["input_tokens"] or None,
                                                output_tokens=usage_info["output_tokens"] or None,
                                                total_tokens=usage_info["total_tokens"] or None,
                                                tool_calls=collected_tool_calls if collected_tool_calls else None,
                                                model=model_name,
                                                metadata={"latency_ms": latency_ms}
                                            )
                                            # Cache with full metadata
                                            cache_message = {
                                                "role": "assistant",
                                                "content": final_content,
                                                "input_tokens": usage_info["input_tokens"] or None,
                                                "output_tokens": usage_info["output_tokens"] or None,
                                                "total_tokens": usage_info["total_tokens"] or None,
                                                "tool_calls": collected_tool_calls if collected_tool_calls else None,
                                                "model": model_name,
                                                "latency_ms": latency_ms
                                            }
                                            await cache_append_message(thread_id, cache_message)
                                            print(f"✅ Saved assistant message to DB for thread {thread_id[:8]}... (tokens: {usage_info['total_tokens']}, tools: {len(collected_tool_calls)})")
                                        except Exception as e:
                                            print(f"Error persisting AI message: {e}")
                                    
                                    # Only send if different from what we already streamed
                                    if content != streamed_content:
                                        await websocket.send_json({
                                            "type": "stream",
                                            "content": content,
                                            "agent": agent_name,
                                            "seq": seq
                                        })
                                        seq += 1
                                    break
                
                # Fallback: If we streamed content but never got a final chain_end event
                if streamed_content and not assistant_message_saved:
                    latency_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
                    try:
                        await _persist_message_to_db(
                            thread_id, 
                            "assistant", 
                            streamed_content,
                            input_tokens=usage_info["input_tokens"] or None,
                            output_tokens=usage_info["output_tokens"] or None,
                            total_tokens=usage_info["total_tokens"] or None,
                            tool_calls=collected_tool_calls if collected_tool_calls else None,
                            model=model_name,
                            metadata={"latency_ms": latency_ms}
                        )
                        cache_message = {
                            "role": "assistant",
                            "content": streamed_content,
                            "input_tokens": usage_info["input_tokens"] or None,
                            "output_tokens": usage_info["output_tokens"] or None,
                            "total_tokens": usage_info["total_tokens"] or None,
                            "tool_calls": collected_tool_calls if collected_tool_calls else None,
                            "model": model_name,
                            "latency_ms": latency_ms
                        }
                        await cache_append_message(thread_id, cache_message)
                        print(f"✅ Saved streamed assistant message to DB for thread {thread_id[:8]}... (tokens: {usage_info['total_tokens']}, tools: {len(collected_tool_calls)})")
                    except Exception as e:
                        print(f"Error persisting streamed AI message: {e}")
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                await websocket.send_json({"type": "error", "error": str(e)})
            
            # Send end event
            await websocket.send_json({"type": "end"})
            
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
