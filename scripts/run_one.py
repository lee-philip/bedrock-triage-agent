import json
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph import build_graph, GraphRecursionError
from app.state import TriageState
from app.observability import get_callbacks, flush, check_token_budget

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

    thread_id = f"run-{sample_id}"

    # Build graph with Langfuse callbacks
    callbacks = get_callbacks(thread_id, thread_id)
    graph, conn = build_graph()
    try:
        initial_state = TriageState(
            exception=exception_data,
            run_id=thread_id,
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

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 12,
        }
        if callbacks:
            config["callbacks"] = callbacks

        try:
            final_state = await graph.ainvoke(initial_state, config=config)
        except GraphRecursionError as e:
            print(f"Graph exceeded recursion limit: {e}")
            # Write audit entry for step limit exceeded
            from app.audit import write_audit
            write_audit(thread_id, "step_limit", data={"error": "ABORTED_STEP_LIMIT"})
            final_state = {"exception": exception_data, "decision": "rejected", "reason": "step limit exceeded"}

    finally:
        await conn.close()
        flush()

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
