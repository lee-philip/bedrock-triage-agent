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

    print(f"\n=== Results for {sample_id} (Trade {exception_data.get('trade_id')}) ===")
    print(f"Category: {final_state.get('category')}")
    print(f"Confidence: {final_state.get('confidence')}")
    print(f"Reason: {final_state.get('reason')}")
    print(f"Decision: {final_state.get('decision')}")
    print(f"Executed: {final_state.get('executed')}")

    if final_state.get("draft"):
        print(f"\nDraft fix:\n{final_state['draft']}")

    print("\n=== Audit Trail ===")
    for entry in final_state.get("audit", []):
        print(f"  [{entry['timestamp']}] {entry['node']} - {entry['provider']}/{entry['model']} - {entry['latency_ms']}ms")


if __name__ == "__main__":
    sample_id = sys.argv[1] if len(sys.argv) > 1 else "exception_001"
    asyncio.run(run_sample(sample_id))
