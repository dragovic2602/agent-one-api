# Agent One — API

FastAPI service that wraps the RAG knowledge base with an SSE streaming chat endpoint. Reads from Supabase; ingestion stays in `Docling RAG Agent/`.

---

## Setup

### 1. Copy and fill in environment variables
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2. Install dependencies
```bash
pip install uv
uv sync
```

### 3. Run locally
```bash
uv run uvicorn main:app --reload
```

Server starts on `http://localhost:8000`.

---

## Docker (VPS)

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

---

## API Reference

All endpoints require the `X-API-Key` header.

### `GET /health`
Returns DB status and document/chunk counts.

```bash
curl http://localhost:8000/health -H "X-API-Key: your-key"
```

```json
{"status": "ok", "documents": 42, "chunks": 318}
```

### `POST /chat`
Streams a response via Server-Sent Events (SSE).

```bash
curl -N http://localhost:8000/chat \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is our refund policy?", "session_id": "abc-123"}'
```

Each token arrives as:
```
data: {"content": "token"}

data: [DONE]
```

The `session_id` is a client-generated UUID. Sending the same `session_id` in subsequent requests maintains conversation history.

### `DELETE /sessions/{session_id}`
Clears conversation history for a session.

```bash
curl -X DELETE http://localhost:8000/sessions/abc-123 -H "X-API-Key: your-key"
```

---

## Notes
- Sessions are in-memory — history resets on restart
- HTTPS is handled by your VPS reverse proxy (nginx)
- One deployment per customer; credentials live in `.env`
