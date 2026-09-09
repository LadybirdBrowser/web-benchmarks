#!/usr/bin/env python3
"""Tests for bench_compare: paired log-ratio analysis of interleaved benchmark rounds."""
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import unittest

import bench_compare

HERE = os.path.dirname(os.path.abspath(__file__))


def results(times, benchmark="MicroWeb"):
    """Build one round's results.json payload from {test_key: seconds}."""
    payload = {benchmark: {}}
    for key, seconds in times.items():
        payload[benchmark][key] = {
            "category": "Web",
            "time": {"mean": seconds, "stdev": 0.0, "min": seconds, "max": seconds, "runs": [seconds]},
        }
    payload[benchmark]["_total"] = {
        "time": {"mean": sum(times.values()), "stdev": 0.0, "min": 0, "max": 0, "runs": [sum(times.values())]}
    }
    return payload


def rounds(per_round_times):
    return [results(t) for t in per_round_times]


class RoundCount(unittest.TestCase):
    """One round per arm has no spread to measure, so every non-zero difference would come out as certain."""

    def test_a_single_round_per_arm_is_rejected(self):
        base = [{"dom/create-element": 0.100}]
        head = [{"dom/create-element": 0.103}]
        with self.assertRaises(ValueError):
            bench_compare.analyze(rounds(base), rounds(head))

    def test_no_rounds_at_all_are_rejected_rather_than_reported_neutral(self):
        with self.assertRaises(ValueError):
            bench_compare.analyze([], [])


class IdenticalInputs(unittest.TestCase):
    def test_identical_rounds_report_no_movers(self):
        same = [{"dom/create-element": 0.100, "dom/query-selector": 0.200}] * 7
        out = bench_compare.analyze(rounds(same), rounds(same))
        self.assertEqual(out.movers, [])
        self.assertEqual(out.neutral_count, 2)
        self.assertTrue(out.is_neutral)


class InjectedRegression(unittest.TestCase):
    def test_uniform_5_percent_slowdown_is_flagged_as_slower(self):
        rng = random.Random(1234)
        base, head = [], []
        for _ in range(7):
            b = {"dom/create-element": 0.100 * (1 + rng.gauss(0, 0.01)),
                 "dom/query-selector": 0.200 * (1 + rng.gauss(0, 0.01))}
            h = dict(b)
            h["dom/create-element"] = b["dom/create-element"] * 1.05
            base.append(b)
            head.append(h)
        out = bench_compare.analyze(rounds(base), rounds(head))

        self.assertEqual(len(out.movers), 1, f"expected exactly one mover, got {out.movers}")
        mover = out.movers[0]
        self.assertEqual(mover.test, "MicroWeb/dom/create-element")
        self.assertEqual(mover.direction, "slower")
        self.assertAlmostEqual(mover.effect_pct, 5.0, delta=0.3)


class InjectedSpeedup(unittest.TestCase):
    """The direction trap: these are times, so faster means a NEGATIVE effect."""

    def setUp(self):
        rng = random.Random(99)
        base, head = [], []
        for _ in range(7):
            b = {"dom/create-element": 0.100 * (1 + rng.gauss(0, 0.01))}
            h = {"dom/create-element": b["dom/create-element"] / 1.05}  # 5% speedup
            base.append(b)
            head.append(h)
        self.out = bench_compare.analyze(rounds(base), rounds(head))

    def test_flagged_as_faster(self):
        self.assertEqual(len(self.out.movers), 1)
        self.assertEqual(self.out.movers[0].direction, "faster")

    def test_speedup_percent_is_the_reciprocal_not_the_effect(self):
        # head = base/1.05 -> effect_pct is about -4.76, but the speedup is 5.00.
        mover = self.out.movers[0]
        self.assertAlmostEqual(mover.effect_pct, -4.76, delta=0.3)
        self.assertAlmostEqual(mover.speedup_pct, 5.0, delta=0.3)

    def test_rendered_sentence_says_speedup_with_the_speedup_number(self):
        md = bench_compare.render_markdown(self.out, provenance={})
        self.assertIn("5.0% speedup", md)
        self.assertNotIn("slowdown", md)


class FalseDiscoveryControl(unittest.TestCase):
    def _trials(self, use_fdr):
        rng = random.Random(7)
        flagged_trials = 0
        for _ in range(100):
            base, head = [], []
            for _ in range(7):
                b = {f"t{i}": 0.100 * (1 + rng.gauss(0, 0.025)) for i in range(230)}
                h = {f"t{i}": 0.100 * (1 + rng.gauss(0, 0.025)) for i in range(230)}
                base.append(b)
                head.append(h)
            out = bench_compare.analyze(rounds(base), rounds(head), use_fdr=use_fdr, floor_pct=0.0)
            if out.movers:
                flagged_trials += 1
        return flagged_trials

    def test_fdr_keeps_false_discoveries_rare_across_230_null_tests(self):
        self.assertLessEqual(self._trials(use_fdr=True), 15)

    def test_without_fdr_the_same_data_flags_almost_every_trial(self):
        # Proves the FDR step is doing real work rather than the floor hiding everything.
        self.assertGreaterEqual(self._trials(use_fdr=False), 90)


class CoverageAndInvalidInputs(unittest.TestCase):
    def test_test_only_in_head_is_a_coverage_change_not_a_mover(self):
        base = [{"a": 0.1}] * 7
        head = [{"a": 0.1, "b": 0.2}] * 7
        out = bench_compare.analyze(rounds(base), rounds(head))
        self.assertEqual(out.movers, [])
        self.assertIn("MicroWeb/b", out.coverage_changes)

    def test_non_positive_time_is_dropped_and_reported_invalid(self):
        base = [{"a": 0.1, "bad": 0.0}] * 7
        head = [{"a": 0.1, "bad": 0.1}] * 7
        out = bench_compare.analyze(rounds(base), rounds(head))
        self.assertIn("MicroWeb/bad", out.invalid)
        self.assertNotIn("MicroWeb/bad", [m.test for m in out.movers])


class Rendering(unittest.TestCase):
    def test_neutral_output_states_the_resolution(self):
        same = [{"a": 0.1}] * 7
        out = bench_compare.analyze(rounds(same), rounds(same))
        md = bench_compare.render_markdown(out, provenance={"baseline": "abc1234", "branch": "def5678"})
        self.assertIn("The changes in this PR are performance-neutral when measured against our web benchmarks", md)
        self.assertIn("for a typical test", md)
        self.assertIn("for the noisiest tenth", md)
        self.assertIn("abc1234", md)

    def test_typography_rules_hold(self):
        same = [{"a": 0.1}] * 7
        out = bench_compare.analyze(rounds(same), rounds(same))
        md = bench_compare.render_markdown(out, provenance={"baseline": "abc1234"})
        EM, NBSP = chr(0x2014), chr(0xa0)
        for i, ch in enumerate(md):
            if ch == EM:
                self.assertEqual(md[i - 1], NBSP, "every em dash needs a preceding NBSP")
        self.assertNotIn('"', md)
        self.assertNotIn("`abc1234`", md)  # SHAs stay unbackticked so GitHub auto-links them


def multi_results(per_benchmark):
    """One round's payload spanning several benchmarks: {benchmark: {test: seconds}}."""
    payload = {}
    for benchmark, times in per_benchmark.items():
        payload.update(results(times, benchmark))
    return payload


class TimerQuantization(unittest.TestCase):
    """Ladybird reports performance.now() coarsened to 0.1ms, so every measured time is a multiple of 0.1ms and the
    shortest tests (down to 0.1ms) move in steps of 10-100%."""

    def test_a_one_quantum_shift_on_a_sub_millisecond_test_is_not_a_mover(self):
        # 0.3ms -> 0.4ms in every round is a 33% effect with zero spread, and a value straddling a rounding boundary
        # produces exactly that; it proves nothing.
        base = [{"tiny": 0.0003}] * 7
        head = [{"tiny": 0.0004}] * 7
        out = bench_compare.analyze(rounds(base), rounds(head))
        self.assertEqual(out.movers, [])

    def test_a_consistent_shift_of_several_quanta_is_still_reported(self):
        base = [{"short": 0.0010}] * 7
        head = [{"short": 0.0014}] * 7
        out = bench_compare.analyze(rounds(base), rounds(head))
        self.assertEqual([m.test for m in out.movers], ["MicroWeb/short"])

    def test_identical_quantized_values_do_not_claim_perfect_resolution(self):
        # A 3ms test that reads the same in every round can still hide a one-quantum change — so its resolution is one
        # quantum relative to its time, not zero.
        same = [{"three-ms": 0.0030}] * 7
        out = bench_compare.analyze(rounds(same), rounds(same))
        self.assertGreaterEqual(out.per_test_resolution_pct["MicroWeb/three-ms"], 3.3)

    def test_sub_two_millisecond_tests_stay_out_of_the_quoted_resolution(self):
        rng = random.Random(5)
        base, head = [], []
        for _ in range(7):
            base.append({"tiny": 0.0005, "big": 0.100 * (1 + rng.gauss(0, 0.01))})
            head.append({"tiny": 0.0005, "big": 0.100 * (1 + rng.gauss(0, 0.01))})
        out = bench_compare.analyze(rounds(base), rounds(head))
        self.assertEqual(out.quantized_count, 1)
        self.assertLess(out.resolution_p90_pct, 5.0, "the 0.5ms test's 20% quantum must not set the p90")


class ClaimWording(unittest.TestCase):
    """The PR section's claim line reads as the one the harness was asked for."""

    def _shifted(self, factors):
        base = [{k: 0.100 for k in factors}] * 7
        head = [{k: 0.100 * f for k, f in factors.items()}] * 7
        return bench_compare.analyze(rounds(base), rounds(head))

    def test_neutral_claim(self):
        out = self._shifted({"a": 1.0, "b": 1.0})
        md = bench_compare.render_markdown(out, provenance={})
        self.assertIn("The changes in this PR are performance-neutral when measured against "
                      "our web benchmarks", md)

    def test_single_speedup_names_the_test(self):
        out = self._shifted({"dom/create-element": 1 / 1.05, "other": 1.0})
        md = bench_compare.render_markdown(out, provenance={})
        self.assertIn("The changes in this PR result in a 5.0% speedup in the "
                      "`MicroWeb/dom/create-element` test in our web benchmarks", md)

    def test_single_slowdown_names_the_test(self):
        out = self._shifted({"dom/create-element": 1.05, "other": 1.0})
        md = bench_compare.render_markdown(out, provenance={})
        self.assertIn("result in a 5.0% slowdown in the `MicroWeb/dom/create-element` test", md)

    def test_several_movers_count_the_rest(self):
        out = self._shifted({"a": 1 / 1.10, "b": 1 / 1.05, "c": 1.03})
        md = bench_compare.render_markdown(out, provenance={})
        self.assertIn("result in a 10.0% speedup in the `MicroWeb/a` test in our web benchmarks, "
                      "and 2 other tests moved", md)


class FocusFamily(unittest.TestCase):
    """A family of tests declared before the run is judged on its own — so a real change in the tests the PR targets is
    not drowned by the false-discovery correction over hundreds of unrelated tests."""

    def setUp(self):
        rng = random.Random(2024)
        self.base, self.head = [], []
        for _ in range(7):
            b = {"MicroWeb": {f"t{i}": 0.100 * (1 + rng.gauss(0, 0.03)) for i in range(400)},
                 "WebKitSVG": {"paths": 0.100 * (1 + rng.gauss(0, 0.012))}}
            h = {"MicroWeb": {f"t{i}": 0.100 * (1 + rng.gauss(0, 0.03)) for i in range(400)},
                 "WebKitSVG": {"paths": 0.100 * (1 + rng.gauss(0, 0.012)) / 1.04}}
            self.base.append(multi_results(b))
            self.head.append(multi_results(h))

    def test_without_a_focus_the_change_is_lost_among_hundreds_of_tests(self):
        out = bench_compare.analyze(self.base, self.head)
        self.assertNotIn("WebKitSVG/paths", [m.test for m in out.movers])

    def test_with_the_suite_declared_as_focus_the_change_is_found(self):
        out = bench_compare.analyze(self.base, self.head, focus=["WebKitSVG"])
        self.assertEqual([m.test for m in out.movers], ["WebKitSVG/paths"])

    def test_the_focus_is_stated_in_the_details(self):
        out = bench_compare.analyze(self.base, self.head, focus=["WebKitSVG"])
        md = bench_compare.render_markdown(out, provenance={})
        self.assertIn("Focus (declared before the run): WebKitSVG (1 test)", md)


class CommandLine(unittest.TestCase):
    """bench_compare.py as a command, the way a re-analysis of an archived run invokes it."""

    def test_one_round_per_arm_is_refused_with_a_message_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r1.json")
            with open(path, "w") as f:
                json.dump(results({"dom/create-element": 0.100}), f)
            proc = subprocess.run([sys.executable, os.path.join(HERE, "bench_compare.py"),
                                   "--base", path, "--head", path, "-o", os.path.join(tmp, "out.md")],
                                  capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("2 rounds", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
