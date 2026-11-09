"""SQLite store for fictional trades, proposals, approvals, and MCP audit."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "settlement.db"

_lock = threading.Lock()


def db_path() -> Path:
    """Resolve the database path. Tests override it with SETTLEMENT_DB."""
    return Path(os.environ.get("SETTLEMENT_DB", str(DEFAULT_DB)))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            counterparty TEXT NOT NULL,
            expected_amount REAL,
            currency TEXT,
            settlement_date TEXT,
            status TEXT NOT NULL,
            ssi TEXT
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT NOT NULL,
            category TEXT NOT NULL,
            steps TEXT NOT NULL,
            citations TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            proposal_id INTEGER NOT NULL,
            reviewer TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT UNIQUE NOT NULL,
            trade_id TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mcp_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            client TEXT NOT NULL,
            tool TEXT NOT NULL,
            arguments TEXT NOT NULL,
            decision TEXT NOT NULL,
            result_status TEXT NOT NULL,
            latency_ms REAL NOT NULL
        );
        """
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_audit(
    client: str,
    tool: str,
    arguments: dict,
    decision: str,
    result_status: str,
    latency_ms: float,
) -> None:
    """Insert one audit row. The table is never updated or deleted from."""
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO mcp_audit
                    (timestamp, client, tool, arguments, decision, result_status, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    client,
                    tool,
                    json.dumps(arguments, sort_keys=True),
                    decision,
                    result_status,
                    round(latency_ms, 3),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def audit_rows() -> list[sqlite3.Row]:
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            return list(conn.execute("SELECT * FROM mcp_audit ORDER BY id"))
        finally:
            conn.close()
