"""FAISS runbook search used by the search_runbooks tool."""
import json
from pathlib import Path

import faiss
import numpy as np

from mcp_server.config import CATEGORIES

ROOT = Path(__file__).resolve().parents[1]

# Runbook filename stems are shorter than the category enum.
CATEGORY_SOURCE = {
    "SSI_MISMATCH": "ssi_mismatch",
    "MISSING_COUNTERPARTY_BIC": "missing_bic",
    "PRICE_TOLERANCE_BREAK": "price_tolerance",
    "SETTLEMENT_DATE_MISMATCH": "settlement_date",
    "INSUFFICIENT_CASH": "insufficient_cash",
    "QUANTITY_MISMATCH": "quantity_mismatch",
}


def search_index(query: str, category: str, k: int) -> dict:
    """Query the Phase 3 index. Prefer chunks from the category's runbook."""
    from app.config import EMBED_PROVIDER
    from app.llm import get_embeddings

    index_dir = ROOT / "data" / f"index-{EMBED_PROVIDER}"
    index_path = index_dir / "index.faiss"
    metadata_path = index_dir / "metadata.json"
    if not index_path.exists():
        return {
            "ok": False,
            "status": "INDEX_MISSING",
            "error": f"FAISS index not found at {index_path}. Run scripts/build_index.py first.",
        }

    index = faiss.read_index(str(index_path))
    metadata = json.loads(metadata_path.read_text())
    query_vector = get_embeddings().embed_query(query)
    query_np = np.array([query_vector], dtype=np.float32)
    faiss.normalize_L2(query_np)

    fetch = min(max(k * 4, k), len(metadata))
    distances, indices = index.search(query_np, fetch)
    stem = CATEGORY_SOURCE.get(category)
    ranked = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1 or idx >= len(metadata):
            continue
        chunk = metadata[idx].copy()
        chunk["score"] = float(dist)
        source = str(chunk.get("source", ""))
        chunk["_preferred"] = bool(stem and stem in source)
        ranked.append(chunk)

    if category in CATEGORIES and stem:
        preferred = [chunk for chunk in ranked if chunk["_preferred"]]
        others = [chunk for chunk in ranked if not chunk["_preferred"]]
        ranked = preferred + others

    chunks = []
    for chunk in ranked[:k]:
        chunk.pop("_preferred", None)
        chunks.append(chunk)
    return {
        "ok": True,
        "status": "OK",
        "chunks": chunks,
        "chunk_ids": [chunk["id"] for chunk in chunks],
    }
