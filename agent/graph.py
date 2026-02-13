from typing import Annotated, TypedDict, Sequence, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import ToolNode
from config import settings
from .llm import get_llm
from .tools import SRA_TOOLS


class AgentState(TypedDict):
    """State definition for the conversational agent"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    thread_id: str


# System prompt for the agent
SYSTEM_PROMPT = """You are an intelligent AI assistant for L&T IPMS (Integrated Project Management System).

## AVAILABLE TOOLS - USE ONLY WHEN APPROPRIATE:

1. **sra_status_pei** - Use ONLY when user asks about:
   - "What is the current PEI?"
   - "How's the project doing?"
   - "Show project status"
   - "What's the SPI/CPI?"

2. **sra_drill_delay** - Use ONLY when user asks about:
   - "Why is the project delayed?"
   - "What are the delay causes?"
   - "Analyze delays"
   - "Who is responsible for delays?"

3. **sra_recovery_advise** - Use ONLY when user asks about:
   - "How do we recover?"
   - "Give me options to regain schedule"
   - "What are our recovery options?"
   - "How can we get back on track?"
   After showing recovery options, suggest: "Would you like to simulate any of these options using `sra_simulate`?"

4. **sra_simulate** - Use ONLY when user asks about:
   - "What if I add 2 shuttering gangs?"
   - "If we work this Sunday?"
   - "Simulate adding resources"
   - "What happens if we add overtime?"
   After simulation, suggest: "Would you like to log this as an action using `sra_create_action`?"

5. **sra_create_action** - Use ONLY when user asks about:
   - "Log option 1"
   - "Raise alert to site planner"
   - "Create an action item"
   - "Approve this option"

6. **sra_explain_formula** - Use ONLY when user asks about:
   - "How did you compute SPI?"
   - "What is the PEI formula?"
   - "Explain CPI calculation"
   - "How are metrics calculated?"

## STRICT RULES:

1. **DO NOT HALLUCINATE**: Only answer questions you have tools for. If asked something outside the scope of these tools, politely say you can only help with SRA-related queries.

2. **ONE TOOL AT A TIME**: For each user question, use ONLY the most relevant tool. Do not call multiple tools unless explicitly needed.

3. **FOLLOW-UP SUGGESTIONS**: After each tool response, suggest ONE relevant next step from available tools.

4. **MINIMAL OUTPUT**: Keep responses concise. No long paragraphs. Use the tool output directly with a brief intro.

5. **ASK FOR MISSING INFO**: If a tool requires project_id or dates, the tool will ask - do not make up data.

## CONVERSATION FLOW EXAMPLE:
User: "How do we recover?"
→ Call sra_recovery_advise
→ Show recovery options
→ Suggest: "Would you like me to simulate any of these options?"

User: "Simulate option 1 with 2 extra crews"
→ Call sra_simulate
→ Show simulation results
→ Suggest: "Would you like to log this as an action?"

User: "Yes, log it"
→ Call sra_create_action
→ Confirm action logged
"""


async def chat_node(state: AgentState) -> dict:
    """
    Main chat node that processes user messages and generates responses.
    Uses LLM with tools bound.
    """
    from .message_pruner import prune_messages, MAX_CONTEXT_TOKENS
    
    llm = get_llm()
    
    # Bind tools to the LLM
    # Note: For vLLM, you need to start the server with:
    #   --enable-auto-tool-choice --tool-call-parser hermes
    llm_with_tools = llm.bind_tools(SRA_TOOLS)
    
    # Get the conversation history
    messages = list(state["messages"])
    
    # Add system prompt if this is the start of conversation
    has_system = any(isinstance(m, SystemMessage) for m in messages)
    if not has_system:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    
    # Prune messages to fit within token budget
    messages = prune_messages(messages, max_tokens=MAX_CONTEXT_TOKENS)
    
    # Call the LLM with tools
    # Use sync invoke in a thread to avoid async streaming issues
    import asyncio
    response = await asyncio.to_thread(llm_with_tools.invoke, messages)
    
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """
    Determine if we should continue to tools or end.
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the LLM made a tool call, route to tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    # Otherwise, end
    return "__end__"


def build_graph() -> StateGraph:
    """
    Build the LangGraph conversation graph with tools.
    
    Graph structure:
    START -> chat -> (tools -> chat)* -> END
    """
    # Create the graph builder
    graph_builder = StateGraph(AgentState)
    
    # Create tool node with SRA tools
    tool_node = ToolNode(SRA_TOOLS)
    
    # Add nodes
    graph_builder.add_node("chat", chat_node)
    graph_builder.add_node("tools", tool_node)
    
    # Define the flow
    graph_builder.add_edge(START, "chat")
    
    # Conditional edge from chat: either go to tools or end
    graph_builder.add_conditional_edges(
        "chat",
        should_continue,
        {
            "tools": "tools",
            "__end__": END
        }
    )
    
    # After tools, always go back to chat for LLM to process results
    graph_builder.add_edge("tools", "chat")
    
    return graph_builder


async def create_agent(checkpointer=None):
    """
    Create the compiled agent with PostgreSQL checkpointing.
    
    Args:
        checkpointer: Optional pre-initialized checkpointer
    
    Returns:
        Compiled LangGraph agent with persistent checkpointing
    """
    # Build the graph
    graph_builder = build_graph()
    
    # Compile the graph with checkpointer (if provided)
    agent = graph_builder.compile(checkpointer=checkpointer)
    
    return agent


def create_checkpointer():
    """
    Create the PostgreSQL checkpointer.
    Returns an async context manager that must be used with 'async with' or __aenter__/__aexit__.
    
    Returns:
        AsyncPostgresSaver context manager
    """
    return AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)


async def run_conversation(
    agent,
    message: str,
    thread_id: str,
    project_context: dict | None = None
) -> str:
    """
    Run a conversation turn with the agent.
    
    Args:
        agent: Compiled LangGraph agent
        message: User message
        thread_id: Conversation thread ID for persistence
        project_context: Optional dict with project_id, project_name, date_range
        
    Returns:
        Assistant response text
    """
    # Create config with thread_id for checkpointing
    config = {"configurable": {"thread_id": thread_id}}
    
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
    
    # Create user message
    user_message = HumanMessage(content=enhanced_message)
    
    # Run the agent
    result = await agent.ainvoke(
        {"messages": [user_message], "thread_id": thread_id},
        config=config
    )
    
    # Extract the assistant's response (last AI message that's not a tool call)
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            return msg.content
        elif isinstance(msg, AIMessage) and msg.content:
            # AIMessage with content (might also have tool calls)
            return msg.content
    
    return "I apologize, but I couldn't generate a response. Please try again."


async def get_conversation_history(agent, thread_id: str) -> list[dict]:
    """
    Retrieve conversation history from checkpointer.
    
    Args:
        agent: Compiled LangGraph agent
        thread_id: Conversation thread ID
        
    Returns:
        List of message dictionaries (excluding system messages and tool calls)
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = await agent.aget_state(config)
        if state and state.values:
            messages = state.values.get("messages", [])
            result = []
            for m in messages:
                # Skip system messages and tool messages
                if isinstance(m, SystemMessage):
                    continue
                if isinstance(m, ToolMessage):
                    continue
                    
                # Determine role
                if isinstance(m, HumanMessage):
                    role = "user"
                elif isinstance(m, AIMessage):
                    # Skip AI messages that are just tool calls without content
                    if not m.content and getattr(m, "tool_calls", None):
                        continue
                    role = "assistant"
                else:
                    continue
                
                result.append({
                    "role": role,
                    "content": m.content
                })
            
            return result
    except Exception as e:
        print(f"Error getting conversation history: {e}")
    
    return []
