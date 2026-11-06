#!/usr/bin/env python3
"""
Triage CLI: submit exceptions and review decisions.

Usage:
    python scripts/triage_cli.py submit <sample.json>
    python scripts/triage_cli.py review <thread_id>
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.types import Command
from app.graph import build_graph


async def submit(sample_path: str):
    """Submit an exception for triage."""
    graph, conn = build_graph()
    try:
        with open(sample_path) as f:
            exception = json.load(f)

        thread_id = f"run-{exception.get('trade_id', 'unknown')}"
        config = {"configurable": {"thread_id": thread_id}}

        print(f"Submitting exception {exception.get('trade_id', 'N/A')}...")
        print(f"Thread ID: {thread_id}")

        # Use astream to handle interrupts properly
        paused = False
        async for event in graph.astream(
            {"exception": exception, "run_id": thread_id, "executed": False},
            config=config
        ):
            if "interrupts" in event:
                paused = True
                break

        # Check if we stopped at review (interrupt)
        state = await graph.aget_state(config)
        if state.next:
            print(f"\nStopped at: {state.next}")
            if "review" in state.next:
                print("Waiting for human review. Run:")
                print(f"  python scripts/triage_cli.py review {thread_id}")

                # Show review info
                values = state.values
                draft = values.get("draft", "")
                category = values.get("category", "UNKNOWN")
                confidence = values.get("confidence")
                citations = values.get("citations", [])
                trade_id = values.get("exception", {}).get("trade_id", "N/A")

                print(f"\nTrade ID: {trade_id}")
                print(f"Category: {category}")
                print(f"Confidence: {confidence}")
                print(f"Citations: {citations}")
                print(f"Draft:\n{draft}")
            else:
                print(f"Final decision: {state.values.get('decision', 'unknown')}")
        else:
            print(f"Completed. Decision: {state.values.get('decision', 'unknown')}")
            print(f"Executed: {state.values.get('executed', False)}")
            if state.values.get("settlement_result"):
                print(f"Settlement result: {state.values.get('settlement_result')}")

        return thread_id
    finally:
        await conn.close()


async def review(thread_id: str):
    """Review a pending exception and resume the graph."""
    graph, conn = build_graph()
    try:
        config = {"configurable": {"thread_id": thread_id}}

        # Get current state
        state = await graph.aget_state(config)
        if not state or not state.next or "review" not in state.next:
            print(f"No pending review for thread {thread_id}")
            return

        # Show review info
        values = state.values
        draft = values.get("draft", "")
        category = values.get("category", "UNKNOWN")
        confidence = values.get("confidence")
        citations = values.get("citations", [])
        trade_id = values.get("exception", {}).get("trade_id", "N/A")

        print(f"Trade ID: {trade_id}")
        print(f"Category: {category}")
        print(f"Confidence: {confidence}")
        print(f"Citations: {citations}")
        print(f"Draft:\n{draft}\n")

        decision = input("Approve or reject? (approve/reject): ").strip().lower()
        comment = input("Comment: ").strip()
        reviewer = "phillee"

        if decision not in ["approve", "approved", "reject", "rejected"]:
            print("Invalid decision")
            return

        decision_val = "approved" if decision.startswith("approve") else "rejected"

        # Resume the graph with the decision
        final_state = await graph.ainvoke(
            Command(resume={
                "decision": decision_val,
                "reviewer": reviewer,
                "comment": comment,
            }),
            config=config
        )

        print(f"\nFinal decision: {final_state.get('decision', 'unknown')}")
        print(f"Executed: {final_state.get('executed', False)}")
        if final_state.get("settlement_result"):
            print(f"Settlement result: {final_state.get('settlement_result')}")
        if final_state.get("idempotency_key"):
            print(f"Idempotency key: {final_state.get('idempotency_key')}")
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Triage CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser("submit", help="Submit an exception")
    submit_parser.add_argument("sample", help="Path to sample JSON file")

    review_parser = subparsers.add_parser("review", help="Review a pending exception")
    review_parser.add_argument("thread_id", help="Thread ID to review")

    args = parser.parse_args()

    if args.command == "submit":
        asyncio.run(submit(args.sample))
    elif args.command == "review":
        asyncio.run(review(args.thread_id))


if __name__ == "__main__":
    main()