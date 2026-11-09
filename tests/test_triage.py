"""Unit tests that don't need AWS credentials or LM Studio.

All model and Bedrock calls are mocked.
"""
import asyncio

import pytest

# --- Test 1: Routing logic ---

def test_route_guardrail_blocked_to_reject():
    """If guardrail says BLOCKED, the graph should route to reject, not review."""
    state = {
        "exception": {"trade_id": "T-1"},
        "guardrail_action": "BLOCKED",
    }
    # Import the router function from the graph
    from app.graph import route_after_guardrail
    assert route_after_guardrail(state) == "reject"


def test_route_guardrail_pass_to_review():
    """If guardrail says PASS or MASKED, the graph should route to review."""
    state = {
        "exception": {"trade_id": "T-1"},
        "guardrail_action": "PASS",
    }
    from app.graph import route_after_guardrail
    assert route_after_guardrail(state) == "review"


def test_route_guardrail_masked_to_review():
    """MASKED should still go to review (not reject)."""
    state = {
        "exception": {"trade_id": "T-1"},
        "guardrail_action": "MASKED",
    }
    from app.graph import route_after_guardrail
    assert route_after_guardrail(state) == "review"


def test_route_review_approved_to_execute():
    """If human approves, execute the fix."""
    state = {"decision": "approved"}
    from app.graph import route_after_review
    assert route_after_review(state) == "execute"


def test_route_review_rejected_to_reject():
    """If human rejects, don't execute."""
    state = {"decision": "rejected"}
    from app.graph import route_after_review
    assert route_after_review(state) == "reject"


# --- Test 2: Idempotency guard ---

def test_idempotency_key_deterministic():
    """Same inputs must always produce the same key."""
    from app.nodes.execute import compute_idempotency_key
    key1 = compute_idempotency_key("T-100", "SSI_MISMATCH", ["contact counterparty"])
    key2 = compute_idempotency_key("T-100", "SSI_MISMATCH", ["contact counterparty"])
    assert key1 == key2


def test_idempotency_key_differs_by_trade():
    """Different trade IDs should produce different keys."""
    from app.nodes.execute import compute_idempotency_key
    key1 = compute_idempotency_key("T-100", "SSI_MISMATCH", ["fix"])
    key2 = compute_idempotency_key("T-200", "SSI_MISMATCH", ["fix"])
    assert key1 != key2


def test_idempotency_key_differs_by_fix():
    """Same trade, different fix steps → different key."""
    from app.nodes.execute import compute_idempotency_key
    key1 = compute_idempotency_key("T-100", "SSI_MISMATCH", ["fix A"])
    key2 = compute_idempotency_key("T-100", "SSI_MISMATCH", ["fix B"])
    assert key1 != key2


def test_idempotency_key_is_sha256_hex():
    from app.nodes.execute import compute_idempotency_key
    key = compute_idempotency_key("T-100", "SSI_MISMATCH", ["fix"])
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_execute_idempotency_duplicate_skipped(tmp_path, monkeypatch):
    """Second apply of the same approved proposal is skipped (idempotent)."""
    monkeypatch.setenv("SETTLEMENT_DB", str(tmp_path / "settlement.db"))
    monkeypatch.setenv("MCP_CLIENT", "triage-graph")
    from mcp_server.server import apply_fix, propose_fix
    from mcp_server.settlement import record_approval

    first = propose_fix(
        trade_id="T-1042",
        category="SSI_MISMATCH",
        steps=["contact counterparty"],
        citations=["RB-ssi"],
    )
    approval = record_approval(first["proposal_id"], "reviewer")
    applied = apply_fix(proposal_id=first["proposal_id"], approval_id=approval)
    assert applied["status"] == "APPLIED"

    again = apply_fix(proposal_id=first["proposal_id"], approval_id=approval)
    assert again["status"] == "DUPLICATE_SKIPPED"

    other = propose_fix(
        trade_id="T-1042",
        category="SSI_MISMATCH",
        steps=["different fix"],
        citations=["RB-ssi"],
    )
    other_approval = record_approval(other["proposal_id"], "reviewer")
    other_applied = apply_fix(proposal_id=other["proposal_id"], approval_id=other_approval)
    assert other_applied["status"] == "APPLIED"


# --- Test 3: Classify schema ---

def test_classification_valid_category():
    """Valid category values should parse."""
    from app.nodes.classify import Classification
    obj = Classification(
        category="SSI_MISMATCH",
        confidence=0.95,
        reason="Scrip code mismatch"
    )
    assert obj.category == "SSI_MISMATCH"
    assert 0.0 <= obj.confidence <= 1.0


def test_classification_invalid_category():
    """Invalid category should fail validation."""
    from pydantic import ValidationError

    from app.nodes.classify import Classification
    with pytest.raises(ValidationError):
        # Construct via model_validate to trigger runtime validation
        Classification.model_validate({
            "category": "NOT_A_REAL_CATEGORY",
            "confidence": 0.95,
            "reason": "test"
        })


def test_classification_confidence_range():
    """Confidence must be 0-1."""
    from pydantic import ValidationError

    from app.nodes.classify import Classification
    with pytest.raises(ValidationError):
        Classification(
            category="SSI_MISMATCH",
            confidence=1.5,
            reason="test"
        )


# --- Test 4: Stub guardrail behavior ---

def test_stub_guardrail_passes_clean_draft():
    """A draft with no PII or investment advice should PASS."""
    from app.nodes.guardrail import apply_stub_guardrail
    result = apply_stub_guardrail("Contact counterparty to correct scrip code.")
    assert result["action"] == "PASS"
    assert result["masked_entities"] == []


def test_stub_guardrail_masks_pii():
    """PII in the draft should be detected and masked."""
    from app.nodes.guardrail import apply_stub_guardrail
    draft = "Contact John Doe at john@example.com or 555-123-4567."
    result = apply_stub_guardrail(draft)
    assert result["action"] == "MASKED"
    assert "EMAIL" in result["masked_entities"]
    assert "PHONE" in result["masked_entities"]


def test_stub_guardrail_blocks_investment_advice():
    """Investment advice phrases should be BLOCKED."""
    from app.nodes.guardrail import apply_stub_guardrail
    draft = "Buy more shares of the underlying asset."
    result = apply_stub_guardrail(draft)
    assert result["action"] == "BLOCKED"
    assert "Investment advice" in result["blocked_policies"]


# --- Test 5: Graph wiring ---

async def _build_graph_and_get_nodes():
    from app.graph import build_graph
    graph, conn = build_graph()
    nodes = set(graph.nodes.keys())
    await conn.close()
    return nodes

def test_graph_has_expected_nodes():
    """Graph should contain all expected nodes."""
    import asyncio
    node_names = asyncio.run(_build_graph_and_get_nodes())
    expected = {
        "input_guardrail", "classify", "retrieve", "draft_fix",
        "guardrail", "review", "execute", "reject"
    }
    assert expected.issubset(node_names)
