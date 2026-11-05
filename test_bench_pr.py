#!/usr/bin/env python3
"""Tests for the parts of bench_pr.py that need no build and no browser: its argument checks, the cache seed a fresh
worktree gets, and which executables a relink covers."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

import bench_plan
import bench_pr

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH_PR = os.path.join(HERE, "bench_pr.py")


class Arguments(unittest.TestCase):
    def test_fewer_than_two_kept_rounds_is_refused_before_anything_runs(self):
        # One round per arm can't separate a change from noise. A bogus checkout makes sure that nothing but the
        # argument check gets a say.
        proc = subprocess.run([sys.executable, BENCH_PR, "--rounds", "1", "--dry-run", "--ladybird", "/nonexistent"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("--rounds", proc.stderr)



class FailingSuites(unittest.TestCase):
    """run_pair over a stand-in run_suite that fails for the arms given: per attempt, the set of arms that fail."""

    def run_pair(self, is_warmup, failures):
        attempts = iter(failures)
        calls = []
        current = {}

        def fake_run_suite(executable, suite, iterations, out_path):
            arm = executable
            if not calls or calls[-1][0] == "head":
                current["failing"] = next(attempts)
            calls.append((arm, suite))
            return arm not in current["failing"]

        rnd = bench_plan.Round(index=0 if is_warmup else 1, is_warmup=is_warmup, order=("base", "head"))
        original = bench_pr.run_suite
        bench_pr.run_suite = fake_run_suite
        try:
            with tempfile.TemporaryDirectory() as archive, contextlib.redirect_stdout(io.StringIO()):
                return bench_pr.run_pair(rnd, "WebKitCSS", ["base", "head"], {"base": "base", "head": "head"}, 1,
                                         archive, "warmup" if is_warmup else "round 1/8"), calls
        finally:
            bench_pr.run_suite = original

    def test_a_suite_that_fails_in_both_arms_both_times_in_the_warmup_is_left_out(self):
        outs, calls = self.run_pair(True, [{"base", "head"}, {"base", "head"}])
        self.assertIsNone(outs)
        # Both arms ran on both attempts, so the failure is known to be in both.
        self.assertEqual([arm for arm, _ in calls], ["base", "head", "base", "head"])

    def test_a_suite_that_fails_in_only_one_arm_in_the_warmup_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.run_pair(True, [{"base"}, {"base"}])

    def test_a_suite_that_fails_in_both_arms_in_a_kept_round_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.run_pair(False, [{"base", "head"}, {"base", "head"}])

    def test_a_suite_that_fails_in_each_arm_once_stops_the_run(self):
        # Neither arm failed both times, so the suite runs at both revisions; the failures were stalls, not a hang.
        with self.assertRaises(SystemExit):
            self.run_pair(True, [{"base"}, {"head"}])

    def test_a_failure_the_retry_clears_keeps_the_suite(self):
        outs, _ = self.run_pair(True, [{"base", "head"}, set()])
        self.assertEqual(sorted(outs), ["base", "head"])

class CacheSeed(unittest.TestCase):
    def test_a_fresh_worktree_gets_a_copy_of_the_source_tree_caches(self):
        # With whichever cp this platform has: macOS's clones on APFS, GNU's has no clone flag at all.
        with tempfile.TemporaryDirectory() as tmp:
            source_repo, tree = os.path.join(tmp, "source"), os.path.join(tmp, "tree")
            os.makedirs(os.path.join(source_repo, "Build/caches/ccache"))
            os.makedirs(os.path.join(tree, "Build"))
            with open(os.path.join(source_repo, "Build/caches/ccache/entry"), "w") as f:
                f.write("object")
            bench_pr.seed_caches(source_repo, tree)
            with open(os.path.join(tree, "Build/caches/ccache/entry")) as f:
                self.assertEqual(f.read(), "object")


class VcpkgCheckout(unittest.TestCase):
    @staticmethod
    def make(tmp, baseline=None):
        """A tree whose vcpkg.json names the baseline, and a vcpkg checkout of one commit: the baseline, by default."""
        checkout = os.path.join(tmp, "Build/vcpkg")
        subprocess.run(["git", "init", "-q", checkout], check=True)
        subprocess.run(["git", "-C", checkout, "-c", "user.name=bench", "-c", "user.email=bench@localhost", "commit",
                        "-q", "--allow-empty", "--no-verify", "--no-gpg-sign", "-m", "ports"], check=True)
        with open(os.path.join(tmp, "vcpkg.json"), "w") as f:
            json.dump({"builtin-baseline": baseline or bench_pr.git(["rev-parse", "HEAD"], checkout)}, f)
        return checkout

    def test_a_checkout_at_the_tree_baseline_needs_no_steps(self):
        with tempfile.TemporaryDirectory() as tree:
            checkout = self.make(tree)
            self.assertEqual(bench_pr.vcpkg_steps(checkout, tree), [])

    def test_a_checkout_at_another_baseline_is_checked_out_at_the_tree_baseline_and_bootstrapped(self):
        # An arm's checkout stays at whatever baseline its tree named when the arm was last built, and a later commit
        # of the tree can name another.
        baseline = "20ceb8adbf0504d4b0d5e4058a32f9d4fc896391"
        with tempfile.TemporaryDirectory() as tree:
            checkout = self.make(tree, baseline)
            steps = bench_pr.vcpkg_steps(checkout, tree)
            self.assertEqual(steps[:2], [["git", "-C", checkout, "fetch", "origin"],
                                         ["git", "-C", checkout, "checkout", "--detach", baseline]])
            self.assertEqual(steps[2][1:], ["-disableMetrics"])
            self.assertEqual(os.path.dirname(steps[2][0]), checkout)


class RunLock(unittest.TestCase):
    @unittest.skipIf(bench_pr.fcntl is None, "no flock on this platform")
    def test_a_second_run_is_refused_while_the_first_holds_the_cache(self):
        with tempfile.TemporaryDirectory() as root:
            first, _ = bench_pr.hold_run_lock(root)
            self.assertIsNotNone(first)
            second, holder = bench_pr.hold_run_lock(root)
            self.assertIsNone(second)
            self.assertIn(f"pid {os.getpid()}", holder)
            first.close()
            third, _ = bench_pr.hold_run_lock(root)
            self.assertIsNotNone(third)
            third.close()


class RunnableExecutables(unittest.TestCase):
    @staticmethod
    def make(build, paths):
        for rel in paths:
            os.makedirs(os.path.join(build, os.path.dirname(rel)), exist_ok=True)
            open(os.path.join(build, rel), "w").close()

    def test_on_macos_every_binary_in_the_bundle_is_relinked_and_the_browser_last(self):
        # The browser's link command re-signs the bundle, so every helper has to be in place before it runs.
        with tempfile.TemporaryDirectory() as build:
            macos = "bin/Ladybird.app/Contents/MacOS"
            self.make(build, [f"{macos}/WebContent", f"{macos}/Ladybird", f"{macos}/Compositor"])
            self.assertEqual(bench_pr.runnable_executables(build, "Darwin"),
                             [f"{macos}/Compositor", f"{macos}/WebContent", f"{macos}/Ladybird"])

    def test_elsewhere_the_libexec_helpers_are_relinked_and_then_the_browser(self):
        with tempfile.TemporaryDirectory() as build:
            self.make(build, ["libexec/WebContent", "libexec/RequestServer", "bin/Ladybird"])
            os.makedirs(os.path.join(build, "libexec/not-a-binary"))
            self.assertEqual(bench_pr.runnable_executables(build, "Linux"),
                             ["libexec/RequestServer", "libexec/WebContent", "bin/Ladybird"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
