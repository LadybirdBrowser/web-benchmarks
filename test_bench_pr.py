#!/usr/bin/env python3
"""Tests for the parts of bench_pr.py that need no build and no browser: its argument checks, the cache seed a fresh
worktree gets, and which executables a relink covers."""
import os
import subprocess
import sys
import tempfile
import unittest

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
