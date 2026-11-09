# MCP tools

MCP (Model Context Protocol) is a standard way for an application to call tools that live in a separate process. The triage graph is the client. `mcp_server/server.py` is the server. The graph does not import the database or the FAISS index itself. It asks the server to do that, and the server decides whether the caller is allowed.

The official Python package is `mcp`. In SDK v2 the server class that used to be called FastMCP is `MCPServer`:

```python
from mcp.server import MCPServer as FastMCP

mcp = FastMCP("triage-tools")
```

`mcp.run()` chooses the transport:

| Transport | How the graph reaches it | When |
| --- | --- | --- |
| `stdio` | The graph starts `python -m mcp_server.server` and talks on stdin/stdout | Local development. This is the default. |
| `streamable-http` | The server listens on a port. The graph sends HTTP to `MCP_SERVER_URL`. | A server that is already running. |
| `sse` | Older HTTP transport | Do not use it for anything new. Streamable HTTP replaced it. |

The LangChain client is `langchain.mcp.MCPAdapter` (`pip install "langchain[mcp]"`). The older `langchain-mcp-adapters` package is no longer maintained. `app/tools.py` builds an `MCPConfig`: a script command for stdio, or a URL for streamable HTTP.

## Tools

| Tool | Access | What it does | Who may call it |
| --- | --- | --- | --- |
| `settlement_lookup` | READ | Returns one fictional trade from `data/settlement.db` | `triage-graph`, `readonly` |
| `search_runbooks` | READ | Searches the Phase 3 FAISS index. `k` above 5 is capped at 5 | `triage-graph`, `readonly` |
| `propose_fix` | WRITE | Inserts a `PENDING_APPROVAL` row. Does not execute anything | `triage-graph` only |
| `apply_fix` | WRITE | Writes the simulated settlement table, only with a matching human approval. Repeating it returns `DUPLICATE_SKIPPED` | `triage-graph` only |

The graph calls them from fixed nodes:

- `retrieve` calls `settlement_lookup` and `search_runbooks`.
- `draft_fix` calls `propose_fix` after the model drafts the steps.
- `review` records an `approval_id` when the human approves. That write is not a tool. A model cannot mint an approval.
- `execute` calls `apply_fix` with that `approval_id`.

A rejected review routes to `reject` and never reaches `execute`.

WRITE tools are not passed to `bind_tools`. If the model could choose `apply_fix`, it could skip the human. The node order is what forces staging, then approval, then apply.

Each tool is annotated with MCP hints: READ tools set `read_only_hint=True`. `apply_fix` sets `idempotent_hint=True` and `destructive_hint=False`. Those hints tell a client what the tool does. The server does not trust them. The allowlist is what actually blocks a call.

## How the controls are enforced

**Schemas.** Each argument is a typed parameter with a description, so the SDK publishes a JSON Schema. `trade_id` is a string, `k` is an integer, `steps` is a list of strings.

**Validation.** Before a tool runs, the server checks `trade_id` against `^T-\d{4,6}$`, `category` against the seven triage categories, and length limits on text fields. A bad value returns `VALIDATION_ERROR` and does not touch the settlement table.

**Allowlist.** `mcp_server/config.py` lists which tools each client may call. The stdio child is started with `MCP_CLIENT=triage-graph`. An HTTP client sends the same name in the `X-MCP-Client` header. Any other client, including one that sends no name, is `ALLOWLIST_REJECTED`.

**Approvals.** `apply_fix` loads the proposal and looks for a row in `approvals` with that `approval_id` and the same `proposal_id`. The review node is the only writer of that table, and it writes only after the human approves. A missing or mismatched approval returns `REFUSED`.

**Idempotency.** The key is the Phase 5 SHA-256 of trade id, category, and fix steps. `settlements.idempotency_key` is unique. The second apply of the same fix returns `DUPLICATE_SKIPPED` and does not insert another row.

**Audit.** Every call, including rejected ones, inserts one row into `mcp_audit`: timestamp, client, tool, arguments, `allowed` or `rejected`, result status, and latency. Arguments are masked first. Emails and phone numbers are stored as `[REDACTED]`. The table is insert-only.

## Run it

Seed the fictional trades, then start the server the way the graph does:

```bash
python scripts/seed_settlement.py
MCP_CLIENT=triage-graph python -m mcp_server.server
```

That process waits on stdin. To listen instead:

```bash
MCP_CLIENT=triage-graph MCP_TRANSPORT=streamable-http python -m mcp_server.server
```

Point the graph at it with `MCP_TRANSPORT=streamable-http` and `MCP_SERVER_URL=http://127.0.0.1:8000/mcp`.

## Inspect it

The MCP Inspector is `@modelcontextprotocol/inspector`. It needs Node 22.19.0 or newer. From the repo root, with a client name the allowlist accepts:

```bash
MCP_CLIENT=triage-graph npx @modelcontextprotocol/inspector python -m mcp_server.server
```

That opens the web UI and launches this server over stdio. The Tools tab lists the four tools and builds a form from each input schema.

To list the tools and exit:

```bash
MCP_CLIENT=triage-graph npx @modelcontextprotocol/inspector --cli python -m mcp_server.server --method tools/list
```

The SDK's own launcher does the same thing:

```bash
MCP_CLIENT=triage-graph uv run mcp dev mcp_server/server.py
```
