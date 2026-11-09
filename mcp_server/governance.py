"""Input checks, client allowlist, and PII masking for MCP tool calls."""
import re
import time
from collections.abc import Callable
from typing import Any

from mcp_server.config import (
    CATEGORIES,
    CLIENT_ALLOWLIST,
    MAX_APPROVAL_ID_LEN,
    MAX_K,
    MAX_LIST_ITEMS,
    MAX_QUERY_LEN,
    MAX_TEXT_LEN,
    TOOL_ACCESS,
    TRADE_ID_PATTERN,
)
from mcp_server.db import write_audit

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
_TRADE_ID = re.compile(TRADE_ID_PATTERN)
_APPROVAL_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class ToolRejected(Exception):
    """A call that must not run. The audit row is written by the caller."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def mask_pii(value: Any) -> Any:
    """Replace emails and phone numbers before they are written to the audit log."""
    if isinstance(value, str):
        masked = _EMAIL.sub("[REDACTED]", value)
        return _PHONE.sub("[REDACTED]", masked)
    if isinstance(value, dict):
        return {key: mask_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    return value


def client_is_allowed(client: str, tool: str) -> bool:
    allowed = CLIENT_ALLOWLIST.get(client, ())
    return tool in allowed


def validate_arguments(tool: str, arguments: dict) -> None:
    """Reject arguments that are the wrong shape. Raises ToolRejected."""
    if tool in ("settlement_lookup", "propose_fix"):
        _require_trade_id(arguments.get("trade_id"))
    if tool in ("search_runbooks", "propose_fix"):
        _require_category(arguments.get("category"))
    if tool == "search_runbooks":
        _require_text("query", arguments.get("query"), MAX_QUERY_LEN)
        _require_k(arguments.get("k", 3))
    if tool == "propose_fix":
        _require_text_list("steps", arguments.get("steps"))
        _require_text_list("citations", arguments.get("citations"))
    if tool == "apply_fix":
        proposal_id = arguments.get("proposal_id")
        if not isinstance(proposal_id, int) or isinstance(proposal_id, bool) or proposal_id < 1:
            raise ToolRejected("VALIDATION_ERROR", "proposal_id must be a positive integer")
        approval_id = arguments.get("approval_id")
        if not isinstance(approval_id, str) or not _APPROVAL_ID.match(approval_id):
            raise ToolRejected(
                "VALIDATION_ERROR",
                "approval_id must be 1-64 letters, digits, underscores, or hyphens",
            )
        if len(approval_id) > MAX_APPROVAL_ID_LEN:
            raise ToolRejected("VALIDATION_ERROR", "approval_id is too long")


def _require_trade_id(trade_id: Any) -> None:
    if not isinstance(trade_id, str) or not _TRADE_ID.match(trade_id):
        raise ToolRejected(
            "VALIDATION_ERROR",
            "trade_id must match ^T-\\d{4,6}$ (for example T-1042)",
        )


def _require_category(category: Any) -> None:
    if category not in CATEGORIES:
        allowed = ", ".join(CATEGORIES)
        raise ToolRejected("VALIDATION_ERROR", f"category must be one of: {allowed}")


def _require_text(name: str, value: Any, limit: int) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ToolRejected("VALIDATION_ERROR", f"{name} must be a non-empty string")
    if len(value) > limit:
        raise ToolRejected("VALIDATION_ERROR", f"{name} must be at most {limit} characters")


def _require_text_list(name: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ToolRejected("VALIDATION_ERROR", f"{name} must be a non-empty list of strings")
    if len(value) > MAX_LIST_ITEMS:
        raise ToolRejected("VALIDATION_ERROR", f"{name} must have at most {MAX_LIST_ITEMS} items")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ToolRejected("VALIDATION_ERROR", f"each {name} item must be a non-empty string")
        if len(item) > MAX_TEXT_LEN:
            raise ToolRejected(
                "VALIDATION_ERROR",
                f"each {name} item must be at most {MAX_TEXT_LEN} characters",
            )


def _require_k(k: Any) -> None:
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ToolRejected("VALIDATION_ERROR", "k must be an integer >= 1")


def cap_k(k: int) -> int:
    """search_runbooks never returns more than MAX_K chunks."""
    return min(k, MAX_K)


def guard(tool: str, client: str, arguments: dict, fn: Callable[[], dict]) -> dict:
    """Run allowlist and validation, then the tool. Always writes an audit row."""
    started = time.perf_counter()
    masked = mask_pii(arguments)
    try:
        if tool not in TOOL_ACCESS:
            raise ToolRejected("VALIDATION_ERROR", f"unknown tool {tool}")
        if not client_is_allowed(client, tool):
            raise ToolRejected(
                "ALLOWLIST_REJECTED",
                f"client {client or '(none)'} may not call {tool}",
            )
        validate_arguments(tool, arguments)
        result = fn()
        status = str(result.get("status", "OK"))
        _audit(client, tool, masked, "allowed", status, started)
        return result
    except ToolRejected as exc:
        _audit(client, tool, masked, "rejected", exc.status, started)
        return {"ok": False, "status": exc.status, "error": exc.message}


def _audit(client, tool, arguments, decision, status, started) -> None:
    elapsed_ms = (time.perf_counter() - started) * 1000
    write_audit(client, tool, arguments, decision, status, elapsed_ms)
