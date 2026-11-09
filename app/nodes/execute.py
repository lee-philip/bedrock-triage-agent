"""Execute node. Applies an approved proposal through the MCP apply_fix tool.

The settlement write and the idempotency key live in the MCP server. This
node only runs after review routes an approval here. A rejected case goes to
the reject node and never calls apply_fix.
"""
from app.tools import call_tool
from mcp_server.db import DEFAULT_DB
from mcp_server.settlement import compute_idempotency_key

# Older callers imported this path from the execute node. The server reads
# SETTLEMENT_DB, or this file when that variable is unset.
SETTLEMENT_DB_PATH = DEFAULT_DB


async def execute(state):
    """Apply the approved fix to the simulated settlement table."""
    proposal_id = state.get("proposal_id")
    approval_id = state.get("approval_id")
    if proposal_id is None or not approval_id:
        return {
            "executed": False,
            "idempotency_key": None,
            "settlement_result": "REFUSED",
        }

    # apply_fix is a WRITE tool. The node calls it here. It is not offered to
    # the model with bind_tools, so the model cannot apply a fix on its own.
    result = await call_tool(
        "apply_fix",
        {"proposal_id": int(proposal_id), "approval_id": approval_id},
    )
    status = result.get("status", "ERROR")
    return {
        "executed": status in ("APPLIED", "DUPLICATE_SKIPPED"),
        "idempotency_key": result.get("idempotency_key"),
        "settlement_result": status,
    }
