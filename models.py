"""
Pydantic request/response models.
"""

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Custom /chat endpoint
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str  # UUID, client-generated


class HealthResponse(BaseModel):
    status: str
    documents: int
    chunks: int


# ---------------------------------------------------------------------------
# OpenAI-compatible /v1/chat/completions endpoint (used by Open WebUI)
# ---------------------------------------------------------------------------

class CompletionMessage(BaseModel):
    role: str    # "user" | "assistant" | "system"
    content: str


class CompletionRequest(BaseModel):
    model: str
    messages: list[CompletionMessage]
    stream: bool = True
