#!/usr/bin/env python3
"""Langfuse cost and latency monitoring script.

Reads daily cost and p95 latency from the Langfuse API and warns
when thresholds are exceeded.

Usage:
    python scripts/check_costs.py [--days 7] [--verbose]
"""
import argparse
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.observability import get_client, LANGFUSE_ENABLED


def check_costs(days=7, verbose=False):
    """Check daily costs and p95 latency against thresholds."""
    client = get_client()
    if client is None:
        print("Langfuse client not available. Check LANGFUSE_ENABLED and credentials.")
        return 1

    try:
        # Fetch cost metrics via Langfuse API
        # Using the v3 metrics API for observability costs
        today = datetime.now(timezone.utc)
        start_date = today - timedelta(days=days)

        # Fetch cost data from Langfuse metrics API
        # Note: Exact API endpoint depends on Langfuse version
        response = client.api.metrics.get_many(
            start_time=start_date.isoformat(),
            end_time=today.isoformat(),
            metric_type="cost",
        )

        # Also fetch latency data
        latency_response = client.api.metrics.get_many(
            start_time=start_date.isoformat(),
            end_time=today.isoformat(),
            metric_type="latency",
        )

        # Parse and analyze
        daily_costs = []
        for item in response.data:
            daily_costs.append({
                "date": item.time,
                "cost": item.value,
            })

        p95_latency = 0
        if latency_response.data:
            # Calculate p95 from latency percentiles
            for item in latency_response.data:
                if item.percentile == 95:
                    p95_latency = item.value * 1000  # Convert to ms
                    break

        # Check thresholds
        daily_max = float(os.environ.get("COST_DAILY_MAX", 100.00))
        p95_max = float(os.environ.get("LATENCY_P95_MS", 30000))

        warnings = []

        # Check daily costs
        for entry in daily_costs:
            if entry["cost"] > daily_max:
                warnings.append(
                    f"COST ALERT: {entry['date']} cost ${entry['cost']:.2f} "
                    f"exceeds ${daily_max:.2f}"
                )

        # Check p95 latency
        if p95_latency > p95_max:
            warnings.append(
                f"LATENCY ALERT: p95 latency {p95_latency:.0f}ms "
                f"exceeds {p95_max:.0f}ms"
            )

        # Report
        if verbose:
            print(f"\nDaily costs (last {days} days):")
            for entry in daily_costs:
                print(f"  {entry['date']}: ${entry['cost']:.2f}")
            print(f"\np95 latency: {p95_latency:.0f}ms")

        if warnings:
            print("\nWARNINGS:")
            for w in warnings:
                print(f"  ⚠ {w}")
            return 1
        else:
            print("\n✓ All thresholds within limits")
            return 0

    except Exception as e:
        print(f"Error querying Langfuse API: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Langfuse cost and latency")
    parser.add_argument("--days", type=int, default=7, help="Number of days to check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed data")
    args = parser.parse_args()

    if not LANGFUSE_ENABLED:
        print("LANGFUSE_ENABLED is not set to 'true'")
        sys.exit(1)

    sys.exit(check_costs(args.days, args.verbose))