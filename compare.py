#!/usr/bin/env python3
import json
import argparse
import statistics
import math
from scipy import stats
from tabulate import tabulate


def confidence_interval(data, confidence=0.95):
    n = len(data)
    mean = statistics.mean(data)
    stderr = statistics.stdev(data) / math.sqrt(n) if n > 1 else 0
    interval = stderr * stats.t.ppf((1 + confidence) / 2., n-1) if n > 1 else 0
    return mean - interval, mean + interval


def format_mean_confidence_interval(data):
    lo, hi = confidence_interval(data)
    mean = statistics.mean(data)
    if lo == hi:
        return f"{mean:.2f}"
    return f"{mean:.2f} ± {hi - mean:.2f}"


def extract_tests(data):
    rows = []

    for benchmark, tests in data.items():
        for test_key, metrics in tests.items():
            if test_key == "_total":
                continue

            if "/" in test_key:
                suite_name, test_name = test_key.split("/", 1)
            else:
                suite_name = ""
                test_name = test_key

            time_data = metrics.get("time", {})
            values = time_data.get("runs", [])

            if not values:
                continue

            rows.append({
                "benchmark": benchmark,
                "suite": suite_name,
                "test": test_name,
                "values": values,
            })
    return rows


def extract_scores(data):
    scores = {}
    for benchmark, tests in data.items():
        total = tests.get("_total", {})
        if total:
            scores[benchmark] = {
                "score": total.get("score", {}).get("runs", []),
                "totalTime": total.get("time", {}).get("runs", []),
            }
    return scores


def main():
    parser = argparse.ArgumentParser(description="Compare JavaScript benchmark results (old vs new).")
    parser.add_argument("-o", "--old", required=True, help="Old JSON results file.")
    parser.add_argument("-n", "--new", required=True, help="New JSON results file.")
    args = parser.parse_args()

    with open(args.old, "r") as f:
        old_data = json.load(f)
    with open(args.new, "r") as f:
        new_data = json.load(f)

    old_tests = { (r["benchmark"], r["suite"], r["test"]): r["values"] for r in extract_tests(old_data) }
    new_tests = { (r["benchmark"], r["suite"], r["test"]): r["values"] for r in extract_tests(new_data) }

    table = []

    all_keys = set(old_tests.keys()) | set(new_tests.keys())

    for key in sorted(all_keys):
        benchmark, suite, test = key

        old_vals = old_tests.get(key, [])
        new_vals = new_tests.get(key, [])

        if not old_vals or not new_vals:
            old_str = format_mean_confidence_interval(old_vals) if old_vals else "—"
            new_str = format_mean_confidence_interval(new_vals) if new_vals else "—"
            speedup = ""
        else:
            old_mean = statistics.mean(old_vals)
            new_mean = statistics.mean(new_vals)
            speedup = f"{old_mean / new_mean:.3f}"
            old_str = format_mean_confidence_interval(old_vals)
            new_str = format_mean_confidence_interval(new_vals)

        table.append([
            benchmark,
            suite,
            test,
            speedup,
            old_str,
            new_str
        ])

    print(tabulate(table, headers=["Benchmark", "Suite", "Test", "Speedup", "Old (Mean ± Range)", "New (Mean ± Range)"]))

    old_scores = extract_scores(old_data)
    new_scores = extract_scores(new_data)

    score_table = []
    all_benchmarks = set(old_scores.keys()) | set(new_scores.keys())

    for bench in sorted(all_benchmarks):
        old = old_scores.get(bench, {})
        new = new_scores.get(bench, {})

        old_score = old.get("score", [])
        new_score = new.get("score", [])
        old_time = old.get("totalTime", [])
        new_time = new.get("totalTime", [])

        score_improvement = ""
        speedup = ""

        if old_score and new_score:
            old_score_mean = statistics.mean(old_score)
            new_score_mean = statistics.mean(new_score)
            score_improvement = f"{new_score_mean / old_score_mean:.3f}" if old_score_mean else "—"

        if old_time and new_time:
            old_time_mean = statistics.mean(old_time)
            new_time_mean = statistics.mean(new_time)
            speedup = f"{old_time_mean / new_time_mean:.3f}" if new_time_mean else "—"

        score_table.append([
            bench,
            format_mean_confidence_interval(old_score),
            format_mean_confidence_interval(new_score),
            score_improvement or "—",
            format_mean_confidence_interval(old_time),
            format_mean_confidence_interval(new_time),
            speedup or "—",
        ])

    print()
    print(tabulate(
        score_table,
        headers=[
            "Benchmark",
            "Old Score",
            "New Score",
            "Score Improvement",
            "Old Total Time (ms)",
            "New Total Time (ms)",
            "Speedup"
        ],
    ))


if __name__ == "__main__":
    main()
