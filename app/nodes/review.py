"""Human-in-the-loop review node.

Builds a review payload from the current state and calls interrupt().
On resume, receives the reviewer's decision dict.

IMPORTANT: No side effects before interrupt() — the node re-runs from
the top when resumed.
"""
from langgraph.types import interrupt

from mcp_server.settlement import record_approval


async def review(state):
    """Human-in-the-loop review. Interrupts and waits for a decision."""
    # Build the review payload to show the reviewer
    payload = {
        "trade_id": state["exception"].get("trade_id", "N/A"),
        "category": state.get("category", "UNKNOWN"),
        "confidence": state.get("confidence"),
        "root_cause": state.get("root_cause", ""),
        "proposed_fix_steps": state.get("proposed_fix_steps", []),
        "citations": state.get("citations", []),
        "risk_notes": state.get("risk_notes", ""),
        "draft": state.get("draft", ""),
        "guardrail_action": state.get("guardrail_action", ""),
    }

    # Pause execution and wait for the reviewer
    decision_dict = interrupt(payload)

    # decision_dict is the resumed value: {decision, reviewer, comment}
    # Recording the approval happens after interrupt(), so a resume does not
    # stage a second approval while the node replays from the top.
    decision = decision_dict.get("decision", "rejected")
    reviewer = decision_dict.get("reviewer", "unknown")
    result = {
        "decision": decision,
        "reviewer": reviewer,
        "reviewer_comment": decision_dict.get("comment", ""),
    }
    if decision == "approved":
        proposal_id = state.get("proposal_id")
        if proposal_id is None:
            raise RuntimeError("Cannot approve a fix that was never staged")
        result["approval_id"] = record_approval(int(proposal_id), reviewer)
    return result