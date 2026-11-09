"""Fictional settlement records, staged proposals, and idempotent apply."""
import hashlib
import json
import sqlite3

from mcp_server.db import connect, ensure_schema, utc_now, _lock
from mcp_server.governance import ToolRejected


def compute_idempotency_key(trade_id: str, category: str, proposed_fix_steps: list) -> str:
    """SHA-256 of trade, category, and ordered fix steps. Same inputs, same key."""
    raw = f"{trade_id}|{category}|{json.dumps(proposed_fix_steps, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def lookup_trade(trade_id: str) -> dict:
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT * FROM trades WHERE trade_id = ?",
                (trade_id,),
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        return {
            "ok": False,
            "status": "NOT_FOUND",
            "error": f"no fictional trade {trade_id}",
        }
    return {"ok": True, "status": "OK", "trade": dict(row)}


def stage_proposal(trade_id: str, category: str, steps: list[str], citations: list[str]) -> dict:
    """Insert a PENDING_APPROVAL row. This never touches the settlements table."""
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            cursor = conn.execute(
                """
                INSERT INTO proposals (trade_id, category, steps, citations, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING_APPROVAL', ?)
                """,
                (
                    trade_id,
                    category,
                    json.dumps(steps),
                    json.dumps(citations),
                    utc_now(),
                ),
            )
            conn.commit()
            proposal_id = cursor.lastrowid
        finally:
            conn.close()
    return {
        "ok": True,
        "status": "PENDING_APPROVAL",
        "proposal_id": proposal_id,
    }


def record_approval(proposal_id: int, reviewer: str) -> str:
    """Record the human review decision. Only the review node calls this.

    It is not an MCP tool, so a model cannot mint an approval_id.
    """
    import uuid

    approval_id = "APR-" + uuid.uuid4().hex[:16]
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            row = conn.execute(
                "SELECT id, status FROM proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise ToolRejected("NOT_FOUND", f"proposal {proposal_id} does not exist")
            if row["status"] != "PENDING_APPROVAL":
                raise ToolRejected(
                    "REFUSED",
                    f"proposal {proposal_id} is {row['status']}, not PENDING_APPROVAL",
                )
            conn.execute(
                """
                INSERT INTO approvals (approval_id, proposal_id, reviewer, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (approval_id, proposal_id, reviewer, utc_now()),
            )
            conn.commit()
        finally:
            conn.close()
    return approval_id


def apply_proposal(proposal_id: int, approval_id: str) -> dict:
    """Apply a staged proposal only when this approval_id was recorded for it."""
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            proposal = conn.execute(
                "SELECT * FROM proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if proposal is None:
                return {
                    "ok": False,
                    "status": "NOT_FOUND",
                    "error": f"proposal {proposal_id} does not exist",
                }
            approval = conn.execute(
                """
                SELECT approval_id FROM approvals
                WHERE approval_id = ? AND proposal_id = ?
                """,
                (approval_id, proposal_id),
            ).fetchone()
            if approval is None:
                return {
                    "ok": False,
                    "status": "REFUSED",
                    "error": "approval_id does not match an approval recorded for this proposal",
                }
            steps = json.loads(proposal["steps"])
            idempotency_key = compute_idempotency_key(
                proposal["trade_id"],
                proposal["category"],
                steps,
            )
            try:
                conn.execute(
                    """
                    INSERT INTO settlements
                        (idempotency_key, trade_id, category, status, timestamp)
                    VALUES (?, ?, ?, 'APPLIED', ?)
                    """,
                    (
                        idempotency_key,
                        proposal["trade_id"],
                        proposal["category"],
                        utc_now(),
                    ),
                )
                conn.execute(
                    """
                    UPDATE proposals
                    SET status = 'APPLIED', idempotency_key = ?
                    WHERE id = ?
                    """,
                    (idempotency_key, proposal_id),
                )
                conn.commit()
                status = "APPLIED"
            except sqlite3.IntegrityError:
                status = "DUPLICATE_SKIPPED"
            return {
                "ok": True,
                "status": status,
                "proposal_id": proposal_id,
                "idempotency_key": idempotency_key,
            }
        finally:
            conn.close()
