"""MCP client used by graph nodes.

Local development launches mcp_server/server.py over stdio. Set
MCP_TRANSPORT=streamable-http and MCP_SERVER_URL=http://127.0.0.1:8000/mcp
to call a server that was started with streamable HTTP instead.

WRITE tools are called from graph nodes at fixed points. They are not
returned by read_tools() and must not be passed to bind_tools. A model that
can choose propose_fix or apply_fix can stage or apply a fix without the
human review step. The graph order is the control: draft_fix stages the
proposal, review records the approval, and only execute calls apply_fix.
"""
import json
import os
import sys
from pathlib import Path

from app.observability import start_span

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "mcp_server" / "server.py"
GRAPH_CLIENT = "triage-graph"

_HTTP_TRANSPORTS = {"http", "streamable-http", "streamable_http"}


def build_mcp_config() -> dict:
    """Connection config for the triage tool server."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport in _HTTP_TRANSPORTS:
        url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
        return {
            "mcpServers": {
                "triage-tools": {
                    "url": url,
                    "transport": "streamable-http",
                    "headers": {"X-MCP-Client": GRAPH_CLIENT},
                }
            }
        }
    env = dict(os.environ)
    env["MCP_CLIENT"] = GRAPH_CLIENT
    return {
        "mcpServers": {
            "triage-tools": {
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "cwd": str(ROOT),
                "env": env,
                "transport": "stdio",
                "keep_alive": True,
            }
        }
    }


def _parse_text(text: str) -> dict:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "status": "ERROR", "error": text}
    if isinstance(parsed, dict):
        result = parsed.get("result")
        if isinstance(result, dict) and list(parsed.keys()) == ["result"]:
            return result
        return parsed
    return {"ok": False, "status": "ERROR", "error": text}


def _unwrap(raw):
    """Pull the tool's dict out of a LangChain MCP tool result."""
    if isinstance(raw, tuple) and len(raw) == 2:
        content, artifact = raw
        if isinstance(artifact, dict) and isinstance(artifact.get("structured_content"), dict):
            data = artifact["structured_content"]
            result = data.get("result")
            if isinstance(result, dict) and list(data.keys()) == ["result"]:
                return result
            return data
        raw = content
    if isinstance(raw, list):
        return _parse_text(_content_text(raw))
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_text(raw)
    return {"ok": False, "status": "ERROR", "error": "unreadable MCP tool result"}


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


async def _invoke(name: str, arguments: dict) -> dict:
    import warnings

    warnings.filterwarnings(
        "ignore",
        message="`langchain.mcp` is in beta.*",
        category=UserWarning,
    )
    from langchain.mcp import MCPAdapter

    config = build_mcp_config()
    async with MCPAdapter(config) as adapter:
        tools = await adapter.list_tools()
        match = next((tool for tool in tools if tool.name == name), None)
        if match is None:
            return {"ok": False, "status": "NOT_FOUND", "error": f"MCP server has no tool {name}"}
        raw = await match.ainvoke(arguments)
    return _unwrap(raw)


async def call_tool(name: str, arguments: dict) -> dict:
    """Call one MCP tool and record it as a Langfuse tool span."""
    span, _client = start_span(f"mcp.{name}", as_type="tool", input=arguments)
    try:
        result = await _invoke(name, arguments)
        if span is not None:
            span.update(output={"status": result.get("status"), "ok": result.get("ok")})
        return result
    except Exception as exc:
        if span is not None:
            span.update(level="ERROR", status_message=str(exc))
        raise
    finally:
        if span is not None:
            span.end()


async def read_tools() -> list:
    """READ tools only. Do not add WRITE tools from this list onto a model."""
    from langchain.mcp import MCPAdapter

    async with MCPAdapter(build_mcp_config()) as adapter:
        tools = await adapter.list_tools()
    return [
        tool
        for tool in tools
        if tool.name in ("settlement_lookup", "search_runbooks")
    ]
