"""Execute node with idempotency.

Simulates a settlement system using a SQLite table with a UNIQUE constraint
on the idempotency key. If the key exists, the execution is skipped (idempotent).
"""
import sqlite3
import hashlib
import json
from pathlib import Path

from app.audit import get_model_id

SETTLEMENT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "settlements.db"


def _get_settlement_db():
    """Get a connection to the simulated settlement system database."""
    db_dir = SETTLEMENT_DB_PATH.parent
    db_dir.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(SETTLEMENT_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT UNIQUE NOT NULL,
            trade_id TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def compute_idempotency_key(trade_id: str, category: str, proposed_fix_steps: list) -> str:
    """Compute SHA-256 idempotency key from trade details."""
    raw = f"{trade_id}|{category}|{json.dumps(proposed_fix_steps, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def execute(state):
    """Apply the approved fix (simulated settlement system with idempotency)."""
    trade_id = state["exception"].get("trade_id", "N/A")
    category = state.get("category", "UNKNOWN")
    proposed_fix_steps = state.get("proposed_fix_steps", [])

    idempotency_key = compute_idempotency_key(trade_id, category, proposed_fix_steps)

    conn = _get_settlement_db()
    try:
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            conn.execute(
                "INSERT INTO settlements (idempotency_key, trade_id, category, status, timestamp) VALUES (?, ?, ?, ?, ?)",
                (idempotency_key, trade_id, category, "APPLIED", timestamp)
            )
            conn.commit()
            result = "APPLIED"
        except sqlite3.IntegrityError:
            # Duplicate key — settlement already applied
            result = "DUPLICATE_SKIPPED"
    finally:
        conn.close()

    return {
        "executed": True,
        "idempotency_key": idempotency_key,
        "settlement_result": result,
    }