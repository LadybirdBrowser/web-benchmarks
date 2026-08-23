#!/usr/bin/env python3
"""Compare two result JSONs from run.py across browsers and rank tests by multiplier.

Typical use: rank how much slower Ladybird is than Chromium on every MicroWeb test,
worst first, so the worst offender is always the next thing to work on.

    ./run.py --executable .../Ladybird --benchmarks MicroWeb -o lb.json
    ./run.py --executable /snap/bin/chromium --browser chromium --jitless \\
        --benchmarks MicroWeb -o cr.json
    ./ratios.py --subject lb.json --reference cr.json

A multiplier of 3.0 means the subject took 3x as long as the reference. Tests are also
grouped per suite so category-wide problems stand out. Use --min-multiplier to show only
tests above a threshold, and --markdown for a table to paste into notes.
"""

import argparse
import json
from collections import defaultdict


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
    parser.add_argument("--subject", "-s", required=True, help="Result JSON being evaluated (e.g. Ladybird)")
    parser.add_argument("--reference", "-r", required=True, help="Result JSON to compare against (e.g. Chromium)")
    parser.add_argument("--min-multiplier", type=float, default=0.0, help="Only show tests at or above this multiplier")
    parser.add_argument("--markdown", action="store_true", help="Emit a markdown table")
    args = parser.parse_args()

    subject = load_times(args.subject)
    reference = load_times(args.reference)

    rows = []
    for key in subject:
        if key not in reference or reference[key] == 0:
            continue
        rows.append((key, subject[key], reference[key], subject[key] / reference[key]))
    rows.sort(key=lambda row: -row[3])

    shown = [row for row in rows if row[3] >= args.min_multiplier]
    if args.markdown:
        print("| Test | Subject (ms) | Reference (ms) | Multiplier |")
        print("|---|---|---|---|")
        for key, s, r, m in shown:
            print(f"| {key} | {s * 1000:.2f} | {r * 1000:.2f} | {m:.1f}x |")
    else:
        width = max((len(key) for key, *_ in shown), default=20)
        print(f"{'Test':{width}s} {'Subject':>10s} {'Referen.':>10s} {'Mult':>7s}")
        for key, s, r, m in shown:
            print(f"{key:{width}s} {s * 1000:9.2f}m {r * 1000:9.2f}m {m:6.1f}x")

    by_suite_subject = defaultdict(float)
    by_suite_reference = defaultdict(float)
    for key, s, r, _ in rows:
        suite = "/".join(key.split("/")[:2])
        by_suite_subject[suite] += s
        by_suite_reference[suite] += r

    print()
    print(f"{'Suite summary':40s} {'Subject':>10s} {'Referen.':>10s} {'Mult':>7s}")
    total_subject = total_reference = 0.0
    for suite in sorted(by_suite_subject, key=lambda k: -by_suite_subject[k] / by_suite_reference[k]):
        s, r = by_suite_subject[suite], by_suite_reference[suite]
        total_subject += s
        total_reference += r
        print(f"{suite:40s} {s * 1000:9.1f}m {r * 1000:9.1f}m {s / r:6.1f}x")
    if total_reference:
        print(f"{'TOTAL':40s} {total_subject * 1000:9.1f}m {total_reference * 1000:9.1f}m {total_subject / total_reference:6.1f}x")


if __name__ == "__main__":
    main()
