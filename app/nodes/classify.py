from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.llm import get_chat_model

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

    prompt = f"""Classify this trade settlement exception:

Trade ID: {exception.get("trade_id", "N/A")}
Counterparty: {exception.get("counterparty", "N/A")}
Expected amount: {exception.get("expected_amount", "N/A")}
Actual amount: {exception.get("actual_amount", "N/A")}
Expected settlement date: {exception.get("expected_date", "N/A")}
Actual settlement date: {exception.get("actual_date", "N/A")}
Quantity expected: {exception.get("quantity_expected", "N/A")}
Quantity received: {exception.get("quantity_received", "N/A")}
Error message: {exception.get("error_message", "N/A")}
"""

    result = await structured_llm.ainvoke(prompt)

    print(f"\n=== CLASSIFY ===")
    print(f"Category: {result.category}")
    print(f"Confidence: {result.confidence}")
    print(f"Reason: {result.reason}")
    return {
        "category": result.category,
        "confidence": result.confidence,
        "reason": result.reason,
    }
