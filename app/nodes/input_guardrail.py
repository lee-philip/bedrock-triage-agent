"""Input guardrail: mask PII from incoming exception text before classification."""
import re

from app.config import LLM_PROVIDER, GUARDRAIL_ID, GUARDRAIL_VERSION, AWS_REGION
from app.nodes.guardrail import apply_bedrock_guardrail, apply_stub_guardrail


async def input_guardrail(state):
    """Apply guardrail to incoming exception text (PII masking)."""
    exception = state.get("exception", {})
    error_text = exception.get("error_message", "")
    
    # Also mask any PII in other text fields
    text_to_mask = error_text
    notes = exception.get("notes", "")
    if notes:
        text_to_mask += " " + notes

    if LLM_PROVIDER == "bedrock" and GUARDRAIL_ID:
        result = apply_bedrock_guardrail(text_to_mask, source="INPUT")
        provider = "bedrock"
    else:
        result = apply_stub_guardrail(text_to_mask)
        provider = "stub"

    print(f"\n=== INPUT GUARDRAIL ===")
    print(f"Input (original): {error_text[:100]}...")
    print(f"Output (masked): {result['output'][:100]}...")
    print(f"Provider: {provider}")

    # Build masked exception for downstream nodes
    masked_exception = {**exception}
    masked_exception["error_message"] = result["output"]
    
    audit_entry = {
        "node": "input_guardrail",
        "timestamp": "audit_entry",
        "provider": provider,
        "action": result["action"],
        "blocked_policies": result["blocked_policies"],
        "masked_entities": result["masked_entities"],
    }

    return {
        "exception": masked_exception,
        "input_guardrail_audit": audit_entry,
        "input_masked_entities": result["masked_entities"],
    }
