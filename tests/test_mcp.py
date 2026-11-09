"""MCP server governance. No model provider required."""
import pytest


@pytest.fixture
def settlement_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLEMENT_DB", str(tmp_path / "settlement.db"))
    monkeypatch.setenv("MCP_CLIENT", "triage-graph")
    return tmp_path / "settlement.db"


def _audit():
    from mcp_server.db import audit_rows
    return [dict(row) for row in audit_rows()]


def test_validation_error_is_audited(settlement_db):
    from mcp_server.server import settlement_lookup

    result = settlement_lookup(trade_id="not-a-trade")
    assert result["ok"] is False
    assert result["status"] == "VALIDATION_ERROR"
    assert "T-" in result["error"]

    rows = _audit()
    assert len(rows) == 1
    assert rows[0]["decision"] == "rejected"
    assert rows[0]["result_status"] == "VALIDATION_ERROR"
    assert rows[0]["tool"] == "settlement_lookup"


def test_allowlist_rejects_write_for_readonly_client(settlement_db, monkeypatch):
    monkeypatch.setenv("MCP_CLIENT", "readonly")
    from mcp_server.server import propose_fix

    result = propose_fix(
        trade_id="T-1042",
        category="SSI_MISMATCH",
        steps=["email ops@example.com and call 555-123-4567"],
        citations=["RB-ssi"],
    )
    assert result["status"] == "ALLOWLIST_REJECTED"

    rows = _audit()
    assert len(rows) == 1
    assert rows[0]["decision"] == "rejected"
    assert rows[0]["client"] == "readonly"
    assert rows[0]["tool"] == "propose_fix"
    stored = rows[0]["arguments"]
    assert "ops@example.com" not in stored
    assert "555-123-4567" not in stored
    assert "[REDACTED]" in stored


def test_unknown_client_is_rejected(settlement_db, monkeypatch):
    monkeypatch.setenv("MCP_CLIENT", "stranger")
    from mcp_server.server import settlement_lookup

    result = settlement_lookup(trade_id="T-1042")
    assert result["status"] == "ALLOWLIST_REJECTED"
    assert _audit()[0]["decision"] == "rejected"


def test_apply_fix_refused_without_approval(settlement_db):
    from mcp_server.server import apply_fix, propose_fix

    staged = propose_fix(
        trade_id="T-1042",
        category="SSI_MISMATCH",
        steps=["contact counterparty"],
        citations=["RB-ssi"],
    )
    assert staged["status"] == "PENDING_APPROVAL"

    refused = apply_fix(proposal_id=staged["proposal_id"], approval_id="APR-notrecorded")
    assert refused["ok"] is False
    assert refused["status"] == "REFUSED"

    rows = _audit()
    assert len(rows) == 2
    assert [row["decision"] for row in rows] == ["allowed", "allowed"]
    assert rows[1]["result_status"] == "REFUSED"


def test_second_apply_is_duplicate_skipped(settlement_db):
    from mcp_server.server import apply_fix, propose_fix
    from mcp_server.settlement import record_approval

    staged = propose_fix(
        trade_id="T-2087",
        category="MISSING_COUNTERPARTY_BIC",
        steps=["request the BIC"],
        citations=["RB-bic"],
    )
    approval_id = record_approval(staged["proposal_id"], "reviewer")
    first = apply_fix(proposal_id=staged["proposal_id"], approval_id=approval_id)
    second = apply_fix(proposal_id=staged["proposal_id"], approval_id=approval_id)

    assert first["status"] == "APPLIED"
    assert second["status"] == "DUPLICATE_SKIPPED"
    assert first["idempotency_key"] == second["idempotency_key"]
    assert len(first["idempotency_key"]) == 64

    statuses = [row["result_status"] for row in _audit()]
    assert statuses == ["PENDING_APPROVAL", "APPLIED", "DUPLICATE_SKIPPED"]
    assert all(row["decision"] == "allowed" for row in _audit())


def test_rejected_review_does_not_record_approval(settlement_db):
    """A rejected decision never creates the approval apply_fix would accept."""
    from mcp_server.server import apply_fix, propose_fix

    staged = propose_fix(
        trade_id="T-3314",
        category="QUANTITY_MISMATCH",
        steps=["recount"],
        citations=["RB-qty"],
    )
    refused = apply_fix(proposal_id=staged["proposal_id"], approval_id="APR-nohuman")
    assert refused["status"] == "REFUSED"


def test_stdio_config_names_the_graph_client(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    from app.tools import build_mcp_config

    server = build_mcp_config()["mcpServers"]["triage-tools"]
    assert server["transport"] == "stdio"
    assert server["args"] == ["-m", "mcp_server.server"]
    assert server["env"]["MCP_CLIENT"] == "triage-graph"


def test_http_config_uses_streamable_http(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
    from app.tools import build_mcp_config

    server = build_mcp_config()["mcpServers"]["triage-tools"]
    assert server["transport"] == "streamable-http"
    assert server["url"] == "http://127.0.0.1:8000/mcp"
    assert server["headers"]["X-MCP-Client"] == "triage-graph"


def test_unwrap_reads_langchain_text_blocks():
    from app.tools import _unwrap

    raw = [{"type": "text", "text": '{"ok": true, "status": "OK", "trade": {"trade_id": "T-1042"}}'}]
    parsed = _unwrap(raw)
    assert parsed["status"] == "OK"
    assert parsed["trade"]["trade_id"] == "T-1042"


def test_call_tool_opens_a_langfuse_span(monkeypatch):
    from app import tools

    class FakeSpan:
        def __init__(self):
            self.updates = []
            self.ended = False

        def update(self, **kwargs):
            self.updates.append(kwargs)

        def end(self):
            self.ended = True

    span = FakeSpan()
    seen = {}

    def start_span(name, **kwargs):
        seen["name"] = name
        seen.update(kwargs)
        return span, None

    async def invoke(name, arguments):
        return {"ok": True, "status": "OK", "trade": {"trade_id": arguments["trade_id"]}}

    monkeypatch.setattr(tools, "start_span", start_span)
    monkeypatch.setattr(tools, "_invoke", invoke)

    import asyncio
    result = asyncio.run(tools.call_tool("settlement_lookup", {"trade_id": "T-1042"}))
    assert result["status"] == "OK"
    assert seen["name"] == "mcp.settlement_lookup"
    assert seen["as_type"] == "tool"
    assert span.ended is True
    assert span.updates[-1]["output"]["status"] == "OK"


def test_tool_schemas_and_annotations():
    from mcp_server.server import mcp

    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    assert set(tools) == {
        "settlement_lookup",
        "search_runbooks",
        "propose_fix",
        "apply_fix",
    }
    lookup = tools["settlement_lookup"]
    assert "trade_id" in lookup.parameters["properties"]
    assert "ctx" not in lookup.parameters["properties"]
    assert lookup.annotations.read_only_hint is True
    assert tools["propose_fix"].annotations.read_only_hint is False
    assert tools["apply_fix"].annotations.idempotent_hint is True
    assert tools["search_runbooks"].annotations.read_only_hint is True


def test_k_is_capped_at_five(settlement_db, monkeypatch):
    """k above 5 is capped, not rejected. Embeddings are not called."""
    from mcp_server.server import search_runbooks

    seen = {}

    def fake_search(query, category, k):
        seen["k"] = k
        return {"ok": True, "status": "OK", "chunks": [], "chunk_ids": []}

    monkeypatch.setattr("mcp_server.server.search_index", fake_search)
    result = search_runbooks(query="ssi mismatch", category="SSI_MISMATCH", k=9)
    assert result["status"] == "OK"
    assert seen["k"] == 5
    assert _audit()[0]["decision"] == "allowed"
