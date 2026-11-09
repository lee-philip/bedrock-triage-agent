"""Seed fictional trades into data/settlement.db.

Usage: python scripts/seed_settlement.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.db import _lock, connect, db_path, ensure_schema

TRADES = [
    ("T-1042", "Fictional Bank AG", 1500000, "USD", "2026-11-05", "EXCEPTION", "DEUTDEFFXXX / DE89370400440532013000"),
    ("T-2087", "Northwind Custody", 250000, "EUR", "2026-11-06", "EXCEPTION", "BNPAFRPPXXX"),
    ("T-3314", "Harbor Securities", 98000, "USD", "2026-11-04", "EXCEPTION", "CHASUS33XXX"),
    ("T-9001", "Example Trust Co", 410000, "GBP", "2026-11-07", "EXCEPTION", "BARCGB22XXX"),
    ("T-9002", "Sample Broker LLC", 72500, "USD", "2026-11-08", "EXCEPTION", "CITIUS33XXX"),
    ("T-9003", "Placeholder Asset Mgmt", 1200000, "USD", "2026-11-03", "EXCEPTION", "BOFAUS3NXXX"),
    ("T-9999", "PII Fixture Bank", 1000, "USD", "2026-11-01", "EXCEPTION", "TESTUS33XXX"),
]


def seed() -> None:
    with _lock:
        conn = connect()
        try:
            ensure_schema(conn)
            conn.executemany(
                """
                INSERT INTO trades
                    (trade_id, counterparty, expected_amount, currency, settlement_date, status, ssi)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    counterparty = excluded.counterparty,
                    expected_amount = excluded.expected_amount,
                    currency = excluded.currency,
                    settlement_date = excluded.settlement_date,
                    status = excluded.status,
                    ssi = excluded.ssi
                """,
                TRADES,
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        finally:
            conn.close()
    print(f"Seeded {len(TRADES)} trades ({count} rows now in {db_path()})")


if __name__ == "__main__":
    seed()
