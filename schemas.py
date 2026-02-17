"""
Pydantic Schemas for API Request/Response Models
"""

from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(..., min_length=1, description="User message")
    thread_id: str | None = Field(None, description="Conversation thread ID (optional, will be generated if not provided)")
    project_key: str | None = Field(None, description="Selected project key for context filtering")


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str = Field(..., description="Assistant's response")
    thread_id: str = Field(..., description="Conversation thread ID")
    message_count: int = Field(..., description="Total messages in conversation")


class MessageSchema(BaseModel):
    """Schema for individual message"""
    id: str | None = Field(None, description="Message database ID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    created_at: datetime | None = Field(None, description="Message timestamp")
    feedback: str | None = Field(None, description="User feedback: 'positive' or 'negative'")
    # Branching fields for ChatGPT-style navigation
    position_index: int | None = Field(None, description="Logical position in conversation")
    branch_index: int | None = Field(None, description="Version number at this position (0 = original)")
    total_branches: int | None = Field(None, description="Total versions at this position")


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


class FeedbackRequest(BaseModel):
    """Request model for message feedback"""
    feedback: str = Field(..., description="Feedback type: 'positive' or 'negative'")
    note: str | None = Field(None, description="Optional feedback note")


class EditMessageRequest(BaseModel):
    """Request model for editing a message"""
    content: str = Field(..., min_length=1, description="New message content")
