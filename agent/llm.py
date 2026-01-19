"""
LLM Client Configuration
Configures OpenAI-compatible LLM client for the conversational agent
"""

from langchain_openai import ChatOpenAI

from config import settings


def get_llm() -> ChatOpenAI:
    """
    Create and return a configured LLM instance.
    
    Uses OpenRouter API with a model that properly supports tool calling.
    Note: streaming=False is required for tool support on most providers.
    Graph-level event streaming via astream_events still works.
    """
    return ChatOpenAI(
        model="qwen3-8b",
        openai_api_key="06bec33a36ee70a637f3e385666d0e1210a2b893681de1c7c5d42fbcbccbcfd8",
        base_url="http://192.168.10.232:5454/v1",
        streaming=False,  # Disable streaming - required for vLLM tool calls
    )

    
