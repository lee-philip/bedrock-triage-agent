"""Draft fix recommendation based on retrieved runbook sections."""
from pydantic import BaseModel, Field
from typing import List, Optional

from app.llm import get_chat_model
from app.observability import get_prompt


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

    # Load prompt from Langfuse with local fallback
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fallback_path = os.path.join(base_dir, "prompts", "draft_fix.txt")
    prompt_data = get_prompt(
        "triage-draft",
        fallback_path=fallback_path,
        category=category,
        trade_id=exception.get("trade_id", "N/A"),
        error_message=exception.get("error_message", "N/A"),
        runbook_excerpts=chunks_text,
    )
    prompt = prompt_data["prompt"]

    result = structured_llm.invoke(prompt)
    tokens = result.usage_metadata.input_tokens + result.usage_metadata.output_tokens if result.usage_metadata else 0

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
        "input_tokens": result.usage_metadata.input_tokens if result.usage_metadata else 0,
        "output_tokens": result.usage_metadata.output_tokens if result.usage_metadata else 0,
        "prompt_name": prompt_data.get("prompt_name"),
        "prompt_version": prompt_data.get("prompt_version"),
    }
