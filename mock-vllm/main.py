"""Mock vLLM — OpenAI-compatible /v1/chat/completions endpoint.

Lab fallback layer: replaces the Kaggle GPU vLLM service when the hybrid
tunnel is unavailable. Returns canned-but-plausible completions so that
downstream integration tests (smoke, readiness) remain deterministic.
"""
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock vLLM (OpenAI-compatible)")
MODEL = "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4"


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = MODEL
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "mock"}]}


@app.post("/v1/chat/completions")
def chat_completions(req: ChatRequest):
    user_msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    snippet = user_msg[:200].replace("\n", " ")
    answer = (
        "Platform engineering is the discipline of building self-service "
        "developer platforms that abstract infrastructure complexity. "
        f"Based on the provided context, your query — '{snippet}' — typically "
        "involves orchestrating CI/CD, observability, and data pipelines as a product."
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(user_msg.split()),
            "completion_tokens": len(answer.split()),
            "total_tokens": len(user_msg.split()) + len(answer.split()),
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-vllm"}
