"""Build FAISS embedding index from runbook markdown files.

Splits runbooks by ## headings, embeds each section, and saves the index
to data/index-{EMBED_PROVIDER}/ for retrieval.

Usage: python scripts/build_index.py
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import faiss
import numpy as np
from app.llm import get_embeddings
from app.config import EMBED_PROVIDER


def split_by_headings(text: str, source_file: str) -> list:
    """Split markdown by ## headings into chunks with metadata."""
    chunks = []
    # Match ## heading and its content until next ## or EOF
    pattern = r'(## .+?)(?=\n## |\Z)'
    matches = re.findall(pattern, text, re.DOTALL)

    for match in matches:
        lines = match.strip().split('\n')
        heading = lines[0].strip()
        content = '\n'.join(lines[1:]).strip()
        # Create chunk ID from source filename and heading
        source_id = Path(source_file).stem
        heading_slug = re.sub(r'[^a-zA-Z0-9]+', '-', heading.replace('## ', '').strip()).lower()
        chunk_id = f"RB-{source_id}-{heading_slug}"
        chunks.append({
            "id": chunk_id,
            "heading": heading,
            "content": content,
            "source": source_file,
        })

    return chunks


def build_index():
    """Build FAISS index from all runbook files."""
    runbooks_dir = Path(__file__).resolve().parents[1] / "runbooks"
    data_dir = Path(__file__).resolve().parents[1] / "data"
    index_dir = data_dir / f"index-{EMBED_PROVIDER}"
    index_dir.mkdir(parents=True, exist_ok=True)

    # Collect all chunks
    all_chunks = []
    for runbook in sorted(runbooks_dir.glob("*.md")):
        text = runbook.read_text()
        chunks = split_by_headings(text, str(runbook))
        all_chunks.extend(chunks)
        print(f"  {runbook.name}: {len(chunks)} chunks")

    print(f"Total chunks: {len(all_chunks)}")

    # Embed all chunks
    embeddings_model = get_embeddings()
    texts = [chunk["content"] for chunk in all_chunks]
    print("Embedding chunks...")
    vectors = embeddings_model.embed_documents(texts)

    # Create FAISS index (inner product for cosine similarity)
    dimension = len(vectors[0])
    index = faiss.IndexFlatIP(dimension)
    # Normalize vectors for cosine similarity
    vectors_np = np.array(vectors, dtype=np.float32)
    faiss.normalize_L2(vectors_np)
    index.add(vectors_np)

    # Save index and metadata
    faiss.write_index(index, str(index_dir / "index.faiss"))
    with open(index_dir / "metadata.json", "w") as f:
        json.dump(all_chunks, f, indent=2)

    print(f"Index saved to {index_dir}")


if __name__ == "__main__":
    build_index()
