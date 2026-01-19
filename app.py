"""
L&T IPMS Conversational API
FastAPI application with LangGraph agent, Redis caching, and PostgreSQL persistence
"""

import uuid
import json
import base64
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import redis.asyncio as redis_async
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import settings
from db import get_prisma, close_prisma
from cache import get_redis_cache
from agent import create_agent, create_checkpointer
from agent.graph import run_conversation, get_conversation_history
from agent.streaming import stream_conversation, subscribe_to_channel
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
    
    # Initialize Redis cache
    cache = await get_redis_cache()
    print("✅ Redis cache connected")
    
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
    cache_instance = await get_redis_cache()
    await cache_instance.close()
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


@app.get("/api/projects", tags=["Projects"])
async def get_projects():
    """
    Get list of projects from SraTable with date range.
    """
    prisma = await get_prisma()
    
    try:
        # Get distinct projects using Prisma ORM
        all_projects = await prisma.sratable.find_many(
            distinct=["projectId", "projectName"],
            order={"projectName": "asc"}
        )
        
        # Get date range
        date_stats = await prisma.sratable.find_first(
            order={"date": "asc"}
        )
        date_stats_max = await prisma.sratable.find_first(
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
            project_data = await prisma.sratable.find_first(
                where={"projectId": request.project_id}
            )
            date_stats = await prisma.sratable.find_first(
                where={"projectId": request.project_id},
                order={"date": "asc"}
            )
            date_stats_max = await prisma.sratable.find_first(
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
    
    Returns a stream of events:
    - init: Thread ID
    - stream: Incremental content chunks
    - tool_call: Tool invocation
    - tool_result: Tool output  
    - end: Stream finished
    """
    global _agent
    
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    # Generate thread_id if not provided
    thread_id = request.thread_id or str(uuid.uuid4())
    
    # Get project context if project_id is provided
    project_context = None
    if request.project_id:
        prisma = await get_prisma()
        try:
            project_data = await prisma.sratable.find_first(
                where={"projectId": request.project_id}
            )
            date_stats = await prisma.sratable.find_first(
                where={"projectId": request.project_id},
                order={"date": "asc"}
            )
            date_stats_max = await prisma.sratable.find_first(
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
        """Generate SSE events directly from LangGraph astream_events."""
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        
        # Persist User Message
        try:
            await _persist_message_to_db(thread_id, "user", request.message)
        except Exception as e:
            print(f"Error persisting user message: {e}")

        # Yield initial event with thread_id
        yield f"data: {json.dumps({'type': 'init', 'thread_id': thread_id})}\n\n"
        
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {
            "messages": [HumanMessage(content=enhanced_message)],
            "thread_id": thread_id
        }
        
        seq = 0
        streamed_content = ""  # Accumulate streamed chunks
        final_sent = False  # Only send one final response
        
        try:
            # Stream events directly from LangGraph
            async for event in _agent.astream_events(initial_state, version="v2", config=config):
                event_type = event.get("event", "")
                meta = event.get("metadata", {}) or {}
                agent_name = meta.get("langgraph_node") or "agent"
                
                # Debug: print event type
                print(f"[DEBUG] Event: {event_type}, Agent: {agent_name}")
                
                # Stream content chunks from LLM (when streaming=True on LLM)
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, 'content') and chunk.content:
                        streamed_content += chunk.content
                        yield f"data: {json.dumps({'type': 'stream', 'content': chunk.content, 'agent': agent_name, 'seq': seq})}\n\n"
                        seq += 1
                
                # Chat model finished - only check for tool calls here
                elif event_type == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if output and hasattr(output, "tool_calls") and output.tool_calls:
                        print(f"[DEBUG] Tool calls: {output.tool_calls}")
                        for tool_call in output.tool_calls:
                            if isinstance(tool_call, dict):
                                tool_name = tool_call.get('name', 'unknown')
                            else:
                                tool_name = getattr(tool_call, 'name', 'unknown')
                            yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'seq': seq})}\n\n"
                            seq += 1
                
                # Tool completed
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'seq': seq})}\n\n"
                    seq += 1
                
                # Chain/node completed - get final content from chat node
                elif event_type == "on_chain_end" and agent_name == "chat" and not final_sent:
                    out = event.get("data", {}).get("output")
                    
                    # Handle different output types
                    if out is None:
                        continue
                    
                    msgs = []
                    if isinstance(out, dict):
                        msgs = out.get("messages") or []
                    elif isinstance(out, list):
                        msgs = out
                    # If out is a string or other type, skip
                    
                    # Find the final AI message with content
                    for m in reversed(msgs):
                        content = getattr(m, "content", None) if hasattr(m, "content") else None
                        has_tool_calls = hasattr(m, "tool_calls") and m.tool_calls
                        
                        # Only use message if it has content and no tool calls
                        if content and not has_tool_calls:
                            # Check if we already streamed this content
                            if content != streamed_content:
                                final_sent = True
                                
                                # Persist AI Message (Final Answer)
                                try:
                                    await _persist_message_to_db(thread_id, "assistant", content)
                                except Exception as e:
                                    print(f"Error persisting AI message: {e}")
                                
                                yield f"data: {json.dumps({'type': 'stream', 'content': content, 'agent': agent_name, 'seq': seq})}\n\n"
                                seq += 1
                            break

        
        except Exception as e:
            import traceback
            print(f"[DEBUG] Exception: {e}")
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        # Signal end of stream
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
    
    Checks: Redis cache -> LangGraph checkpointer -> Prisma messages
    """
    global _agent
    
    # Try cache first
    cache = await get_redis_cache()
    cached_messages = await cache.get_conversation_cache(thread_id)
    
    if cached_messages:
        return ConversationHistory(
            thread_id=thread_id,
            messages=[MessageSchema(**m) for m in cached_messages],
        )
    
    # Try LangGraph checkpointer
    if _agent is not None:
        try:
            history = await get_conversation_history(_agent, thread_id)
            if history:
                # Cache for next time
                await cache.set_conversation_cache(thread_id, history)
                return ConversationHistory(
                    thread_id=thread_id,
                    messages=[MessageSchema(**m) for m in history],
                )
        except Exception as e:
            print(f"Checkpointer error: {e}")
    
    # Fall back to Prisma messages table
    try:
        prisma = await get_prisma()
        conversation = await prisma.conversation.find_unique(
            where={"threadId": thread_id},
            include={"messages": {"order": {"createdAt": "asc"}}}
        )
        
        if conversation and conversation.messages:
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.createdAt.isoformat() if msg.createdAt else None
                }
                for msg in conversation.messages
            ]
            
            # Cache for next time
            await cache.set_conversation_cache(thread_id, messages)
            
            return ConversationHistory(
                thread_id=thread_id,
                messages=[MessageSchema(**m) for m in messages],
                created_at=conversation.createdAt
            )
        
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation: {str(e)}")


@app.delete("/conversations/{thread_id}", tags=["Conversations"])
async def delete_conversation(thread_id: str):
    """
    Delete a conversation from cache and database.
    """
    # Clear from cache
    cache = await get_redis_cache()
    await cache.invalidate_cache(thread_id)
    
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


async def _persist_message_to_db(thread_id: str, role: str, content: str):
    """
    Persist a message to the Prisma database.
    Creates the conversation if it doesn't exist.
    
    Note: The main conversation state is also stored by LangGraph's PostgreSQL 
    checkpointer. This Prisma storage is for additional metadata and custom queries.
    """
    from datetime import datetime
    
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
        # Update the conversation's updated_at timestamp using Python datetime
        await prisma.conversation.update(
            where={"id": conversation.id},
            data={"updatedAt": datetime.utcnow()}
        )
    
    # Create the message
    await prisma.message.create(
        data={
            "conversationId": conversation.id,
            "role": role,
            "content": content,
        }
    )


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat streaming.
    
    Client sends: {"message": "...", "thread_id": "..." (optional), "project_id": "..." (optional)}
    Server sends: StreamEvent JSON objects
    """
    global _agent
    
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")
            thread_id = data.get("thread_id") or str(uuid.uuid4())
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
                    project_data = await prisma.sratable.find_first(where={"projectId": project_id})
                    date_stats = await prisma.sratable.find_first(where={"projectId": project_id}, order={"date": "asc"})
                    date_stats_max = await prisma.sratable.find_first(where={"projectId": project_id}, order={"date": "desc"})
                    
                    if project_data:
                        date_from = date_stats.date.strftime("%Y-%m-%d") if date_stats else "N/A"
                        date_to = date_stats_max.date.strftime("%Y-%m-%d") if date_stats_max else "N/A"
                        project_context = {
                            "project_id": project_id,
                            "project_name": project_data.projectName,
                            "date_range": f"{date_from} to {date_to}",
                        }
                except Exception as e:
                    print(f"Error getting project context: {e}")
            
            # Build enhanced message
            enhanced_message = message
            if project_context:
                enhanced_message += (
                    f"\n\n[CONTEXT]\nSelected Project: {project_context.get('project_name', 'Unknown')} "
                    f"({project_context.get('project_id', 'N/A')})\n"
                    f"Available Date Range: {project_context.get('date_range', 'N/A')}\n[/CONTEXT]"
                )
            
            # Persist user message
            try:
                await _persist_message_to_db(thread_id, "user", message)
            except Exception as e:
                print(f"Error persisting user message: {e}")
            
            # Send init event
            await websocket.send_json({"type": "init", "thread_id": thread_id})
            
            # Stream response
            from langchain_core.messages import HumanMessage
            config = {"configurable": {"thread_id": thread_id}}
            initial_state = {"messages": [HumanMessage(content=enhanced_message)], "thread_id": thread_id}
            
            accumulated_content = ""
            seq = 0
            
            try:
                async for event in _agent.astream_events(initial_state, version="v2", config=config):
                    event_type = event.get("event", "")
                    
                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, 'content') and chunk.content:
                            accumulated_content += chunk.content
                            await websocket.send_json({
                                "type": "stream",
                                "content": chunk.content,
                                "seq": seq
                            })
                            seq += 1
                    
                    elif event_type == "on_chat_model_end":
                        output = event.get("data", {}).get("output")
                        if output:
                            if hasattr(output, "tool_calls") and output.tool_calls:
                                for tool_call in output.tool_calls:
                                    tool_name = tool_call.get('name', 'unknown') if isinstance(tool_call, dict) else getattr(tool_call, 'name', 'unknown')
                                    await websocket.send_json({"type": "tool_call", "tool": tool_name, "seq": seq})
                                    seq += 1
                            elif hasattr(output, 'content') and output.content:
                                try:
                                    await _persist_message_to_db(thread_id, "assistant", output.content)
                                except Exception as e:
                                    print(f"Error persisting AI message: {e}")
                    
                    elif event_type == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        await websocket.send_json({"type": "tool_result", "tool": tool_name, "seq": seq})
                        seq += 1
                
            except Exception as e:
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
