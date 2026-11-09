"""Tool registry and per-client allowlist.

READ tools only look up data. WRITE tools change the simulated settlement
database. The graph client may call every tool. A readonly client may not.
"""

CATEGORIES = (
    "SSI_MISMATCH",
    "MISSING_COUNTERPARTY_BIC",
    "PRICE_TOLERANCE_BREAK",
    "SETTLEMENT_DATE_MISMATCH",
    "INSUFFICIENT_CASH",
    "QUANTITY_MISMATCH",
    "UNKNOWN",
)

# Access class advertised by the registry. Annotations on each tool mirror this.
TOOL_ACCESS = {
    "settlement_lookup": "READ",
    "search_runbooks": "READ",
    "propose_fix": "WRITE",
    "apply_fix": "WRITE",
}

CLIENT_ALLOWLIST = {
    "triage-graph": (
        "settlement_lookup",
        "search_runbooks",
        "propose_fix",
        "apply_fix",
    ),
    "readonly": (
        "settlement_lookup",
        "search_runbooks",
    ),
}

TRADE_ID_PATTERN = r"^T-\d{4,6}$"
MAX_QUERY_LEN = 500
MAX_TEXT_LEN = 500
MAX_LIST_ITEMS = 20
MAX_APPROVAL_ID_LEN = 64
MAX_K = 5
