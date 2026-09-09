#!/usr/bin/env python3
"""Tests for the pure decision logic in bench_plan: round ordering, preflight and parity."""
import datetime
import os
import unittest
import unittest.mock

import bench_plan


class RoundPlan(unittest.TestCase):
    def test_first_round_is_a_discarded_warmup(self):
        plan = bench_plan.round_plan(7)
        self.assertTrue(plan[0].is_warmup)
        self.assertEqual(sum(1 for r in plan if r.is_warmup), 1)

    def test_the_default_kept_rounds_come_with_one_warmup_on_top(self):
        plan = bench_plan.round_plan(bench_plan.DEFAULT_KEPT_ROUNDS)
        self.assertEqual(len(plan), bench_plan.DEFAULT_KEPT_ROUNDS + 1)
        self.assertEqual(sum(1 for r in plan if not r.is_warmup), bench_plan.DEFAULT_KEPT_ROUNDS)

    def test_arm_order_alternates_so_going_first_is_not_a_fixed_advantage(self):
        orders = [r.order for r in bench_plan.round_plan(7)]
        self.assertEqual(orders[0], ("base", "head"))
        self.assertEqual(orders[1], ("head", "base"))
        self.assertEqual(orders[2], ("base", "head"))

    def test_each_arm_goes_first_equally_often_across_the_default_kept_rounds(self):
        kept = [r for r in bench_plan.round_plan(bench_plan.DEFAULT_KEPT_ROUNDS) if not r.is_warmup]
        first = [r.order[0] for r in kept]
        self.assertEqual(first.count("base"), first.count("head"))


class Preflight(unittest.TestCase):
    def test_an_unreadable_power_source_warns_without_blocking(self):
        problems = bench_plan.preflight(on_ac=None, load1=0.1, ncpu=18, browser_running=False)
        self.assertEqual(len(problems), 1)
        self.assertFalse(problems[0].blocking)
        self.assertIn("AC power", problems[0].message)

    def test_battery_power_blocks_the_run(self):
        problems = bench_plan.preflight(on_ac=False, load1=0.1, ncpu=18, browser_running=False)
        self.assertTrue(any("battery" in p.message.lower() for p in problems))
        self.assertTrue(any(p.blocking for p in problems))

    def test_load_threshold_scales_with_core_count(self):
        # 2.33 on an 18-core machine is 13% busy and must not block; the same load on a 4-core machine is another story.
        self.assertEqual(bench_plan.preflight(on_ac=True, load1=2.33, ncpu=18, browser_running=False), [])
        self.assertTrue(bench_plan.preflight(on_ac=True, load1=2.33, ncpu=4, browser_running=False))

    def test_heavy_load_blocks(self):
        problems = bench_plan.preflight(on_ac=True, load1=9.0, ncpu=18, browser_running=False)
        self.assertTrue(any(p.blocking for p in problems))

    def test_a_running_browser_warns_but_never_blocks(self):
        problems = bench_plan.preflight(on_ac=True, load1=0.1, ncpu=18, browser_running=True)
        self.assertTrue(problems)
        self.assertFalse(any(p.blocking for p in problems),
                         "a running Ladybird is the daily driver; warn, never block or kill")


class SuiteSelection(unittest.TestCase):
    def test_all_ten_suites_run_by_default(self):
        # Each suite costs seconds per arm per round, so none is left out and every run makes the broadest claim it can.
        self.assertEqual(
            sorted(bench_plan.default_suites()),
            sorted(["MicroWeb", "Speedometer2", "Speedometer3", "StyleBench",
                    "StyleBenchConservative", "WebKitBindings", "WebKitCSS",
                    "WebKitDOM", "WebKitParser", "WebKitSVG"]))

    def test_the_default_battery_stays_under_twenty_five_minutes(self):
        minutes = bench_plan.estimate_seconds(bench_plan.default_suites(),
                                              kept_rounds=bench_plan.DEFAULT_KEPT_ROUNDS) / 60
        self.assertGreater(minutes, 15)
        self.assertLess(minutes, 25)


class Estimate(unittest.TestCase):
    def test_eta_sums_the_selected_suites_over_every_arm_and_round(self):
        # 7 kept rounds + 1 warmup, 2 arms: 16 runs of each selected suite.
        suites = ["WebKitCSS", "WebKitDOM"]
        expected = 16 * (bench_plan.SUITE_SECONDS["WebKitCSS"] + bench_plan.SUITE_SECONDS["WebKitDOM"])
        self.assertAlmostEqual(bench_plan.estimate_seconds(suites, kept_rounds=7), expected)

    def test_every_default_suite_has_a_measured_cost(self):
        for suite in bench_plan.default_suites():
            self.assertIn(suite, bench_plan.SUITE_SECONDS)


class ThermalPreflight(unittest.TestCase):
    """NSProcessInfo.thermalState: 0 nominal, 1 fair, 2 serious, 3 critical."""

    def _run(self, state):
        return bench_plan.preflight(on_ac=True, load1=0.1, ncpu=18, browser_running=False,
                                  thermal_state=state)

    def test_nominal_is_silent(self):
        self.assertEqual(self._run(0), [])

    def test_fair_warns_without_blocking(self):
        problems = self._run(1)
        self.assertTrue(problems)
        self.assertFalse(any(p.blocking for p in problems))

    def test_serious_or_critical_blocks(self):
        for state in (2, 3):
            self.assertTrue(any(p.blocking for p in self._run(state)), state)


class CacheRoot(unittest.TestCase):
    def test_xdg_cache_home_wins_when_it_is_set(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/xdg"}):
            self.assertEqual(bench_plan.cache_root(), "/tmp/xdg/ladybird-bench")

    def test_the_archive_of_a_run_sits_under_the_cache_root(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/xdg"}):
            self.assertEqual(bench_plan.archive_dir("a" * 40, "b" * 40, "20260909-010203"),
                             "/tmp/xdg/ladybird-bench/aaaaaaaaaaa..bbbbbbbbbbb-20260909-010203")


class Schedule(unittest.TestCase):
    """run.py launches one browser per suite anyway, so the arms alternate per suite: each suite's pair is measured
    seconds apart — instead of a whole battery apart."""

    def test_each_suite_runs_both_arms_back_to_back(self):
        rnd = bench_plan.Round(index=1, is_warmup=False, order=("base", "head"))
        steps = bench_plan.schedule(rnd, ["A", "B", "C"])
        self.assertEqual(steps, [("A", "base"), ("A", "head"), ("B", "head"), ("B", "base"),
                                 ("C", "base"), ("C", "head")])

    def test_a_head_first_round_starts_with_head(self):
        rnd = bench_plan.Round(index=2, is_warmup=False, order=("head", "base"))
        self.assertEqual(bench_plan.schedule(rnd, ["A", "B"])[:2], [("A", "head"), ("A", "base")])

    def test_at_the_default_round_count_every_suite_sees_each_arm_first_equally_often(self):
        # The order flips per suite and per round, so an odd number of kept rounds would leave one arm going first one
        # extra time in every suite — and whatever going first costs would leak into every test by 1/N of itself.
        kept = [r for r in bench_plan.round_plan(bench_plan.DEFAULT_KEPT_ROUNDS) if not r.is_warmup]
        first = {}
        for rnd in kept:
            for suite, arm in bench_plan.schedule(rnd, bench_plan.SUITES)[::2]:
                first.setdefault(suite, []).append(arm)
        for suite, arms in first.items():
            self.assertEqual(arms.count("base"), arms.count("head"), suite)


class NoiseFloor(unittest.TestCase):
    """A calibration is only worth trusting when it's recent and from this setup."""

    def setUp(self):
        self.now = datetime.datetime(2026, 9, 8, 23, 0, 0)
        self.floor = {"when": "20260908-224737", "machine": "Mac16,6, 18 cores, macOS 27.0",
                      "benchmarks": "c85ef85", "false_movers": 0, "p90_pct": 4.0,
                      "build": "Distribution preset, AppleClang 21.0.0, ThinLTO"}

    def _problems(self, floor, **overrides):
        args = dict(now=self.now, machine="Mac16,6, 18 cores, macOS 27.0", benchmarks="c85ef85",
                    build="Distribution preset, AppleClang 21.0.0, ThinLTO")
        args.update(overrides)
        return bench_plan.noise_floor_problems(floor, **args)

    def test_a_fresh_matching_calibration_is_silent(self):
        self.assertEqual(self._problems(self.floor), [])

    def test_no_calibration_warns_and_names_the_command(self):
        problems = self._problems(None)
        self.assertEqual(len(problems), 1)
        self.assertFalse(problems[0].blocking)
        self.assertIn("--calibrate", problems[0].message)

    def test_a_calibration_older_than_thirty_days_is_stale(self):
        problems = self._problems(self.floor, now=self.now + datetime.timedelta(days=31))
        self.assertTrue(any("stale" in p.message.lower() for p in problems))

    def test_another_machine_or_benchmarks_checkout_warns(self):
        self.assertTrue(self._problems(self.floor, machine="Mac15,3, 8 cores, macOS 26.1"))
        self.assertTrue(self._problems(self.floor, benchmarks="f57e0f6"))

    def test_false_movers_in_the_calibration_warn(self):
        self.assertTrue(self._problems(dict(self.floor, false_movers=2)))

    def test_a_calibration_of_a_differently_configured_build_warns(self):
        floor = dict(self.floor, build="Distribution preset, AppleClang 21.0.0, no LTO")
        self.assertEqual(self._problems(floor, build="Distribution preset, AppleClang 21.0.0, no LTO"), [])
        problems = self._problems(floor, build="Distribution preset, AppleClang 21.0.0, ThinLTO")
        self.assertTrue(any("lto" in p.message.lower() for p in problems))


class FloorRecording(unittest.TestCase):
    def test_only_a_full_battery_calibration_is_recorded(self):
        # A partial --calibrate is an experiment; it must not overwrite the record a real run is checked against.
        self.assertTrue(bench_plan.records_floor(bench_plan.default_suites()))
        self.assertTrue(bench_plan.records_floor(list(reversed(bench_plan.default_suites()))))
        self.assertFalse(bench_plan.records_floor(["WebKitSVG"]))


class BuildParity(unittest.TestCase):
    """Both arms must be compiled the same way — or else the section measures the build, not the branch."""

    FLAGS = "-O3 -flto=thin -fstack-protector-strong -std=gnu++23"

    def test_identical_flags_pass(self):
        self.assertEqual(bench_plan.build_parity_problems({"base": self.FLAGS, "head": self.FLAGS}), [])

    def test_an_lto_mismatch_blocks_and_names_the_flag(self):
        problems = bench_plan.build_parity_problems(
            {"base": self.FLAGS, "head": self.FLAGS.replace(" -flto=thin", "")})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].blocking)
        self.assertIn("-flto=thin", problems[0].message)

    def test_the_same_flags_in_another_order_block_and_say_so(self):
        # The last of a repeated option wins, so -O2 -O3 and -O3 -O2 are different builds. And a reorder can only come
        # from a build-system change in the branch — which is what the check exists to stop.
        reordered = " ".join(reversed(self.FLAGS.split()))
        problems = bench_plan.build_parity_problems({"base": self.FLAGS, "head": reordered})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].blocking)
        self.assertIn("order", problems[0].message)

    def test_lto_state_is_named_for_provenance(self):
        self.assertEqual(bench_plan.lto_state(self.FLAGS), "ThinLTO")
        self.assertEqual(bench_plan.lto_state("-O3 -flto"), "LTO")
        self.assertEqual(bench_plan.lto_state("-O3"), "no LTO")


class Iterations(unittest.TestCase):
    def test_more_iterations_cost_less_than_proportionally(self):
        # The browser launch is paid once per-suite — whatever the iteration count.
        one = bench_plan.estimate_seconds(["WebKitCSS"], kept_rounds=7, iterations=1)
        three = bench_plan.estimate_seconds(["WebKitCSS"], kept_rounds=7, iterations=3)
        self.assertGreater(three, one)
        self.assertLess(three, 3 * one)


if __name__ == "__main__":
    unittest.main(verbosity=2)
