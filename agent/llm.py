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
    #     base_url="http://localhost:1234/v1",
    #     api_key=settings.OPENROUTER_API_KEY,
    #     model="qwen3-1.7b",
    #     # Request token usage from compatible providers
    #     model_kwargs={
    #         "stream_options": {"include_usage": True}
    #     }
    # )

    # return ChatOpenAI(
    #     model="gemini-2.5-flash",
    #     openai_api_key="AIzaSyAZyM5gwpVnRupLIjTE2pritDpcmbvZUAI",
    #     base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    # )

    # Use config so .env BASE_URL / LLM_MODEL are used (e.g. Ollama at 192.168.1.20:11434)
    base_url = settings.BASE_URL.rstrip("/") + "/v1"
    # (connect_timeout, read_timeout): long connect for slow networks, long read for LLM
    timeout = (60.0, 300.0)
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=base_url,
        openai_api_key=settings.OPENAI_API_KEY or "ollama",
        timeout=timeout,
        model_kwargs={
            "stream_options": {"include_usage": True}
        },
    )

    # return ChatOpenAI(
    #     base_url='https://ltceip4prod.azure-api.net/AI',
    #     model="GPT-OSS-120B",
    #     default_headers={
    #         "Ocp-Apim-Subscription-Key": "351588a104744813bf00652d900cb3a0",
    #         "x-api-key": "eyJ0ZWFtIjogIklQTVMiLCAiZW52IjogInByb2QifQ=="
    #     }
    # )

        # return ChatOpenAI(



    
