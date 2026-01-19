"""
Streaming module for LangGraph Agent
Handles event streaming and Redis pub/sub for real-time chat responses
"""

import json
import base64
import logging
from collections import defaultdict
from uuid import uuid4
from typing import Optional, AsyncIterator
import redis.asyncio as redis

from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

from config import settings

log = logging.getLogger(__name__)


def serialize_message_chunk(chunk) -> str:
    """Serialize an AI message chunk to string content."""
    if hasattr(chunk, 'content'):
        return chunk.content or ""
    elif isinstance(chunk, dict):
        return chunk.get('content', str(chunk))
    elif isinstance(chunk, str):
        return chunk
    return str(chunk)


async def stream_conversation(
    graph,
    redis_client,
    message: str,
    thread_id: str,
    project_context: Optional[dict] = None,
    channel: Optional[str] = None,
    is_new_conversation: bool = True
) -> str:
    """
    Stream a conversation with the agent using astream_events and Redis pub/sub.
    
    Args:
        graph: Compiled LangGraph agent
        redis_client: Redis client for pub/sub
        message: User message
        thread_id: Conversation thread ID
        project_context: Optional project context for filtering
        channel: Redis channel for pub/sub (auto-generated if not provided)
        is_new_conversation: Whether this is a new conversation or continuation
        
    Returns:
        Final response text (also streamed via Redis)
    """
    # Build user message with project context if provided
    if project_context:
        context_info = (
            f"\n\n[CONTEXT]\n"
            f"Selected Project: {project_context.get('project_name', 'Unknown')} ({project_context.get('project_id', 'N/A')})\n"
            f"Available Date Range: {project_context.get('date_range', 'N/A')}\n"
            f"If user asks about PEI or project status without specifying a date, ask them to specify "
            f"a date within the range {project_context.get('date_from', '')} to {project_context.get('date_to', '')}.\n"
            f"When calling tools, use project_id='{project_context.get('project_id', '')}' to filter results.\n"
            f"[/CONTEXT]"
        )
        enhanced_message = message + context_info
    else:
        enhanced_message = message

    # Setup channel and config
    channel = channel or f"chat:{thread_id}"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initial state
    initial_state = {
        "messages": [HumanMessage(content=enhanced_message)],
        "thread_id": thread_id
    }
    
    # Publish checkpoint/start info
    payload_start = {
        "type": "start",
        "thread_id": thread_id,
        "channel": channel
    }
    await redis_client.publish(channel, json.dumps(payload_start))
    log.info(f"Published start to {channel}")
    
    # Start streaming events
    events = graph.astream_events(initial_state, version="v2", config=config)
    
    seq = 0
    final_response = ""
    agent_buffers = defaultdict(str)
    
    try:
        async for event in events:
            event_type = event.get("event", "")
            meta = event.get("metadata", {}) or {}
            agent_name = meta.get("langgraph_node") or meta.get("node") or "unknown"
            
            # Handle streaming content from LLM
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    chunk_content = serialize_message_chunk(chunk)
                    if chunk_content:
                        agent_buffers[agent_name] += chunk_content
                        final_response = agent_buffers.get("chat", "") or agent_buffers.get("__end__", "")
                        
                        # Base64 encode for safe transport
                        safe_content = base64.b64encode(chunk_content.encode("utf-8")).decode("ascii")
                        
                        # Check if this is the final chunk
                        finish_reason = None
                        if hasattr(chunk, 'response_metadata'):
                            finish_reason = chunk.response_metadata.get("finish_reason")
                        
                        payload = {
                            "type": "stream",
                            "agent": agent_name,
                            "content": safe_content,
                            "seq": seq,
                            "is_final": finish_reason == "stop"
                        }
                        await redis_client.publish(channel, json.dumps(payload))
                        seq += 1
            
            # Handle tool calls starting
            elif event_type == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                if output and hasattr(output, "tool_calls") and output.tool_calls:
                    for tool_call in output.tool_calls:
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("args", {})
                        
                        payload = {
                            "type": "tool_call",
                            "tool": tool_name,
                            "args": tool_args,
                            "seq": seq
                        }
                        await redis_client.publish(channel, json.dumps(payload))
                        log.debug(f"Published tool_call for {tool_name}")
                        seq += 1
            
            # Handle tool results
            elif event_type == "on_tool_end":
                tool_name = event.get("name", "unknown")
                output = event.get("data", {}).get("output")
                
                # Serialize tool output
                if isinstance(output, ToolMessage):
                    tool_result = output.content
                elif isinstance(output, str):
                    tool_result = output
                else:
                    tool_result = str(output)
                
                # Truncate long results for pub/sub
                if len(tool_result) > 1000:
                    tool_result = tool_result[:1000] + "..."
                
                safe_result = base64.b64encode(tool_result.encode("utf-8")).decode("ascii")
                
                payload = {
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": safe_result,
                    "seq": seq
                }
                await redis_client.publish(channel, json.dumps(payload))
                log.debug(f"Published tool_result for {tool_name}")
                seq += 1
            
            # Handle chain end (final output)
            elif event_type == "on_chain_end":
                output = event.get("data", {}).get("output") or {}
                messages = output.get("messages") or []
                
                # Look for the final AI response
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        # Skip if it's just a tool call without content
                        if not getattr(msg, "tool_calls", None) or msg.content:
                            final_response = msg.content
                            break
            
            # Handle errors
            elif event_type in ("on_tool_error", "on_chat_model_error", "on_chain_error", "on_error"):
                err_info = event.get("data", {}).get("error", "Unknown error")
                
                payload = {
                    "type": "error",
                    "error": "An error occurred while processing. Please try again.",
                    "seq": seq
                }
                await redis_client.publish(channel, json.dumps(payload))
                log.error(f"Stream error: {err_info}")
                seq += 1
    
    except Exception as e:
        log.error(f"Stream exception: {e}")
        payload = {
            "type": "error",
            "error": "Stream interrupted. Please try again.",
            "seq": seq
        }
        await redis_client.publish(channel, json.dumps(payload))
    
    # Publish final response if we have it
    if final_response:
        safe_final = base64.b64encode(final_response.encode("utf-8")).decode("ascii")
        payload = {
            "type": "final",
            "content": safe_final,
            "seq": seq
        }
        await redis_client.publish(channel, json.dumps(payload))
        seq += 1
    
    # Signal end of stream
    payload_end = {"type": "end", "seq": seq}
    await redis_client.publish(channel, json.dumps(payload_end))
    log.info(f"Published end to {channel}")
    
    return final_response


async def subscribe_to_channel(
    redis_client,
    channel: str
) -> AsyncIterator[dict]:
    """
    Subscribe to a Redis channel and yield parsed messages.
    
    Args:
        redis_client: Redis client
        channel: Channel to subscribe to
        
    Yields:
        Parsed message dictionaries
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    yield data
                    
                    # Stop if we got the end signal
                    if data.get("type") == "end":
                        break
                except json.JSONDecodeError:
                    continue
    finally:
        await pubsub.unsubscribe(channel)
