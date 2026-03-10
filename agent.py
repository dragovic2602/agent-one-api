"""
PydanticAI agent with search_knowledge_base tool.

Fully independent — no imports from Docling RAG Agent.
Only reads from Supabase. Chat history is persisted in Supabase conversations/messages tables.
"""

import hashlib
import logging
import os
from typing import Any

from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

from database import get_pool

logger = logging.getLogger(__name__)

# Customer-specific config — set per deployment in .env
AGENT_NAME = os.getenv("AGENT_NAME", "Knowledge Assistant")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are an intelligent knowledge assistant with access to an organisation's "
    "documentation and information. Your role is to help users find accurate "
    "information from the knowledge base. You have a professional yet friendly demeanour.\n\n"
    "IMPORTANT: Always search the knowledge base before answering questions about "
    "specific information. If information isn't in the knowledge base, clearly state "
    "that and offer general guidance. Be concise but thorough in your responses. "
    "Ask clarifying questions if the user's query is ambiguous. When you find "
    "relevant information, synthesise it clearly and cite the source documents.",
)

# OpenAI client for embeddings
_openai_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


async def embed_query(query: str) -> list[float]:
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    client = get_openai_client()
    response = await client.embeddings.create(model=model, input=query)
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# Supabase history persistence
# ---------------------------------------------------------------------------

def session_id_from_first_message(first_user_message: str) -> str:
    """Derive a stable session_id by hashing the first user message."""
    return hashlib.sha256(first_user_message.encode()).hexdigest()[:32]


async def load_history(session_id: str) -> list[Any]:
    """
    Load chat history from Supabase and convert to PydanticAI message objects.
    Returns an empty list if no history exists yet.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        conv = await conn.fetchrow(
            "SELECT id FROM conversations WHERE session_id = $1", session_id
        )
        if not conv:
            return []

        rows = await conn.fetch(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            """,
            conv["id"],
        )

    history = []
    for row in rows:
        if row["role"] == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=row["content"])]))
        elif row["role"] == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=row["content"])]))
    return history


async def save_message(session_id: str, role: str, content: str) -> None:
    """
    Upsert the conversation row and insert a message.
    role: 'user' | 'assistant'
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Upsert conversation
        conv_id = await conn.fetchval(
            """
            INSERT INTO conversations (session_id)
            VALUES ($1)
            ON CONFLICT (session_id) DO UPDATE SET session_id = EXCLUDED.session_id
            RETURNING id
            """,
            session_id,
        )
        # Insert message
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, $2, $3)",
            conv_id,
            role,
            content,
        )


# ---------------------------------------------------------------------------
# RAG tool
# ---------------------------------------------------------------------------

async def search_knowledge_base(ctx: RunContext[None], query: str, limit: int = 5) -> str:
    """
    Search the knowledge base using semantic similarity.

    Args:
        query: The search query to find relevant information
        limit: Maximum number of results to return (default: 5)

    Returns:
        Formatted search results with source citations
    """
    try:
        query_embedding = await embed_query(query)
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        candidates = limit * 3
        pool = get_pool()
        async with pool.acquire() as conn:
            results = await conn.fetch(
                "SELECT * FROM match_chunks_hybrid($1::vector, $2, $3)",
                embedding_str,
                query,
                candidates,
            )

        # Rerank: penalise redundant chunks from the same document
        seen_docs: dict[str, int] = {}
        reranked = []
        for row in results:
            doc_id = str(row["document_id"])
            base_score = float(row["similarity"])
            doc_count = seen_docs.get(doc_id, 0)
            final_score = base_score - 0.1 * doc_count
            seen_docs[doc_id] = doc_count + 1
            reranked.append((final_score, row))

        reranked.sort(key=lambda x: x[0], reverse=True)
        top_results = [row for _, row in reranked[:limit]]

        if not top_results:
            return "No relevant information found in the knowledge base for your query."

        parts = [
            f"[Source: {row['document_title']}]\n{row['content']}\n"
            for row in top_results
        ]
        return f"Found {len(parts)} relevant results:\n\n" + "\n---\n".join(parts)

    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}", exc_info=True)
        return f"I encountered an error searching the knowledge base: {str(e)}"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def build_agent() -> Agent:
    model = os.getenv("LLM_CHOICE", "gpt-4o-mini")
    return Agent(
        f"openai:{model}",
        system_prompt=SYSTEM_PROMPT,
        tools=[search_knowledge_base],
    )


agent = build_agent()
