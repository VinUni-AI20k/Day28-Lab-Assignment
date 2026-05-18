"""Local embedding service — CPU fallback for the Kaggle embedding tunnel.

Uses sentence-transformers/all-MiniLM-L6-v2 (384-dim, ~80MB), matching
the vector size expected by api-gateway and Qdrant.
"""
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI(title="Embedding Service")
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


class EmbedRequest(BaseModel):
    texts: List[str]


@app.post("/embed")
def embed(req: EmbedRequest):
    embeddings = model.encode(req.texts).tolist()
    return {"embeddings": embeddings, "dim": len(embeddings[0]) if embeddings else 0}


@app.get("/health")
def health():
    return {"status": "ok", "service": "embed", "model": "all-MiniLM-L6-v2"}
