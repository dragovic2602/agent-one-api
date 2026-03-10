"""
Agent One — FastAPI service wrapping the RAG knowledge base.

Endpoints:
  POST   /chat                      Stream a response via SSE (custom format)
  POST   /v1/chat/completions       OpenAI-compatible streaming (used by Open WebUI)
  GET    /health                    DB ping + document/chunk counts
  DELETE /sessions/{session_id}     Clear conversation history for a session
"""

import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

load_dotenv()

from agent import agent, load_history, save_message, session_id_from_first_message
from auth import verify_api_key
from database import close_pool, get_pool, init_pool
from models import ChatRequest, CompletionRequest, HealthResponse

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Agent One API",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)],
)


# ---------------------------------------------------------------------------
# POST /chat — custom SSE format
# ---------------------------------------------------------------------------

async def _stream_chat(message: str, session_id: str):
    history = await load_history(session_id)

    try:
        full_response = []

        async with agent.run_stream(message, message_history=history) as result:
            async for token in result.stream_text(delta=True):
                full_response.append(token)
                payload = json.dumps({"content": token})
                yield f"data: {payload}\n\n"

        # Persist both turns after streaming completes
        await save_message(session_id, "user", message)
        await save_message(session_id, "assistant", "".join(full_response))

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Streaming error for session {session_id}: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _stream_chat(request.message, request.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — OpenAI-compatible (Open WebUI connects here)
# ---------------------------------------------------------------------------

async def _stream_openai(message: str, session_id: str, completion_id: str):
    history = await load_history(session_id)

    try:
        full_response = []

        async with agent.run_stream(message, message_history=history) as result:
            async for token in result.stream_text(delta=True):
                full_response.append(token)
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": os.getenv("LLM_CHOICE", "gpt-4o-mini"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"

        # Final chunk with finish_reason
        final_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": os.getenv("LLM_CHOICE", "gpt-4o-mini"),
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

        # Persist both turns
        await save_message(session_id, "user", message)
        await save_message(session_id, "assistant", "".join(full_response))

    except Exception as e:
        logger.error(f"OpenAI stream error for session {session_id}: {e}", exc_info=True)
        error_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": os.getenv("LLM_CHOICE", "gpt-4o-mini"),
            "choices": [{"index": 0, "delta": {"content": f"\n\nError: {e}"}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def openai_chat(request: CompletionRequest):
    # Extract user messages only (skip system role — we use our own system prompt)
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message provided")

    # Last message is the new input
    message = user_messages[-1].content

    # Stable session_id from first user message content
    first_message = user_messages[0].content
    session_id = session_id_from_first_message(first_message)

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    return StreamingResponse(
        _stream_openai(message, session_id, completion_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            documents = await conn.fetchval("SELECT COUNT(*) FROM documents")
            chunks = await conn.fetchval("SELECT COUNT(*) FROM chunks")
        return HealthResponse(status="ok", documents=documents, chunks=chunks)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}
# ---------------------------------------------------------------------------

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM conversations WHERE session_id = $1", session_id
        )
    return {"session_id": session_id, "cleared": True}
