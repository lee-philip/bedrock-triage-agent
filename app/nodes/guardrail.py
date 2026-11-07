"""Bedrock Guardrails integration.

Applies a Bedrock guardrail to the draft fix to check for:
- Sensitive information (PII)
- Investment advice
- Content filters

When LLM_PROVIDER=bedrock, calls the real apply_guardrail API.
When LLM_PROVIDER=local, uses a regex-based stub.
"""
import re
import boto3
from botocore.exceptions import ClientError

from app.config import LLM_PROVIDER, GUARDRAIL_ID, GUARDRAIL_VERSION, GUARDRAIL_REGION
from app.observability import start_span


def get_bedrock_runtime_client():
    """Get a Bedrock Runtime client configured for the guardrail region."""
    import boto3.session
    session = boto3.session.Session(profile_name="bedrock-triage")
    return session.client("bedrock-runtime", region_name=GUARDRAIL_REGION)


def apply_bedrock_guardrail(draft: str, source: str = "OUTPUT") -> dict:
    """Apply the Bedrock guardrail to the draft text.

    Args:
        draft: Text to check
        source: "INPUT" or "OUTPUT"

    Returns:
        dict with fields:
            action: "BLOCKED" | "MASKED" | "PASS"
            output: Cleaned/masked text (or original)
            blocked_policies: List of policy names that fired
            masked_entities: List of entity types that were masked
    """
    client = get_bedrock_runtime_client()
    try:
        response = client.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=GUARDRAIL_VERSION,
            source=source,
            content=[{"text": {"text": draft}}],
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ValidationException":
            return {
                "action": "PASS",
                "output": draft,
                "blocked_policies": [],
                "masked_entities": [],
                "error": "Guardrail not found",
            }
        return {
            "action": "PASS",
            "output": draft,
            "blocked_policies": [],
            "masked_entities": [],
            "error": str(e),
        }

    action = response.get("action", "NONE")

    # Extract output content
    output_text = draft
    for output in response.get("outputs", []):
        text_value = output.get("text", "")
        if text_value:
            output_text = text_value
            break

    # Check assessments for triggered policies
    blocked_policies = []
    masked_entities = []
    for assessment in response.get("assessments", []):
        # Topic policy (investment advice, etc.)
        topic_policy = assessment.get("topicPolicy", {})
        for topic in topic_policy.get("topics", []):
            if topic.get("detected") and topic.get("action") == "BLOCKED":
                blocked_policies.append(topic.get("name", "unknown"))
        # Sensitive info policy (PII)
        sensitive_info_policy = assessment.get("sensitiveInformationPolicy", {})
        for entity in sensitive_info_policy.get("piiEntities", []):
            if entity.get("detected"):
                masked_entities.append(entity.get("type", "unknown"))

    if action == "GUARDRAIL_INTERVENED" and blocked_policies:
        return {
            "action": "BLOCKED",
            "output": draft,
            "blocked_policies": blocked_policies,
            "masked_entities": masked_entities,
        }
    elif masked_entities:
        return {
            "action": "MASKED",
            "output": output_text,
            "blocked_policies": [],
            "masked_entities": masked_entities,
        }
    else:
        return {
            "action": "PASS",
            "output": output_text,
            "blocked_policies": [],
            "masked_entities": [],
        }


def apply_stub_guardrail(draft: str) -> dict:
    """Stub guardrail for local development (regex-based)."""
    masked = []

    # PII detection regexes
    name_pattern = re.compile(r"(Mr|Mrs|Ms|Mx)\.\s+[A-Z][a-z]+")
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
    ssn_pattern = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    if name_pattern.search(draft):
        masked.append("NAME")
    if email_pattern.search(draft):
        masked.append("EMAIL")
    if phone_pattern.search(draft):
        masked.append("PHONE")
    if ssn_pattern.search(draft):
        masked.append("SSN")

    # Investment advice detection
    investment_phrases = [
        "buy more", "buy ", "sell ", "hold ", "short ", "long ",
        "shares of", "put option", "call option", "gains",
        "returns", "buying ", "selling ", "invest in",
    ]
    has_investment = any(phrase in draft.lower() for phrase in investment_phrases)

    if has_investment:
        return {
            "action": "BLOCKED",
            "output": draft,
            "blocked_policies": ["Investment advice"],
            "masked_entities": masked,
        }
    elif masked:
        # Mask PII with placeholder
        masked_draft = re.sub(ssn_pattern, "***-**-****", draft)
        masked_draft = re.sub(email_pattern, "[email]", masked_draft)
        masked_draft = re.sub(phone_pattern, "[phone]", masked_draft)
        masked_draft = re.sub(name_pattern, "[name]", masked_draft)
        return {
            "action": "MASKED",
            "output": masked_draft,
            "blocked_policies": [],
            "masked_entities": masked,
        }
    else:
        return {
            "action": "PASS",
            "output": draft,
            "blocked_policies": [],
            "masked_entities": [],
        }


async def guardrail(state):
    """Apply guardrail to the fix draft."""
    draft = state.get("draft", "")
    span, lf = start_span("bedrock-guardrail", input={"draft_length": len(draft)})
    
    try:
        if LLM_PROVIDER == "bedrock" and GUARDRAIL_ID:
            result = apply_bedrock_guardrail(draft, source="OUTPUT")
            provider = "bedrock"
        else:
            result = apply_stub_guardrail(draft)
            provider = "stub"
    finally:
        if span is not None:
            span.update(output={"action": result["action"]})
            span.end()

    audit_entry = {
        "node": "guardrail",
        "timestamp": "audit_entry",
        "provider": provider,
        "action": result["action"],
        "blocked_policies": result["blocked_policies"],
        "masked_entities": result["masked_entities"],
    }

    print(f"\n=== GUARDRAIL ===")
    print(f"Action: {result['action']}")
    if result.get("blocked_policies"):
        print(f"Blocked: {', '.join(result['blocked_policies'])}")
    if result.get("masked_entities"):
        print(f"Masked: {', '.join(result['masked_entities'])}")
    print(f"Provider: {provider}")
    return {
        "guardrail_action": result["action"],
        "guardrail_audit": audit_entry,
        "draft": result["output"],
        "blocked_policies": result["blocked_policies"],
        "masked_entities": result["masked_entities"],
    }