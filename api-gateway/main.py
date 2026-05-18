# api-gateway/main.py
import os
import time
from typing import List, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="AI Platform API Gateway")
Instrumentator().instrument(app).expose(app)

VLLM_URL = os.environ.get("VLLM_URL", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4")

LANGSMITH_ENABLED = bool(os.environ.get("LANGCHAIN_API_KEY"))
if LANGSMITH_ENABLED:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "lab28-platform")
    try:
        from langsmith.run_helpers import traceable
    except ImportError:
        LANGSMITH_ENABLED = False


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    embedding: Optional[List[float]] = None


async def _vector_search(vector: List[float]) -> list:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{QDRANT_URL}/collections/documents/points/search",
                json={"vector": vector, "limit": 3},
            )
            return resp.json().get("result", []) if resp.status_code == 200 else []
        except Exception:
            return []


async def _llm_complete(prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{VLLM_URL}/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return resp.json()


async def _run_rag(query: str, vector: List[float]) -> dict:
    start = time.time()
    context = await _vector_search(vector)
    prompt = f"Context: {context}\n\nQuery: {query}"
    result = await _llm_complete(prompt)
    return {
        "answer": result["choices"][0]["message"]["content"],
        "latency_ms": round((time.time() - start) * 1000, 2),
        "model": result.get("model", MODEL_NAME),
        "retrieved_docs": len(context),
    }


if LANGSMITH_ENABLED:
    _run_rag = traceable(run_type="chain", name="rag_chat", project_name="lab28-platform")(_run_rag)


@app.post("/api/v1/chat")
async def chat(req: ChatRequest):
    vector = req.embedding or [0.0] * 384
    return await _run_rag(req.query, vector)


@app.get("/health")
def health():
    return {"status": "ok", "langsmith": LANGSMITH_ENABLED}
