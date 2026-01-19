"""
Generate a visual representation of the LangGraph conversation graph
"""

import asyncio
from langgraph.graph import StateGraph, START, END
from typing import Annotated, TypedDict, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State definition for the conversational agent"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    thread_id: str


def chat_node(state: AgentState) -> dict:
    """Placeholder chat node"""
    return {"messages": []}


def build_graph() -> StateGraph:
    """Build the LangGraph conversation graph"""
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("chat", chat_node)
    graph_builder.add_edge(START, "chat")
    graph_builder.add_edge("chat", END)
    return graph_builder


if __name__ == "__main__":
    # Build the graph
    graph_builder = build_graph()
    graph = graph_builder.compile()
    
    # Generate PNG image
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open("graph.png", "wb") as f:
            f.write(png_data)
        print("✅ Graph saved to graph.png")
    except Exception as e:
        print(f"❌ Error generating PNG: {e}")
        print("\n📝 Generating Mermaid diagram instead...")
        mermaid = graph.get_graph().draw_mermaid()
        print(mermaid)
        with open("graph.mermaid", "w") as f:
            f.write(mermaid)
        print("✅ Mermaid diagram saved to graph.mermaid")
