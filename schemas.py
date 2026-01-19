"""
Pydantic Schemas for API Request/Response Models
"""

from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(..., min_length=1, description="User message")
    thread_id: str | None = Field(None, description="Conversation thread ID (optional, will be generated if not provided)")
    project_id: str | None = Field(None, description="Selected project ID for context filtering")


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str = Field(..., description="Assistant's response")
    thread_id: str = Field(..., description="Conversation thread ID")
    message_count: int = Field(..., description="Total messages in conversation")


class MessageSchema(BaseModel):
    """Schema for individual message"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    created_at: datetime | None = Field(None, description="Message timestamp")


class ConversationHistory(BaseModel):
    """Response model for conversation history"""
    thread_id: str = Field(..., description="Conversation thread ID")
    messages: list[MessageSchema] = Field(default_factory=list, description="List of messages")
    created_at: datetime | None = Field(None, description="Conversation creation time")


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="Overall health status")
    redis: str = Field(..., description="Redis connection status")
    postgres: str = Field(..., description="PostgreSQL connection status")
    llm: str = Field(..., description="LLM endpoint status")
