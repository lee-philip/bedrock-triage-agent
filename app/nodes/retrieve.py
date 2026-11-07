"""Retrieve relevant runbook sections using FAISS index."""
import json
import os
from pathlib import Path

import faiss
import numpy as np

from app.llm import get_embeddings
from app.config import EMBED_PROVIDER
from app.observability import start_span

# Index directory
INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / f"index-{EMBED_PROVIDER}"

# Load index once
_index = None
_metadata = None


def _load_index():
    global _index, _metadata
    if _index is not None:
        return
    index_path = INDEX_DIR / "index.faiss"
    metadata_path = INDEX_DIR / "metadata.json"
    if not index_path.exists():
        raise FileNotFoundError(f"FAISS index not found at {index_path}. Run scripts/build_index.py first.")
    _index = faiss.read_index(str(index_path))
    with open(metadata_path) as f:
        _metadata = json.load(f)


async def retrieve(state):
    """Retrieve relevant runbook sections based on the exception category and details."""
    _load_index()

    category = state.get("category", "UNKNOWN")
    exception = state["exception"]

    # Build query from category and exception details
    query = f"{category} trade settlement exception"
    if exception.get("error_message"):
        query += f" {exception['error_message']}"
    if exception.get("notes"):
        query += f" {exception['notes']}"

    span, lf = start_span("faiss-retrieve", input={"query": query, "category": category})

    try:
        # Embed query
        embeddings_model = get_embeddings()
        query_vector = embeddings_model.embed_query(query)
        query_np = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query_np)

        # Search for top k=3 chunks
        k = 3
        distances, indices = _index.search(query_np, k)

        # Collect results
        chunks = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx >= len(_metadata):
                continue
            chunk = _metadata[idx].copy()
            chunk["score"] = float(dist)
            chunks.append(chunk)

        chunk_ids = [c["id"] for c in chunks]
        span.update(output={"chunk_ids": chunk_ids, "count": len(chunks)})
    finally:
        if span is not None:
            span.end()

    print(f"\n=== RETRIEVE ===")
    print(f"Retrieved {len(chunks)} runbook chunks: {', '.join(chunk_ids)}")
    return {
        "runbook_chunks": chunks,
        "retrieved_chunk_ids": chunk_ids,
    }
