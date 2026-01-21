"""Pydantic schemas for request/response models."""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class QueryRequest(BaseModel):
    """Request model for text queries."""
    message: str = Field(..., description="User's query message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation context")
    context: Optional[dict] = Field(None, description="Additional context (e.g., current page)")


class QueryResponse(BaseModel):
    """Response model for queries."""
    content: str = Field(..., description="AI response content")
    category: Optional[str] = Field(None, description="Classified category of the query")
    tool_used: Literal["search", "rag", "general", "navigation"] = Field(..., description="Tool used to generate response")
    session_id: Optional[str] = Field(None, description="Session ID")
    target_route: Optional[str] = Field(None, description="Target route for navigation")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class NavigateRequest(BaseModel):
    """Request model for navigation commands."""
    command: str = Field(..., description="Navigation command (e.g., 'take me to stats')")
    context: Optional[str] = Field(None, description="Current page context")


class NavigateResponse(BaseModel):
    """Response model for navigation."""
    targetRoute: str = Field(..., description="Target URL or anchor")
    action: str = Field("navigate", description="Action to perform")
    message: Optional[str] = Field(None, description="Confirmation message")


class RouteInfo(BaseModel):
    """Information about a navigable route."""
    name: str
    path: str
    description: str


class AssistRequest(BaseModel):
    """Request model for nav mic assistant commands."""
    command: str = Field(..., description="Raw voice command or text")
    context: Optional[dict] = Field(None, description="Context such as current page")


class AssistAction(BaseModel):
    """Action to perform in the frontend."""
    type: Literal[
        "navigate",
        "open_upload",
        "focus_chat_input",
        "insert_text",
        "send_text",
        "show_guide",
        "open_chat",
        "highlight"
    ]
    target: Optional[str] = None
    value: Optional[str] = None


class AssistResponse(BaseModel):
    """Response model for nav mic assistant actions."""
    message: str
    actions: list[AssistAction] = []
    handled: bool = True
