"""Append-only audit log persisted to SQLite."""
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import LLM_PROVIDER, LMSTUDIO_MODEL, BEDROCK_MODEL_ID

AUDIT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "audit.db"


def get_model_id():
    if LLM_PROVIDER == "local":
        return LMSTUDIO_MODEL
    return BEDROCK_MODEL_ID


def _get_audit_db():
    """Get a connection to the audit database."""
    db_dir = AUDIT_DB_PATH.parent
    db_dir.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(AUDIT_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            node TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            latency_ms REAL,
            data TEXT
        )
    """)
    conn.commit()
    return conn


def write_audit(run_id: str, node_name: str, latency_ms=None, data=None):
    """Write an append-only audit entry."""
    conn = _get_audit_db()
    try:
        conn.execute(
            "INSERT INTO audit (run_id, node, timestamp, provider, model, latency_ms, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                node_name,
                datetime.now(timezone.utc).isoformat(),
                LLM_PROVIDER,
                get_model_id(),
                latency_ms,
                data,
            )
        )
        conn.commit()
    finally:
        conn.close()


def timed_node(node_func, node_name):
    """Wrap a node function to measure latency and append audit."""
    async def wrapper(state):
        start = time.time()
        result = await node_func(state)
        elapsed_ms = (time.time() - start) * 1000
        # Write to SQLite audit
        write_audit(
            run_id=state.get("run_id", "unknown"),
            node_name=node_name,
            latency_ms=round(elapsed_ms, 1)
        )
        # Also maintain in-memory audit list for the current run
        entry = {
            "node": node_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": LLM_PROVIDER,
            "model": get_model_id(),
            "latency_ms": round(elapsed_ms, 1),
        }
        result["audit"] = [entry]
        return result
    return wrapper