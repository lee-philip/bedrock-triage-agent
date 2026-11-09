#!/usr/bin/env python3
"""
Eval harness for settlement exception triage agent.

Runs each case through the graph up to the review interrupt,
records predictions and metrics, and reports accuracy.

Usage:
    python evals/run_evals.py --provider local
    python evals/run_evals.py --provider bedrock --confirm-cost
"""
import argparse
import asyncio
import json
import sys
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.errors import GraphRecursionError
from app.graph import build_graph
from app.config import BEDROCK_MODEL_ID, LMSTUDIO_MODEL
from app.observability import get_trace_config, add_score, flush, check_token_budget


class TokenCounter:
    """Thread-safe token counter."""
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.call_count = 0
        self.latencies = []
        self._start = None

    def call_start(self):
        self._start = time.time()

    def call_end(self, input_tokens: int, output_tokens: int):
        elapsed = time.time() - self._start
        self._start = None
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.call_count += 1
        self.latencies.append(elapsed)


# Global counter shared across graph nodes
_counter: Optional[TokenCounter] = None


def install_token_tracking():
    """Wrap model class ainvoke methods to track tokens."""
    global _counter
    _counter = TokenCounter()

    # Wrap ChatOpenAI (used by local LM Studio)
    from langchain_openai import ChatOpenAI
    original_openai_ainvoke = ChatOpenAI.ainvoke

    async def tracked_openai_ainvoke(self, input, config=None, **kwargs):
        _counter.call_start()
        response = await original_openai_ainvoke(self, input, config=config, **kwargs)
        input_t = 0
        output_t = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_t = response.usage_metadata.get("input_tokens", 0)
            output_t = response.usage_metadata.get("output_tokens", 0)
        _counter.call_end(input_t, output_t)
        return response

    ChatOpenAI.ainvoke = tracked_openai_ainvoke

    # Wrap ChatBedrockConverse (used by Bedrock)
    try:
        from langchain_aws import ChatBedrockConverse
        original_bedrock_ainvoke = ChatBedrockConverse.ainvoke

        async def tracked_bedrock_ainvoke(self, input, config=None, **kwargs):
            _counter.call_start()
            response = await original_bedrock_ainvoke(self, input, config=config, **kwargs)
            input_t = 0
            output_t = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                input_t = response.usage_metadata.get("input_tokens", 0)
                output_t = response.usage_metadata.get("output_tokens", 0)
            _counter.call_end(input_t, output_t)
            return response

        ChatBedrockConverse.ainvoke = tracked_bedrock_ainvoke
    except ImportError:
        pass  # Bedrock package not installed

    return _counter


def estimate_tokens(cases: List[Dict[str, Any]]) -> int:
    """Rough estimate of tokens needed for all cases."""
    total = 0
    for case in cases:
        exc = case["exception"]
        # Estimate ~4 tokens per word
        text = json.dumps(exc)
        words = len(text.split())
        total += words * 4
    # Each case has multiple LLM calls (guardrail, classify, retrieve, draft)
    # Estimate ~3 calls per case
    return total * 3


async def run_case(graph, case: Dict[str, Any], verbose: bool, eval_run_name=None) -> Dict[str, Any]:
    """Run a single case through the graph up to the review interrupt."""
    exception = case["exception"]
    thread_id = f"eval-{case['id']}-{int(time.time())}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 12,
        **get_trace_config(thread_id, thread_id, eval_run_name=eval_run_name),
    }

    start = time.time()
    node_latencies = {}

    try:
        paused = False
        try:
            async for event in graph.astream(
                {"exception": exception, "run_id": thread_id, "executed": False},
                config=config
            ):
                # Check for interrupts
                if "interrupts" in event:
                    paused = True
                    break
        except GraphRecursionError as e:
            # Tag trace with failure
            print(f"  ✗ {case['id']} recursion limit exceeded")
            return {
                "id": case["id"],
                "expected_category": case["expected_category"],
                "predicted_category": "RECURSION_LIMIT",
                "confidence": 0,
                "expected_guardrail": case.get("expected_guardrail", "PASS"),
                "actual_guardrail": "RECURSION_LIMIT",
                "category_correct": False,
                "guardrail_correct": False,
                "latency_ms": round((time.time() - start) * 1000, 1),
                "node_latencies_ms": {},
            }

        state = await graph.aget_state(config)
        values = state.values

        predicted_category = values.get("category", "UNKNOWN")
        confidence = values.get("confidence")
        guardrail_action = values.get("guardrail_action", "PASS")

        # Extract per-node latencies from audit
        audit = values.get("audit", [])
        for entry in audit:
            node_latencies[entry["node"]] = entry.get("latency_ms", 0)

        elapsed = time.time() - start

        result = {
            "id": case["id"],
            "expected_category": case["expected_category"],
            "predicted_category": predicted_category,
            "confidence": confidence,
            "expected_guardrail": case.get("expected_guardrail", "PASS"),
            "actual_guardrail": guardrail_action,
            "category_correct": predicted_category == case["expected_category"],
            "guardrail_correct": guardrail_action == case.get("expected_guardrail", "PASS"),
            "latency_ms": round(elapsed * 1000, 1),
            "node_latencies_ms": node_latencies,
        }

        if verbose:
            status = "✓" if result["category_correct"] else "✗"
            print(f"  {status} {case['id']} {predicted_category} (expected {case['expected_category']}) "
                  f"conf={confidence} guardrail={guardrail_action} "
                  f"{result['latency_ms']}ms")

        return result

    finally:
        # State is in the checkpoint DB, no cleanup needed
        pass


def print_results(results: List[Dict[str, Any]], cases: List[Dict[str, Any]]):
    """Print summary table and metrics."""
    print("\n" + "=" * 80)
    print("EVAL RESULTS")
    print("=" * 80)

    # Category accuracy
    correct = sum(1 for r in results if r["category_correct"])
    total = len(results)
    overall_acc = correct / total * 100
    print(f"\nOverall category accuracy: {correct}/{total} ({overall_acc:.1f}%)")

    # Per-category accuracy
    from collections import defaultdict
    cat_results = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in results:
        cat = r["expected_category"]
        cat_results[cat]["total"] += 1
        if r["category_correct"]:
            cat_results[cat]["correct"] += 1

    print("\nPer-category accuracy:")
    for cat in sorted(cat_results.keys()):
        cr = cat_results[cat]
        acc = cr["correct"] / cr["total"] * 100
        print(f"  {cat}: {cr['correct']}/{cr['total']} ({acc:.1f}%)")

    # Confusion list (misses)
    misses = [r for r in results if not r["category_correct"]]
    if misses:
        print(f"\nMisses ({len(misses)}):")
        for m in misses:
            print(f"  {m['id']}: predicted={m['predicted_category']} expected={m['expected_category']}")
    else:
        print("\nNo misses!")

    # Guardrail agreement
    guardrail_correct = sum(1 for r in results if r["guardrail_correct"])
    guardrail_acc = guardrail_correct / total * 100
    print(f"\nGuardrail agreement: {guardrail_correct}/{total} ({guardrail_acc:.1f}%)")
    guardrail_misses = [r for r in results if not r["guardrail_correct"]]
    if guardrail_misses:
        for gm in guardrail_misses:
            print(f"  {gm['id']}: actual={gm['actual_guardrail']} expected={gm['expected_guardrail']}")

    # Latency
    latencies = sorted([r["latency_ms"] for r in results])
    p50 = latencies[len(latencies) // 2]
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[min(p95_idx, len(latencies) - 1)]
    avg = sum(latencies) / len(latencies)
    print(f"\nLatency (ms): avg={avg:.0f} p50={p50:.0f} p95={p95:.0f} min={latencies[0]:.0f} max={latencies[-1]:.0f}")

    # Token summary
    print("\nDone.")


async def run_evals(provider: str, confirm_cost: bool, verbose: bool):
    """Run the full eval suite."""
    cases_file = Path(__file__).parent / "cases.jsonl"
    results_dir = Path(__file__).parent / "results"

    # Load cases
    cases = []
    with open(cases_file) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    print(f"Loaded {len(cases)} eval cases")
    print(f"Provider: {provider}")

    # Estimate token cost
    estimated_tokens = estimate_tokens(cases)
    print(f"Estimated token usage: ~{estimated_tokens:,} tokens")

    if provider == "bedrock" and not confirm_cost:
        print("\nBedrock provider selected. Estimated cost will depend on your plan.")
        print("Run again with --confirm-cost to proceed.")
        return

    # Install token tracking before building graph
    _counter = install_token_tracking()

    # Run cases
    results = []

    eval_run_name = f"eval-{model_id.replace(':', '-')}"
    tracing_enabled = bool(get_trace_config("eval-run", "eval-run", eval_run_name=eval_run_name))

    trace_results = []
    for i, case in enumerate(cases, 1):
        print(f"Running case {i}/{len(cases)}: {case['id']}")

        # Fresh graph for each case (checkpoint DB persists between them)
        graph, conn = build_graph()
        try:
            result = await run_case(graph, case, verbose, eval_run_name=eval_run_name)
            result["thread_id"] = f"eval-{case['id']}-{int(time.time())}"
            trace_results.append(result)
        finally:
            await conn.close()

    # Add scores to Langfuse traces for eval runs
    if tracing_enabled:
        print("\nAdding eval scores to Langfuse traces...")
        for result in trace_results:
            # The Langfuse callback generates a trace ID; we attach scores by thread_id
            # which the callback uses as session_id
            add_score(
                trace_id=result["thread_id"],
                name="category_correct",
                value=1.0 if result["category_correct"] else 0.0,
                data_type="NUMERIC",
            )
            add_score(
                trace_id=result["thread_id"],
                name="guardrail_agree",
                value=1.0 if result["guardrail_correct"] else 0.0,
                data_type="NUMERIC",
            )

    # Print results
    print_results(results, cases)

    # Token/latency summary
    total_input = _counter.input_tokens
    total_output = _counter.output_tokens
    print(f"\nTotal tokens: input={total_input:,} output={total_output:,}")
    print(f"LLM calls: {_counter.call_count}")
    if _counter.latencies:
        avg_latency = sum(_counter.latencies) / len(_counter.latencies) * 1000
        print(f"LLM call latency: avg={avg_latency:.0f}ms")

    # Save results
    model_id = BEDROCK_MODEL_ID if provider == "bedrock" else LMSTUDIO_MODEL
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_file = results_dir / f"{timestamp}-{provider}-{model_id.replace(':', '-')}.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": timestamp,
            "provider": provider,
            "model": model_id,
            "cases": len(cases),
            "results": results,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "llm_call_count": _counter.call_count,
        }, f, indent=2)
    print(f"\nResults saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Run triage eval suite")
    parser.add_argument("--provider", choices=["local", "bedrock"], default="local",
                        help="LLM provider to use")
    parser.add_argument("--confirm-cost", action="store_true",
                        help="Confirm bedrock cost and proceed")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-case results")
    args = parser.parse_args()

    # Set provider env var for the session
    os.environ["LLM_PROVIDER"] = args.provider

    asyncio.run(run_evals(args.provider, args.confirm_cost, args.verbose))


if __name__ == "__main__":
    main()