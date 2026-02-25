"""
Generate a visual PNG of the real LangGraph agent graph.
Run from the project root: python generate_graph.py
"""

from agent.graph import build_graph


if __name__ == "__main__":
    graph = build_graph().compile()

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
