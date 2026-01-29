"""
Message Pruning Utility for LangGraph Agent
Provides token-aware message pruning to prevent context overflow
"""

from typing import Sequence
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage

# Configuration
MAX_CONTEXT_TOKENS = 6000  # Leave room for response (model max is ~8200)
MIN_RECENT_MESSAGES = 4     # Always keep at least this many recent messages
CHARS_PER_TOKEN = 4         # Approximation for token counting


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a string.
    Uses simple chars/4 approximation which works reasonably well for most models.
    """
    if not text:
        return 0
    return len(text) // CHARS_PER_TOKEN + 1


def estimate_message_tokens(message: BaseMessage) -> int:
    """
    Estimate token count for a message including role overhead.
    """
    content = message.content if isinstance(message.content, str) else str(message.content)
    base_tokens = estimate_tokens(content)
    
    # Add overhead for message structure (~4 tokens for role + formatting)
    overhead = 4
    
    # Tool calls add extra tokens
    if hasattr(message, 'tool_calls') and message.tool_calls:
        for tool_call in message.tool_calls:
            overhead += estimate_tokens(str(tool_call.get('name', '')))
            overhead += estimate_tokens(str(tool_call.get('args', {})))
    
    return base_tokens + overhead


def prune_messages(
    messages: Sequence[BaseMessage],
    max_tokens: int = MAX_CONTEXT_TOKENS,
    min_recent: int = MIN_RECENT_MESSAGES
) -> list[BaseMessage]:
    """
    Prune messages to fit within token budget while preserving context.
    
    Strategy:
    1. Always keep the system message (if present)
    2. Always keep the last `min_recent` messages
    3. Remove oldest non-essential messages until under budget
    4. Never break tool call -> tool message pairs
    
    Args:
        messages: List of messages to prune
        max_tokens: Maximum token budget for the context
        min_recent: Minimum number of recent messages to always keep
    
    Returns:
        Pruned list of messages that fits within token budget
    """
    if not messages:
        return []
    
    messages = list(messages)  # Make mutable copy
    
    # Separate system message if present
    system_msg = None
    working_messages = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_msg = msg
        else:
            working_messages.append(msg)
    
    # Calculate current token count
    def total_tokens(msgs: list[BaseMessage]) -> int:
        total = 0
        if system_msg:
            total += estimate_message_tokens(system_msg)
        for m in msgs:
            total += estimate_message_tokens(m)
        return total
    
    current_tokens = total_tokens(working_messages)
    
    # If already under budget, return as is
    if current_tokens <= max_tokens:
        result = ([system_msg] if system_msg else []) + working_messages
        return result
    
    # Need to prune - protect recent messages
    protected_count = min(min_recent, len(working_messages))
    protected_messages = working_messages[-protected_count:] if protected_count > 0 else []
    prunable_messages = working_messages[:-protected_count] if protected_count > 0 else working_messages[:]
    
    # Remove oldest messages until under budget
    removed_count = 0
    while prunable_messages and total_tokens(prunable_messages + protected_messages) > max_tokens:
        # Find the first message that's safe to remove
        # Don't remove ToolMessage without its preceding AIMessage with tool_calls
        idx_to_remove = 0
        
        # Check if first message is part of a tool sequence
        msg = prunable_messages[0]
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            # This is a tool call - also remove following ToolMessages
            idx_to_remove = 0
            prunable_messages.pop(0)
            removed_count += 1
            # Remove associated ToolMessages
            while prunable_messages and isinstance(prunable_messages[0], ToolMessage):
                prunable_messages.pop(0)
                removed_count += 1
        elif isinstance(msg, ToolMessage):
            # Orphaned ToolMessage - safe to remove
            prunable_messages.pop(0)
            removed_count += 1
        else:
            # Regular message (Human or AI without tool calls) - remove it
            prunable_messages.pop(0)
            removed_count += 1
    
    # Log pruning action
    if removed_count > 0:
        final_tokens = total_tokens(prunable_messages + protected_messages)
        print(f"[PRUNE] Removed {removed_count} old messages, kept {len(prunable_messages) + len(protected_messages)}, tokens: {final_tokens}/{max_tokens}")
    
    # Reconstruct message list
    result = []
    if system_msg:
        result.append(system_msg)
    result.extend(prunable_messages)
    result.extend(protected_messages)
    
    return result


def should_prune(messages: Sequence[BaseMessage], threshold: int = MAX_CONTEXT_TOKENS) -> bool:
    """
    Check if messages need pruning based on token count.
    
    Args:
        messages: List of messages to check
        threshold: Token threshold to trigger pruning
    
    Returns:
        True if pruning is recommended
    """
    total = sum(estimate_message_tokens(m) for m in messages)
    return total > threshold
