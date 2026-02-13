from langchain_openai import ChatOpenAI
from config import settings
import httpx

def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="qwen3-8b",
        openai_api_key="06bec33a36ee70a637f3e385666d0e1210a2b893681de1c7c5d42fbcbccbcfd8",
        base_url="http://192.168.10.100:5454/v1"
    )