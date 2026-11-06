"""Draft fix recommendation based on retrieved runbook sections."""
from pydantic import BaseModel, Field
from typing import List, Optional

from app.llm import get_chat_model


class FixDraft(BaseModel):
    """Structured fix draft with citations."""
    root_cause: str = Field(description="Likely root cause of the exception")
    proposed_fix_steps: List[str] = Field(description="Step-by-step fix instructions")
    citations: List[str] = Field(description="Runbook chunk IDs that support this recommendation")
    risk_notes: Optional[str] = Field(default=None, description="Risks or considerations if any")


async def draft_fix(state):
    """Draft a fix based on retrieved runbook sections."""
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(FixDraft)

    category = state.get("category", "UNKNOWN")
    exception = state["exception"]
    runbook_chunks = state.get("runbook_chunks", [])

    # Format retrieved chunks for prompt
    chunks_text = ""
    for i, chunk in enumerate(runbook_chunks):
        chunks_text += f"[{chunk['id']}] {chunk['heading']}\n{chunk['content']}\n\n"

    prompt = f"""You are a settlement exception triage specialist. Based on the retrieved runbook excerpts below, draft a fix recommendation for the following exception.

Exception Category: {category}
Trade ID: {exception.get("trade_id", "N/A")}
Error: {exception.get("error_message", "N/A")}

Use only the runbook excerpts below. Cite chunk ids like [RB-SSI-2]. If the excerpts do not cover it, say so and recommend escalation.

Runbook excerpts:
{chunks_text}
"""

    result = structured_llm.invoke(prompt)

    # Format as readable draft for guardrail + downstream
    draft_lines = [
        f"Root cause: {result.root_cause}",
        f"Proposed fix steps: {', '.join(result.proposed_fix_steps)}",
        f"Citations: {', '.join(result.citations)}",
    ]
    if result.risk_notes:
        draft_lines.append(f"Risk notes: {result.risk_notes}")
    draft = "\n".join(draft_lines)

    print(f"\n=== DRAFT FIX ===")
    print(f"Citations: {', '.join(result.citations)}")
    return {
        "draft": draft,
        "root_cause": result.root_cause,
        "proposed_fix_steps": result.proposed_fix_steps,
        "citations": result.citations,
        "risk_notes": result.risk_notes,
    }
