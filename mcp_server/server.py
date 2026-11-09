"""Triage MCP server.

SDK v2 renamed FastMCP to MCPServer (from mcp.server import MCPServer).
The constructor call below is that class. Transports are stdio, the local
default, and streamable-http for a listening port. SSE still runs but the
protocol replaced it with streamable HTTP.
"""
import os
from typing import Annotated, Any

from mcp.server import MCPServer as FastMCP
from mcp.server.mcpserver.context import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_server.governance import cap_k, guard
from mcp_server.runbooks import search_index
from mcp_server.settlement import apply_proposal, lookup_trade, stage_proposal

mcp = FastMCP("triage-tools")

_READ = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_STAGE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
_APPLY = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def _client_name(ctx: Context | None) -> str:
    """stdio clients are named by MCP_CLIENT. HTTP clients send X-MCP-Client."""
    if ctx is not None:
        try:
            headers = ctx.request_context.headers or {}
        except Exception:
            headers = {}
        for key, value in headers.items():
            if key.lower() == "x-mcp-client" and value:
                return value
    return os.environ.get("MCP_CLIENT", "")


@mcp.tool(annotations=_READ)
def settlement_lookup(
    trade_id: Annotated[str, Field(description="Fictional trade id, pattern T- followed by 4 to 6 digits.")],
    ctx: Context | None = None,
) -> dict[str, Any]:
    """READ. Return the fictional trade record for trade_id from settlement.db."""
    arguments = {"trade_id": trade_id}
    return guard(
        "settlement_lookup",
        _client_name(ctx),
        arguments,
        lambda: lookup_trade(trade_id),
    )


@mcp.tool(annotations=_READ)
def search_runbooks(
    query: Annotated[str, Field(description="Text to search in the runbook index. At most 500 characters.")],
    category: Annotated[str, Field(description="Exception category from the fixed taxonomy.")],
    k: Annotated[int, Field(description="Maximum chunks to return. Values above 5 are capped at 5.", ge=1)] = 3,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """READ. Search the Phase 3 FAISS runbook index and return up to k chunks."""
    arguments = {"query": query, "category": category, "k": k}
    return guard(
        "search_runbooks",
        _client_name(ctx),
        arguments,
        lambda: search_index(query, category, cap_k(k)),
    )


@mcp.tool(annotations=_STAGE)
def propose_fix(
    trade_id: Annotated[str, Field(description="Fictional trade id, pattern T- followed by 4 to 6 digits.")],
    category: Annotated[str, Field(description="Exception category from the fixed taxonomy.")],
    steps: Annotated[list[str], Field(description="Fix steps to stage. Nothing is executed.")],
    citations: Annotated[list[str], Field(description="Runbook chunk ids that support the steps.")],
    ctx: Context | None = None,
) -> dict[str, Any]:
    """WRITE. Stage a PENDING_APPROVAL proposal. Does not execute the fix."""
    arguments = {
        "trade_id": trade_id,
        "category": category,
        "steps": steps,
        "citations": citations,
    }
    return guard(
        "propose_fix",
        _client_name(ctx),
        arguments,
        lambda: stage_proposal(trade_id, category, steps, citations),
    )


@mcp.tool(annotations=_APPLY)
def apply_fix(
    proposal_id: Annotated[int, Field(description="Id of a PENDING_APPROVAL proposal.", ge=1)],
    approval_id: Annotated[str, Field(description="Approval id recorded by the human review step for this proposal.")],
    ctx: Context | None = None,
) -> dict[str, Any]:
    """WRITE. Apply a staged proposal to the simulated settlement table.

    Refuses unless approval_id was recorded for this proposal. A repeated call
    with the same fix is DUPLICATE_SKIPPED via the idempotency key.
    """
    arguments = {"proposal_id": proposal_id, "approval_id": approval_id}
    return guard(
        "apply_fix",
        _client_name(ctx),
        arguments,
        lambda: apply_proposal(proposal_id, approval_id),
    )


if __name__ == "__main__":
    # stdio is the local default. Set MCP_TRANSPORT=streamable-http to listen.
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport in ("http", "streamable-http", "streamable_http"):
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "8000")),
        )
    else:
        mcp.run(transport="stdio")
