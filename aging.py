#!/usr/bin/env python3
"""Quantify session-aging tax: same suite measured in one long browser session versus
a fresh browser per category.

    ./aging.py --aged one-session.json --fresh split.json

Tests whose aged time far exceeds their fresh time were penalized by state accumulated
from everything that ran before them (leaked documents, heap growth, ...). The aged run
is the realistic one: real benchmarks and real browsing are long sessions.
"""

import argparse
import json


def load_times(path):
    with open(path) as f:
        data = json.load(f)
    times = {}
    for benchmark, tests in data.items():
        for key, value in tests.items():
            if key == "_total" or "time" not in value:
                continue
            times[f"{benchmark}/{key}"] = value["time"]["mean"]
    return times


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aged", required=True, help="Result JSON from a single long session")
    parser.add_argument("--fresh", required=True, help="Result JSON from --split-suites (fresh browser per category)")
    parser.add_argument("--min-tax", type=float, default=1.5, help="Only show tests at or above this aged/fresh ratio")
    args = parser.parse_args()

    aged = load_times(args.aged)
    fresh = load_times(args.fresh)

    rows = []
    total_aged = total_fresh = 0.0
    for key in aged:
        if key not in fresh or fresh[key] == 0:
            continue
        total_aged += aged[key]
        total_fresh += fresh[key]
        rows.append((key, aged[key], fresh[key], aged[key] / fresh[key]))
    rows.sort(key=lambda row: -row[3])

    width = max((len(key) for key, *_ in rows), default=20)
    print(f"{'Test':{width}s} {'Aged':>10s} {'Fresh':>10s} {'Tax':>7s}")
    for key, aged_time, fresh_time, tax in rows:
        if tax < args.min_tax:
            break
        print(f"{key:{width}s} {aged_time * 1000:9.2f}m {fresh_time * 1000:9.2f}m {tax:6.1f}x")
    if total_fresh:
        print(f"\n{'TOTAL':{width}s} {total_aged * 1000:9.1f}m {total_fresh * 1000:9.1f}m {total_aged / total_fresh:6.1f}x")


if __name__ == "__main__":
    main()
