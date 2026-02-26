import uuid, json, asyncio, httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from auth.dependencies import get_current_user
from redis_client import (
    append_message, get_redis_client,
    publish_stream_event, subscribe_stream,
)
from schemas import FeedbackRequest, EditMessageRequest, ChatRequest, ChatResponse, HealthResponse
from langchain_core.messages import HumanMessage, AIMessage
from config import settings
from db import get_prisma

router = APIRouter(tags=["Chat"])
_agent = None


def set_agent(agent):
    """Set the global agent instance for this router"""
    global _agent
    _agent = agent


# ─── Helpers ────────────────────────────────────────────────────────────────────

async def _persist_message_to_db(
    thread_id: str,
    role: str,
    content: str,
    *,
    branch_index: int = None,
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
    """
    prisma = await get_prisma()

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
        await prisma.conversation.update(
            where={"id": conversation.id},
            data={"updatedAt": datetime.utcnow()}
        )

    # Compute next positionIndex for this conversation
    existing = await prisma.message.find_many(
        where={"conversationId": conversation.id},
        order={"createdAt": "desc"},
        take=1,
    )
    if existing and existing[0].positionIndex is not None:
        next_position = existing[0].positionIndex + 1
    else:
        # Count existing messages as fallback
        count = await prisma.message.count(
            where={"conversationId": conversation.id}
        )
        next_position = count

    # Inherit branch from the currently active previous position when not explicitly provided.
    # This keeps regenerated assistant turns and subsequent turns on the selected user branch.
    resolved_branch_index = branch_index
    if resolved_branch_index is None:
        resolved_branch_index = 0
        if next_position > 0:
            prev_active = await prisma.message.find_first(
                where={
                    "conversationId": conversation.id,
                    "positionIndex": next_position - 1,
                    "activeBranch": True,
                },
                order={"createdAt": "desc"},
            )
            if prev_active and prev_active.branchIndex is not None:
                resolved_branch_index = prev_active.branchIndex

    message_data = {
        "conversationId": conversation.id,
        "role": role,
        "content": content,
        "positionIndex": next_position,
        "branchIndex": resolved_branch_index,
        "activeBranch": True,
    }

    if input_tokens is not None:
        message_data["inputTokens"] = input_tokens
    if output_tokens is not None:
        message_data["outputTokens"] = output_tokens
    if total_tokens is not None:
        message_data["totalTokens"] = total_tokens
    if tool_calls is not None:
        message_data["toolCalls"] = json.dumps(tool_calls) if isinstance(tool_calls, list) else tool_calls
    if tool_name is not None:
        message_data["toolName"] = tool_name
    if model is not None:
        message_data["model"] = model
    if metadata is not None:
        message_data["metadata"] = json.dumps(metadata) if isinstance(metadata, dict) else metadata

    created = await prisma.message.create(data=message_data)
    return created.id


# ─── Shared Agent Runner (Publisher) ────────────────────────────────────────────

async def _run_agent_and_publish(
    thread_id: str,
    enhanced_message: str,
    *,
    skip_user_persist: bool = False,
    original_user_message: str | None = None,
    ready_event: asyncio.Event | None = None,
):
    """
    Run the LangGraph agent and publish every streaming event to Redis pub/sub.
    
    This is the SINGLE source of truth for agent streaming logic:
    - Runs astream_events on the agent
    - Handles <think> tag filtering
    - Handles tool call/result tracking
    - Publishes each event to Redis channel  stream:{thread_id}
    - Persists final assistant message to DB + Redis cache
    
    Args:
        thread_id: conversation thread ID
        enhanced_message: user message with project context appended
        skip_user_persist: if True, skip persisting user message (edit flow)
        original_user_message: raw user message (without context), for DB persistence
    """
    global _agent

    # Wait for subscriber to be ready before we start publishing
    if ready_event is not None:
        await ready_event.wait()
        print(f"[PUBSUB] Publisher got ready signal for {thread_id[:8]}...")

    if _agent is None:
        await publish_stream_event(thread_id, {"type": "error", "error": "Agent not initialized"})
        await publish_stream_event(thread_id, {"type": "end"})
        return

    # Persist user message
    user_msg = original_user_message or enhanced_message
    if not skip_user_persist:
        try:
            await _persist_message_to_db(thread_id, "user", user_msg)
        except Exception as e:
            print(f"Error persisting user message: {e}")
        try:
            await append_message(thread_id, {"role": "user", "content": user_msg})
        except Exception as e:
            print(f"Error caching user message: {e}")

    # Run agent
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "messages": [HumanMessage(content=enhanced_message)],
        "thread_id": thread_id
    }

    seq = 0
    streamed_content = ""
    final_sent = False
    assistant_message_saved = False
    in_tool_loop = False
    insight_started = False  # Track if we've emitted insight_start for this stream
    tool_output_content = ""  # Capture tool result content for combining with insight

    # Metadata tracking
    collected_tool_calls = []
    usage_info = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    model_name = None
    start_time = asyncio.get_event_loop().time()

    # Think-tag state
    in_thinking = False
    thinking_content = ""

    try:
        async for event in _agent.astream_events(initial_state, version="v2", config=config):
            event_type = event.get("event", "")
            meta = event.get("metadata", {}) or {}
            agent_name = meta.get("langgraph_node") or "agent"

            # ── LLM streaming chunks ──
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, 'content') and chunk.content:
                    if not in_tool_loop:
                        # If streaming from insights node, emit insight_start once
                        if agent_name == "insights" and not insight_started:
                            insight_started = True
                            await publish_stream_event(thread_id, {
                                "type": "insight_start",
                                "seq": seq
                            })
                            seq += 1
                        content = chunk.content

                        # Handle <think> tags
                        while content:
                            if in_thinking:
                                end_idx = content.find("</think>")
                                if end_idx != -1:
                                    thinking_content += content[:end_idx]
                                    in_thinking = False
                                    if thinking_content.strip():
                                        await publish_stream_event(thread_id, {
                                            "type": "thinking",
                                            "content": thinking_content.strip(),
                                            "seq": seq
                                        })
                                        seq += 1
                                    thinking_content = ""
                                    content = content[end_idx + 8:]
                                else:
                                    thinking_content += content
                                    content = ""
                            else:
                                start_idx = content.find("<think>")
                                if start_idx != -1:
                                    before = content[:start_idx]
                                    if before:
                                        streamed_content += before
                                        await publish_stream_event(thread_id, {
                                            "type": "stream",
                                            "content": before,
                                            "agent": agent_name,
                                            "seq": seq
                                        })
                                        seq += 1
                                    in_thinking = True
                                    content = content[start_idx + 7:]
                                else:
                                    streamed_content += content
                                    await publish_stream_event(thread_id, {
                                        "type": "stream",
                                        "content": content,
                                        "agent": agent_name,
                                        "seq": seq
                                    })
                                    seq += 1
                                    content = ""

            # ── LLM generation complete ──
            elif event_type == "on_chat_model_end":
                output = event.get("data", {}).get("output")

                # Extract usage info
                if output and hasattr(output, "usage_metadata") and output.usage_metadata:
                    usage = output.usage_metadata
                    if isinstance(usage, dict):
                        usage_info["input_tokens"] += usage.get("input_tokens", 0) or 0
                        usage_info["output_tokens"] += usage.get("output_tokens", 0) or 0
                        usage_info["total_tokens"] += usage.get("total_tokens", 0) or 0
                    else:
                        usage_info["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
                        usage_info["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
                        usage_info["total_tokens"] += getattr(usage, "total_tokens", 0) or 0

                if output and hasattr(output, "response_metadata") and output.response_metadata:
                    resp_meta = output.response_metadata
                    if "model_name" in resp_meta:
                        model_name = resp_meta["model_name"]
                    elif "model" in resp_meta:
                        model_name = resp_meta["model"]

                    if "token_usage" in resp_meta and usage_info["total_tokens"] == 0:
                        token_usage = resp_meta["token_usage"]
                        if isinstance(token_usage, dict):
                            usage_info["input_tokens"] = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0) or 0
                            usage_info["output_tokens"] = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0) or 0
                            usage_info["total_tokens"] = token_usage.get("total_tokens", 0) or (usage_info["input_tokens"] + usage_info["output_tokens"])

                    if "usage" in resp_meta and usage_info["total_tokens"] == 0:
                        usage = resp_meta["usage"]
                        if isinstance(usage, dict):
                            usage_info["input_tokens"] = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
                            usage_info["output_tokens"] = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
                            usage_info["total_tokens"] = usage.get("total_tokens", 0) or (usage_info["input_tokens"] + usage_info["output_tokens"])

                # Handle tool calls
                if output and hasattr(output, "tool_calls") and output.tool_calls:
                    in_tool_loop = True
                    streamed_content = ""
                    for tool_call in output.tool_calls:
                        tool_name_val = tool_call.get('name', 'unknown') if isinstance(tool_call, dict) else getattr(tool_call, 'name', 'unknown')
                        tool_args = tool_call.get('args', {}) if isinstance(tool_call, dict) else getattr(tool_call, 'args', {})
                        collected_tool_calls.append({
                            "name": tool_name_val,
                            "args": tool_args,
                            "result": None
                        })
                        await publish_stream_event(thread_id, {
                            "type": "tool_call",
                            "tool": tool_name_val,
                            "seq": seq
                        })
                        seq += 1

            # ── Tool execution complete ──
            elif event_type == "on_tool_end":
                tool_name_val = event.get("name", "unknown")
                raw_output = event.get("data", {}).get("output", "")

                # Extract .content from ToolMessage objects
                if hasattr(raw_output, 'content'):
                    tool_output = raw_output.content
                elif isinstance(raw_output, dict):
                    tool_output = raw_output.get('content', str(raw_output))
                else:
                    tool_output = str(raw_output)

                print(f"[TOOL_END] tool={tool_name_val}, output_type={type(raw_output).__name__}, content_len={len(tool_output)}")

                for tc in collected_tool_calls:
                    if tc["name"] == tool_name_val and tc["result"] is None:
                        tc["result"] = tool_output[:500]
                        break

                in_tool_loop = False
                tool_output_content = tool_output  # Save for combining with insight
                await publish_stream_event(thread_id, {
                    "type": "tool_result",
                    "tool": tool_name_val,
                    "content": tool_output,
                    "seq": seq
                })
                seq += 1

            # ── Chain end (final output) ──
            elif event_type == "on_chain_end":
                if agent_name in ("SR-AGENT", "insights") and not final_sent:
                    out = event.get("data", {}).get("output")
                    if out is None:
                        continue

                    msgs = out.get("messages") if isinstance(out, dict) else out if isinstance(out, list) else []

                    for m in reversed(msgs):
                        content = getattr(m, "content", None)
                        has_tool_calls = hasattr(m, "tool_calls") and m.tool_calls

                        if content and not has_tool_calls:
                            final_sent = True
                            final_content = content or streamed_content

                            # Prepend tool output to final content for DB persistence
                            save_content = final_content
                            if tool_output_content:
                                save_content = tool_output_content + "\n\n<!-- INSIGHT -->\n\n" + final_content

                            # Persist to DB
                            if save_content and not assistant_message_saved:
                                assistant_message_saved = True
                                latency_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                                try:
                                    await _persist_message_to_db(
                                        thread_id,
                                        "assistant",
                                        save_content,
                                        input_tokens=usage_info["input_tokens"] or None,
                                        output_tokens=usage_info["output_tokens"] or None,
                                        total_tokens=usage_info["total_tokens"] or None,
                                        tool_calls=collected_tool_calls if collected_tool_calls else None,
                                        model=model_name,
                                        metadata={"latency_ms": latency_ms}
                                    )
                                    cache_message = {
                                        "role": "assistant",
                                        "content": save_content,
                                        "input_tokens": usage_info["input_tokens"] or None,
                                        "output_tokens": usage_info["output_tokens"] or None,
                                        "total_tokens": usage_info["total_tokens"] or None,
                                        "tool_calls": collected_tool_calls if collected_tool_calls else None,
                                        "model": model_name,
                                        "latency_ms": latency_ms
                                    }
                                    await append_message(thread_id, cache_message)
                                    print(f"✅ Saved assistant message for thread {thread_id[:8]}... (tokens: {usage_info['total_tokens']}, tools: {len(collected_tool_calls)})")
                                except Exception as e:
                                    print(f"Error persisting AI message: {e}")

                            # If content was NOT streamed (short-circuited tool output),
                            # publish it now so subscriber sees it
                            if not streamed_content and final_content:
                                print(f"[PUBSUB] Publishing short-circuited content, len={len(final_content)}")
                                await publish_stream_event(thread_id, {
                                    "type": "stream",
                                    "content": final_content,
                                    "agent": agent_name,
                                    "seq": seq
                                })
                                seq += 1
                                streamed_content = final_content

                            break

        # Fallback persistence
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
                await append_message(thread_id, {
                    "role": "assistant",
                    "content": streamed_content,
                    "input_tokens": usage_info["input_tokens"] or None,
                    "output_tokens": usage_info["output_tokens"] or None,
                    "total_tokens": usage_info["total_tokens"] or None,
                    "tool_calls": collected_tool_calls if collected_tool_calls else None,
                    "model": model_name,
                    "latency_ms": latency_ms
                })
                print(f"✅ Saved fallback assistant message for thread {thread_id[:8]}...")
            except Exception as e:
                print(f"Error persisting fallback AI message: {e}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        await publish_stream_event(thread_id, {"type": "error", "error": str(e)})

    # Always publish end event
    await publish_stream_event(thread_id, {"type": "end"})


# ─── Non-streaming chat endpoint ────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    """
    Send a message and receive a response from the AI assistant.
    Non-streaming endpoint.
    """
    global _agent
    from agent import run_conversation, get_conversation_history

    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    thread_id = request.thread_id or str(uuid.uuid4())

    # Get project context
    project_context = None
    if request.project_key:
        prisma = await get_prisma()
        try:
            project_data = await prisma.tbl01projectsummary.find_first(
                where={"projectKey": int(request.project_key)}
            )
            if project_data:
                project_context = {
                    "project_key": request.project_key,
                    "project_name": project_data.projectName,
                    "project_location": project_data.projectLocation,
                    "start_date": project_data.baselineStartDate,
                    "end_date": project_data.contractualCompletionDate
                }
        except Exception as e:
            print(f"Error getting project context: {e}")

    try:
        response = await run_conversation(_agent, request.message, thread_id, project_context)
        history = await get_conversation_history(_agent, thread_id)
        message_count = len(history)

        await _persist_message_to_db(thread_id, "user", request.message)
        await _persist_message_to_db(thread_id, "assistant", response)

        return ChatResponse(
            response=response,
            thread_id=thread_id,
            message_count=message_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


# ─── Message Feedback ───────────────────────────────────────────────────────────

@router.post(settings.API_SLUG + "/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: str,
    feedback: FeedbackRequest,
    current_user: dict = Depends(get_current_user)
):
    """Submit feedback (thumbs up/down) for an assistant message."""
    prisma = await get_prisma()

    message = await prisma.message.find_unique(where={"id": message_id})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Can only provide feedback on assistant messages")

    await prisma.message.update(
        where={"id": message_id},
        data={
            "feedback": feedback.feedback,
            "feedbackNote": feedback.note
        }
    )
    return {"status": "ok", "message_id": message_id}


# ─── Message Edit ────────────────────────────────────────────────────────────────

@router.put(settings.API_SLUG + "/messages/{message_id}/edit")
async def edit_message(
    message_id: str,
    request: EditMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Edit a user message — creates a new branch at the same position.
    Old versions are preserved (activeBranch=false) for branch navigation.
    Regeneration streams via the active WebSocket (Redis pub/sub).
    Returns a JSON ack immediately.
    """
    prisma = await get_prisma()

    message = await prisma.message.find_unique(
        where={"id": message_id},
        include={"conversation": True}
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "user":
        raise HTTPException(status_code=400, detail="Can only edit user messages")

    thread_id = message.conversation.threadId
    position = message.positionIndex

    # Backfill positionIndex for pre-migration messages
    if position is None:
        all_msgs = await prisma.message.find_many(
            where={"conversationId": message.conversationId},
            order={"createdAt": "asc"},
        )
        for idx, m in enumerate(all_msgs):
            await prisma.message.update(
                where={"id": m.id},
                data={"positionIndex": idx, "branchIndex": 0, "activeBranch": True}
            )
            if m.id == message_id:
                position = idx
        print(f"[BRANCH] Backfilled positionIndex for {len(all_msgs)} messages in thread {thread_id[:8]}...")

    # 1. Deactivate old branch: mark this message + all subsequent active messages
    await prisma.message.update_many(
        where={
            "conversationId": message.conversationId,
            "positionIndex": {"gte": position},
            "activeBranch": True,
        },
        data={"activeBranch": False}
    )

    # 2. Compute next branchIndex at this position
    max_branch = await prisma.message.find_many(
        where={
            "conversationId": message.conversationId,
            "positionIndex": position,
        },
        order={"branchIndex": "desc"},
        take=1,
    )
    next_branch = (max_branch[0].branchIndex + 1) if max_branch else 1

    # 3. Create new user message at same position with new branch
    new_msg = await prisma.message.create(
        data={
            "conversationId": message.conversationId,
            "role": "user",
            "content": request.content,
            "positionIndex": position,
            "branchIndex": next_branch,
            "activeBranch": True,
            "editedFrom": message_id,
        }
    )
    print(f"[BRANCH] Created branch {next_branch} at position {position} for thread {thread_id[:8]}...")

    # 4. Return ack — frontend will send WebSocket message to trigger regeneration
    return {"status": "ok", "thread_id": thread_id}


# ─── Branch Switching ────────────────────────────────────────────────────────────

@router.put(settings.API_SLUG + "/messages/{message_id}/switch-branch/{branch_index}")
async def switch_branch(
    message_id: str,
    branch_index: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Switch the active branch at a message's position.
    Cascades to subsequent positions — deactivates all, then reactivates
    the target branch and its timeline of subsequent messages.
    """
    prisma = await get_prisma()

    message = await prisma.message.find_unique(
        where={"id": message_id},
        include={"conversation": True}
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    conv_id = message.conversationId
    position = message.positionIndex
    thread_id = message.conversation.threadId

    # 1. Deactivate ALL messages at this position and later
    await prisma.message.update_many(
        where={
            "conversationId": conv_id,
            "positionIndex": {"gte": position},
            "activeBranch": True,
        },
        data={"activeBranch": False}
    )

    # 2. Activate the target branch at this position
    target = await prisma.message.find_first(
        where={
            "conversationId": conv_id,
            "positionIndex": position,
            "branchIndex": branch_index,
        }
    )
    if not target:
        raise HTTPException(status_code=404, detail="Branch not found")

    await prisma.message.update(
        where={"id": target.id},
        data={"activeBranch": True}
    )

    # 3. Cascade: find and activate subsequent messages in this branch's timeline
    # Walk forward from position+1, activating messages that share this branch timeline
    current_pos = position + 1
    current_ref_id = target.id

    while True:
        # Find the message at next position that was created after the current ref
        # (i.e., the assistant response to this user message, or vice versa)
        next_msg = await prisma.message.find_first(
            where={
                "conversationId": conv_id,
                "positionIndex": current_pos,
                "branchIndex": branch_index,
            }
        )
        # Fallback: try branchIndex 0 (original timeline) if exact branch not found
        if not next_msg:
            next_msg = await prisma.message.find_first(
                where={
                    "conversationId": conv_id,
                    "positionIndex": current_pos,
                    "branchIndex": 0,
                }
            )
        if not next_msg:
            break  # No more messages in this timeline

        await prisma.message.update(
            where={"id": next_msg.id},
            data={"activeBranch": True}
        )
        current_ref_id = next_msg.id
        current_pos += 1

    print(f"[BRANCH] Switched to branch {branch_index} at position {position} for thread {thread_id[:8]}...")

    # 4. Return refreshed active messages
    from redis_client import invalidate_cache
    await invalidate_cache(thread_id)

    return {"status": "ok", "thread_id": thread_id}



@router.websocket("/ws/chat/{thread_id}")
async def websocket_chat(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for real-time chat streaming.
    Uses Redis pub/sub: agent publishes events, WebSocket subscribes and forwards.
    
    Supports two action types:
    - Chat: {"message": "...", "project_key": "..." (optional)}
    - Edit: {"action": "edit", "message": "...", "project_key": "..." (optional)}
    
    Path parameter: thread_id - use "new" for a new conversation
    Server sends: StreamEvent JSON objects
    """
    prisma = await get_prisma()

    global _agent

    if thread_id == "new":
        thread_id = str(uuid.uuid4())

    await websocket.accept()
    await websocket.send_json({"type": "init", "thread_id": thread_id})
    await asyncio.sleep(0)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")
            project_key = data.get("project_key")
            action = data.get("action", "chat")  # "chat" or "edit"

            if not message:
                await websocket.send_json({"type": "error", "error": "No message provided"})
                await asyncio.sleep(0)
                continue

            if _agent is None:
                await websocket.send_json({"type": "error", "error": "Agent not initialized"})
                await asyncio.sleep(0)
                continue

            # Build project context
            project_context = None
            if project_key:
                try:
                    project_data = await prisma.tbl01projectsummary.find_first(
                        where={"projectKey": int(project_key)}
                    )
                    if project_data:
                        project_context = {
                            "project_key": project_key,
                            "project_name": project_data.projectName,
                            "project_location": project_data.projectLocation,
                            "start_date": project_data.baselineStartDate,
                            "end_date": project_data.contractualCompletionDate
                        }
                except Exception as e:
                    print(f"Error getting project context: {e}")

            # Build enhanced message with project context
            if project_context:
                context_info = (
                    f"\n\n[CONTEXT]\n"
                    f"Selected Project: {project_context.get('project_name', 'Unknown')} ({project_context.get('project_location', 'N/A')})\n"
                    f"Project Start Date: {project_context.get('start_date', 'N/A')}\n"
                    f"Project End Date: {project_context.get('end_date', 'N/A')}\n"
                    f"When calling tools, use project_key='{project_context.get('project_key', '')}' to filter results.\n"
                    f"[/CONTEXT]"
                )
                enhanced_message = message + context_info
            else:
                enhanced_message = message

            # Determine whether to persist user message (skip for edits since PUT already did it)
            skip_user_persist = (action == "edit")

            # ── Synchronize publisher/subscriber ──
            ready_event = asyncio.Event()

            # ── PUBLISHER: Start agent in background task (waits for ready_event) ──
            asyncio.create_task(
                _run_agent_and_publish(
                    thread_id,
                    enhanced_message,
                    original_user_message=message,
                    skip_user_persist=skip_user_persist,
                    ready_event=ready_event,
                )
            )

            # ── SUBSCRIBER: Connect to Redis channel, then signal ready ──
            try:
                async for event in subscribe_stream(thread_id, ready_event=ready_event):
                    await websocket.send_json(event)
                    await asyncio.sleep(0)  # Yield control to flush buffer
            except WebSocketDisconnect:
                print(f"[WS] Client disconnected during stream for {thread_id[:8]}...")
                return
            except Exception as e:
                print(f"[WS] Error during subscribe: {e}")
                await websocket.send_json({"type": "error", "error": str(e)})
                await asyncio.sleep(0)

    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


# ─── Health Check ────────────────────────────────────────────────────────────────

@router.get(settings.API_SLUG + "/health", response_model=HealthResponse)
async def health_check():
    """Check the health status of all services."""
    try:
        redis_client = await get_redis_client()
        redis_ok = await redis_client.ping()
        redis_status = "connected" if redis_ok else "disconnected"
    except Exception as e:
        redis_status = f"error: {str(e)}"

    try:
        prisma = await get_prisma()
        await prisma.user.find_many(take=1)
        postgres_status = "connected"
    except Exception as e:
        postgres_status = f"error: {str(e)}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.BASE_URL}/health",
                timeout=5.0
            )
            llm_status = "connected" if response.status_code == 200 else f"status: {response.status_code}"
    except Exception as e:
        llm_status = f"error: {str(e)}"

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
