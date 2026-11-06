import json
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph import graph
from app.state import TriageState

SAMPLES = {
    "exception_001": "samples/exception_001.json",
    "exception_002": "samples/exception_002.json",
    "exception_003": "samples/exception_003.json",
    "exception_004": "samples/exception_004.json",
    "exception_005": "samples/exception_005.json",
    "exception_006": "samples/exception_006.json",
}


async def run_sample(sample_id):
    if sample_id not in SAMPLES:
        print(f"Unknown sample: {sample_id}. Available: {list(SAMPLES.keys())}")
        return

    sample_path = Path(SAMPLES[sample_id])
    with open(sample_path) as f:
        exception_data = json.load(f)

    print(f"\n=== INPUT (Trade {exception_data.get('trade_id')}) ===")
    print(json.dumps(exception_data, indent=2))

    initial_state = TriageState(
        exception=exception_data,
        run_id=f"run-{sample_id}",
        category=None,
        confidence=None,
        reason=None,
        runbook_chunks=[],
        draft=None,
        guardrail_action=None,
        decision=None,
        reviewer=None,
        reviewer_comment=None,
        executed=False,
        audit=[],
    )

    final_state = await graph.ainvoke(initial_state)

    print(f"\n=== STEP 1: INPUT GUARDRAIL ===")
    input_audits = [e for e in final_state.get("audit", []) if e["node"] == "input_guardrail"]
    if input_audits:
        e = input_audits[0]
        print(f"Provider: {e['provider']}/{e['model']}")
        print(f"Latency: {e['latency_ms']}ms")
        print("Action: Masked PII from input before classification")

    print(f"\n=== STEP 2: CLASSIFY ===")
    print(f"Category: {final_state.get('category')}")
    print(f"Confidence: {final_state.get('confidence')}")
    print(f"Reason: {final_state.get('reason')}")
    classify_audits = [e for e in final_state.get("audit", []) if e["node"] == "classify"]
    if classify_audits:
        e = classify_audits[0]
        print(f"Provider: {e['provider']}/{e['model']}")
        print(f"Latency: {e['latency_ms']}ms")

    print(f"\n=== STEP 3: RETRIEVE (RAG) ===")
    chunks = final_state.get("runbook_chunks", [])
    print(f"Retrieved {len(chunks)} runbook chunks")
    for i, chunk in enumerate(chunks):
        text = chunk if isinstance(chunk, str) else str(chunk)
        preview = text[:100].replace("\n", " ")
        print(f"  Chunk {i+1}: {preview}...")
    retrieve_audits = [e for e in final_state.get("audit", []) if e["node"] == "retrieve"]
    if retrieve_audits:
        e = retrieve_audits[0]
        print(f"Provider: {e['provider']}/{e['model']}")
        print(f"Latency: {e['latency_ms']}ms")

    print(f"\n=== STEP 4: DRAFT FIX ===")
    print(f"Draft fix:")
    print(final_state.get("draft"))
    draft_audits = [e for e in final_state.get("audit", []) if e["node"] == "draft_fix"]
    if draft_audits:
        e = draft_audits[0]
        print(f"Provider: {e['provider']}/{e['model']}")
        print(f"Latency: {e['latency_ms']}ms")

    print(f"\n=== STEP 5: OUTPUT GUARDRAIL ===")
    print(f"Action: {final_state.get('guardrail_action')}")
    if final_state.get("blocked_policies"):
        print(f"Blocked policies: {', '.join(final_state['blocked_policies'])}")
    if final_state.get("masked_entities"):
        print(f"Masked entities: {', '.join(final_state['masked_entities'])}")
    guardrail_audits = [e for e in final_state.get("audit", []) if e["node"] == "guardrail"]
    if guardrail_audits:
        e = guardrail_audits[0]
        print(f"Provider: {e['provider']}/{e['model']}")
        print(f"Latency: {e['latency_ms']}ms")

    if final_state.get("guardrail_action") == "BLOCKED":
        print(f"\n=== STEP 6: REJECT (guardrail blocked) ===")
        print(f"Draft rejected by guardrail. Not sent to review.")
    else:
        print(f"\n=== STEP 6: REVIEW ===")
        print(f"Decision: {final_state.get('decision')}")
        print(f"Reviewer: {final_state.get('reviewer')}")
        print(f"Reviewer comment: {final_state.get('reviewer_comment')}")
        review_audits = [e for e in final_state.get("audit", []) if e["node"] == "review"]
        if review_audits:
            e = review_audits[0]
            print(f"Provider: {e['provider']}/{e['model']}")
            print(f"Latency: {e['latency_ms']}ms")

        print(f"\n=== STEP 7: EXECUTE ===")
        print(f"Executed: {final_state.get('executed')}")
        execute_audits = [e for e in final_state.get("audit", []) if e["node"] == "execute"]
        if execute_audits:
            e = execute_audits[0]
            print(f"Provider: {e['provider']}/{e['model']}")
            print(f"Latency: {e['latency_ms']}ms")

    print(f"\n=== FULL AUDIT TRAIL ===")
    for entry in final_state.get("audit", []):
        print(f"  [{entry['timestamp']}] {entry['node']} - {entry['provider']}/{entry['model']} - {entry['latency_ms']}ms")


if __name__ == "__main__":
    sample_id = sys.argv[1] if len(sys.argv) > 1 else "exception_001"
    asyncio.run(run_sample(sample_id))
