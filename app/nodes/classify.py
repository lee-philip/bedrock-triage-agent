from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.llm import get_chat_model
from app.observability import get_prompt

CATEGORIES = Literal[
    "SSI_MISMATCH",
    "MISSING_COUNTERPARTY_BIC",
    "PRICE_TOLERANCE_BREAK",
    "SETTLEMENT_DATE_MISMATCH",
    "INSUFFICIENT_CASH",
    "QUANTITY_MISMATCH",
    "UNKNOWN",
]


class Classification(BaseModel):
    category: CATEGORIES
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


async def classify(state):
    exception = state["exception"]
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(Classification)

    # Load prompt from Langfuse with local fallback
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fallback_path = os.path.join(base_dir, "prompts", "classify.txt")
    prompt_data = get_prompt(
        "triage-classify",
        fallback_path=fallback_path,
        trade_id=exception.get("trade_id", "N/A"),
        counterparty=exception.get("counterparty", "N/A"),
        expected_amount=exception.get("expected_amount", "N/A"),
        actual_amount=exception.get("actual_amount", "N/A"),
        expected_date=exception.get("expected_date", "N/A"),
        actual_date=exception.get("actual_date", "N/A"),
        quantity_expected=exception.get("quantity_expected", "N/A"),
        quantity_received=exception.get("quantity_received", "N/A"),
        error_message=exception.get("error_message", "N/A"),
    )
    prompt = prompt_data["prompt"]

    result = await structured_llm.ainvoke(prompt)
    tokens = result.usage_metadata.input_tokens + result.usage_metadata.output_tokens if result.usage_metadata else 0

    print(f"\n=== CLASSIFY ===")
    print(f"Category: {result.category}")
    print(f"Confidence: {result.confidence}")
    print(f"Reason: {result.reason}")
    return {
        "category": result.category,
        "confidence": result.confidence,
        "reason": result.reason,
        "input_tokens": result.usage_metadata.input_tokens if result.usage_metadata else 0,
        "output_tokens": result.usage_metadata.output_tokens if result.usage_metadata else 0,
        "prompt_name": prompt_data.get("prompt_name"),
        "prompt_version": prompt_data.get("prompt_version"),
    }
