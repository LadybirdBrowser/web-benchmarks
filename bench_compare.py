#!/usr/bin/env python3
"""Paired analysis of interleaved benchmark rounds, and the PR performance section.

Takes per-round results.json payloads from two arms of an A/B run and answers one question: Did anything move by more
than this run can resolve? Knows nothing about git or compilers — so it's testable without a browser.
"""
import json
import math
import statistics
from dataclasses import dataclass, field

from scipy import stats

EM_DASH = chr(0x2014)
NBSP = chr(0x00A0)
PLUS_MINUS = chr(0x00B1)

# Ladybird coarsens performance.now() to 0.1 ms — so every reported time is a multiple of this. A test can't be resolved
# below one quantum of its own time, and a difference of under two quanta is what a value straddling a rounding boundary
# produces — so it never counts as movement.
QUANTUM_SECONDS = 0.0001
FLOOR_SECONDS = 2 * QUANTUM_SECONDS

# Tests shorter than this are a handful of quanta long; their resolution is set by the timer, not the run — so they stay
# out of the resolution the section quotes.
RESOLUTION_MIN_SECONDS = 0.002


@dataclass
class Mover:
    test: str
    base_mean: float
    head_mean: float
    effect_pct: float
    speedup_pct: float
    q: float
    direction: str


@dataclass
class Analysis:
    movers: list = field(default_factory=list)
    neutral_count: int = 0
    coverage_changes: list = field(default_factory=list)
    invalid: list = field(default_factory=list)
    resolution_median_pct: float = 0.0
    resolution_p90_pct: float = 0.0
    per_test_resolution_pct: dict = field(default_factory=dict)
    quantized_count: int = 0
    focus: list = field(default_factory=list)
    focus_count: int = 0
    rounds: int = 0

    @property
    def is_neutral(self):
        return not self.movers


def _flatten(payload):
    """One round's results.json -> {benchmark/test: seconds}."""
    out = {}
    for benchmark, tests in payload.items():
        for key, metrics in tests.items():
            if key == "_total":
                continue
            time = metrics.get("time")
            if isinstance(time, dict) and "mean" in time:
                out[f"{benchmark}/{key}"] = time["mean"]
    return out


def _benjamini_hochberg(pvalues):
    """Return BH-adjusted q-values, in the order the p-values were given."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank, idx in enumerate(reversed(order), start=1):
        i = m - rank + 1
        running = min(running, pvalues[idx] * m / i)
        q[idx] = running
    return q


def analyze(base_rounds, head_rounds, alpha=0.05, floor_pct=1.0, floor_seconds=FLOOR_SECONDS,
            use_fdr=True, focus=None):
    """focus names suites or benchmark/test keys declared before the run; they form their own false-discovery family —
    so a real change in the tests a PR targets isn't drowned by the correction over hundreds of unrelated tests."""
    base = [_flatten(r) for r in base_rounds]
    head = [_flatten(r) for r in head_rounds]
    n = min(len(base), len(head))
    if n < 2:
        raise ValueError(f"paired analysis needs at least 2 rounds per arm; got {n}")
    result = Analysis(rounds=n, focus=list(focus or []))

    in_all_base = set.intersection(*[set(r) for r in base]) if base else set()
    in_all_head = set.intersection(*[set(r) for r in head]) if head else set()
    result.coverage_changes = sorted(in_all_base.symmetric_difference(in_all_head))

    keys, log_ratios, means = [], [], []
    for key in sorted(in_all_base & in_all_head):
        b = [base[i][key] for i in range(n)]
        h = [head[i][key] for i in range(n)]
        if any(v <= 0 for v in b + h):
            result.invalid.append(key)
            continue
        keys.append(key)
        log_ratios.append([math.log(h[i] / b[i]) for i in range(n)])
        means.append((statistics.mean(b), statistics.mean(h)))

    pvalues, effects, resolutions = [], [], []
    for r, (base_mean, _) in zip(log_ratios, means):
        mean_r = statistics.mean(r)
        spread = statistics.stdev(r) if len(r) > 1 else 0.0
        if spread == 0.0:
            # A perfectly-consistent difference across every round; the t-test is undefined here, but the evidence is as
            # strong as it can get.
            pvalues.append(0.0 if mean_r != 0.0 else 1.0)
            crit = 0.0
        else:
            pvalues.append(float(stats.ttest_1samp(r, 0.0).pvalue))
            crit = stats.t.ppf(1 - alpha / 2, len(r) - 1) * spread / math.sqrt(len(r))
        resolutions.append(max((math.exp(crit) - 1) * 100, QUANTUM_SECONDS / base_mean * 100))
        effects.append((math.exp(mean_r) - 1) * 100)

    in_focus = [any(key == f or key.startswith(f + "/") for f in result.focus) for key in keys]
    result.focus_count = sum(in_focus)
    qvalues = list(pvalues)
    if use_fdr:
        for family in (True, False):
            members = [i for i, flag in enumerate(in_focus) if flag == family]
            for i, q in zip(members, _benjamini_hochberg([pvalues[i] for i in members])):
                qvalues[i] = q

    for i, key in enumerate(keys):
        base_mean, head_mean = means[i]
        if (qvalues[i] < alpha and abs(effects[i]) >= floor_pct
                and abs(head_mean - base_mean) >= floor_seconds):
            effect = effects[i]
            result.movers.append(Mover(
                test=key,
                base_mean=base_mean,
                head_mean=head_mean,
                effect_pct=effect,
                speedup_pct=(math.exp(-math.log1p(effect / 100)) - 1) * 100,
                q=qvalues[i],
                direction="slower" if effect > 0 else "faster",
            ))
    result.movers.sort(key=lambda m: -abs(m.effect_pct))
    result.neutral_count = len(keys) - len(result.movers)
    result.per_test_resolution_pct = dict(zip(keys, resolutions))

    resolvable = sorted(res for res, (base_mean, _) in zip(resolutions, means)
                        if base_mean >= RESOLUTION_MIN_SECONDS)
    result.quantized_count = len(keys) - len(resolvable)
    if resolvable:
        result.resolution_median_pct = statistics.median(resolvable)
        result.resolution_p90_pct = resolvable[min(len(resolvable) - 1, int(0.9 * len(resolvable)))]
    return result


def _dash(text):
    """An em dash always gets a non-breaking space before it; the body is soft-wrap rendered."""
    return text.replace(" " + EM_DASH, NBSP + EM_DASH)


def _change(mover):
    """A mover's size as the PR reader wants it. A speedup is the reciprocal of the time ratio; a slowdown is the time
    ratio itself — so either one reads as a positive percentage."""
    if mover.direction == "faster":
        return f"{abs(mover.speedup_pct):.1f}% speedup"
    return f"{mover.effect_pct:.1f}% slowdown"


def render_markdown(analysis, provenance):
    res = (f"what this run resolves ({PLUS_MINUS}{analysis.resolution_median_pct:.1f}% for a typical test, "
           f"{PLUS_MINUS}{analysis.resolution_p90_pct:.1f}% for the noisiest tenth)")
    lines = ["## Performance", ""]

    if analysis.is_neutral:
        lines.append(_dash(
            f"The changes in this PR are performance-neutral when measured against our web "
            f"benchmarks {EM_DASH} no test moved beyond {res}."))
    else:
        top = analysis.movers[0]
        claim = (f"The changes in this PR result in a {_change(top)} in the `{top.test}` test "
                 f"in our web benchmarks")
        others = len(analysis.movers) - 1
        if others:
            claim += f", and {others} other test{'s' if others > 1 else ''} moved"
        lines.append(_dash(f"{claim}; every other test is neutral within {res}."))

    lines += ["", "<details>", "<summary>Benchmark run details</summary>", ""]
    if analysis.movers:
        lines += ["| Test | Base | Head | Change | q |", "|---|---:|---:|---:|---:|"]
        for m in analysis.movers:
            lines.append(f"| `{m.test}` | {m.base_mean * 1000:.2f}ms | {m.head_mean * 1000:.2f}ms "
                         f"| {_change(m)} | {m.q:.4f} |")
        lines.append("")

    lines.append(f"{analysis.neutral_count} test(s) neutral over {analysis.rounds} paired rounds. "
                 f"Resolution: {analysis.resolution_median_pct:.1f}% median, "
                 f"{analysis.resolution_p90_pct:.1f}% at the 90th percentile.")
    if analysis.quantized_count:
        lines.append(f"{analysis.quantized_count} test(s) run under {RESOLUTION_MIN_SECONDS * 1000:.0f}ms "
                     f"and are resolved only to the {QUANTUM_SECONDS * 1000:.1f}ms timer quantum; "
                     "the resolution figures leave them out.")
    if analysis.focus:
        lines.append(f"Focus (declared before the run): {', '.join(analysis.focus)} "
                     f"({analysis.focus_count} test{'s' if analysis.focus_count != 1 else ''})")
    for label, key in (("Baseline", "baseline"), ("Branch", "branch"), ("Benchmarks", "benchmarks"),
                       ("Build", "build"), ("Machine", "machine"), ("Calibration", "calibration"),
                       ("Suites", "suites")):
        if provenance.get(key):
            lines.append(f"{label}: {provenance[key]}")
    if analysis.coverage_changes:
        lines.append(f"Coverage changes (present in only one arm): {', '.join(analysis.coverage_changes)}")
    if analysis.invalid:
        lines.append(f"Dropped as invalid: {', '.join(analysis.invalid)}")
    lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def _load(paths):
    return [json.load(open(p)) for p in paths]


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", nargs="+", required=True, help="per-round results.json for the baseline arm")
    parser.add_argument("--head", nargs="+", required=True, help="per-round results.json for the branch arm")
    parser.add_argument("--floor-pct", type=float, default=1.0)
    parser.add_argument("--focus", nargs="*", default=[],
                        help="suites or benchmark/test keys the change targets, declared before the run")
    parser.add_argument("--provenance", help="the provenance.json bench_pr.py archived with the rounds")
    parser.add_argument("-o", "--output", default="pr-perf-section.md")
    args = parser.parse_args()
    if len(args.base) < 2 or len(args.head) < 2:
        parser.error("at least 2 rounds per arm are needed; one round can't tell a change from noise")

    analysis = analyze(_load(args.base), _load(args.head), floor_pct=args.floor_pct, focus=args.focus)
    provenance = json.load(open(args.provenance)) if args.provenance else {}
    markdown = render_markdown(analysis, provenance)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(markdown)


if __name__ == "__main__":
    main()
