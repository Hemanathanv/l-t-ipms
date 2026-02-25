"""
Admin dashboard API routes for L&T IPMS.
Provides token usage analytics for admin users.
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from auth.dependencies import get_current_user
from db import get_prisma
from config import settings

router = APIRouter(prefix=settings.API_SLUG + "/admin", tags=["Admin"])


def _require_admin(user):
    """Raise 403 if user is not an admin."""
    role = getattr(user, "systemRole", None) or getattr(user, "system_role", None)
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/token-usage")
async def get_token_usage(user=Depends(get_current_user)):
    """
    Get aggregated token usage statistics and per-message details.
    Admin-only endpoint.
    """
    _require_admin(user)

    prisma = await get_prisma()

    # Fetch all messages ordered by newest first
    messages = await prisma.message.find_many(
        order={"createdAt": "desc"},
        include={"conversation": True},
    )

    # Compute summary stats
    total_input = 0
    total_output = 0
    total_tokens = 0
    total_tool_calls = 0
    latency_values = []
    conversation_ids = set()

    rows = []
    for msg in messages:
        inp = msg.inputTokens or 0
        out = msg.outputTokens or 0
        tot = msg.totalTokens or 0

        total_input += inp
        total_output += out
        total_tokens += tot

        if msg.toolName:
            total_tool_calls += 1

        conversation_ids.add(msg.conversationId)

        # Parse metadata for latency
        latency_ms = None
        meta = msg.metadata
        if meta:
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            if isinstance(meta, dict):
                latency_ms = meta.get("latency_ms")
                if latency_ms is not None:
                    latency_values.append(float(latency_ms))

        # Parse tool_calls JSON
        tool_calls_data = None
        if msg.toolCalls:
            tc = msg.toolCalls
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except (json.JSONDecodeError, TypeError):
                    tc = None
            tool_calls_data = tc

        # Build row for AG Grid
        rows.append({
            "id": msg.id,
            "conversation_id": msg.conversationId,
            "thread_id": msg.conversation.threadId if msg.conversation else None,
            "role": msg.role,
            "content": (msg.content[:120] + "...") if msg.content and len(msg.content) > 120 else msg.content,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": tot,
            "tool_name": msg.toolName,
            "tool_calls": tool_calls_data,
            "model": msg.model,
            "latency_ms": latency_ms,
            "feedback": msg.feedback,
            "created_at": msg.createdAt.isoformat() if msg.createdAt else None,
        })

    avg_latency = round(sum(latency_values) / len(latency_values), 1) if latency_values else None

    summary = {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "total_messages": len(messages),
        "total_conversations": len(conversation_ids),
        "total_tool_calls": total_tool_calls,
        "avg_latency_ms": avg_latency,
    }

    return {"summary": summary, "messages": rows}
