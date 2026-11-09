"""Retrieve relevant runbook sections through the MCP search_runbooks tool."""
from app.tools import call_tool


async def retrieve(state):
    """Retrieve relevant runbook sections based on the exception category and details."""
    category = state.get("category", "UNKNOWN")
    exception = state["exception"]
    trade_id = exception.get("trade_id", "")

    query = f"{category} trade settlement exception"
    if exception.get("error_message"):
        query += f" {exception['error_message']}"
    if exception.get("notes"):
        query += f" {exception['notes']}"

    trade = await call_tool("settlement_lookup", {"trade_id": trade_id})
    found = await call_tool(
        "search_runbooks",
        {"query": query, "category": category, "k": 3},
    )
    if not found.get("ok"):
        raise RuntimeError(found.get("error", "search_runbooks failed"))

    chunks = found.get("chunks", [])
    chunk_ids = found.get("chunk_ids", [])
    print(f"\n=== RETRIEVE ===")
    print(f"Retrieved {len(chunks)} runbook chunks: {', '.join(chunk_ids)}")
    return {
        "runbook_chunks": chunks,
        "retrieved_chunk_ids": chunk_ids,
        "trade_record": trade.get("trade"),
    }
