import operator
from typing import Any, TypedDict, Annotated, List, Dict, Optional


class TriageState(TypedDict):
    exception: Dict[str, Any]
    run_id: str
    category: Optional[str]
    confidence: Optional[float]
    reason: Optional[str]
    runbook_chunks: List[Dict[str, Any]]
    draft: Optional[str]
    root_cause: Optional[str]
    proposed_fix_steps: List[str]
    citations: List[str]
    risk_notes: Optional[str]
    guardrail_action: Optional[str]
    decision: Optional[str]
    reviewer: Optional[str]
    reviewer_comment: Optional[str]
    executed: bool
    idempotency_key: Optional[str]
    settlement_result: Optional[str]
    audit: Annotated[List[Dict[str, Any]], operator.add]
    input_tokens: int
    output_tokens: int
    prompt_name: Optional[str]
    prompt_version: Optional[str]
    langfuse_trace_id: Optional[str]