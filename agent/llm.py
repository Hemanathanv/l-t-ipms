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
    # return ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     api_key=settings.OPENROUTER_API_KEY,
    #     # Using Gemini Flash which properly supports tools on OpenRouter
    #     model="google/gemini-2.0-flash-exp:free"
    # )

    # return ChatOpenAI(
    #     model="gemini-2.5-flash",
    #     openai_api_key="AIzaSyAoEMWsoHg_WGMzDva4ZlcishtnPcqiuFg",
    #     base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    # )

    return ChatOpenAI(
        model="qwen3-8b",
        openai_api_key="06bec33a36ee70a637f3e385666d0e1210a2b893681de1c7c5d42fbcbccbcfd8",
        base_url="http://192.168.10.100:5454/v1",
        streaming=False,  # Disable streaming - required for vLLM tool calls
    )

    # return ChatOpenAI(
    #     base_url="https://openrouter.ai/api/v1",
    #     api_key=settings.OPENROUTER_API_KEY,
    #     # Using Gemini Flash which properly supports tools on OpenRouter
    #     model="google/gemini-2.0-flash-exp:free"
    # )

        # return ChatOpenAI(



    
