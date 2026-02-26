"""
Configuration module for L&T IPMS Conversational App
Loads settings from environment variables
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:l-t-eye-password@192.168.1.20:5432/postgres"
    
    # Redis
    REDIS_URL: str
    
    # LLM Configuration
    BASE_URL: str 
    LLM_MODEL: str = "local-model"  # Model name for OpenAI-compatible API
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048
    OPENROUTER_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    API_SLUG: str = "/api/v1"
    
    # Cache settings
    CACHE_TTL_SECONDS: int = 3600  # 1 hour default TTL for cached messages
    
    # API settings
    API_TITLE: str = "L&T IPMS Conversational API"
    API_VERSION: str = "1.0.0"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export singleton for easy access
settings = get_settings()
