#!/usr/bin/env python3
"""Tests for the parts of bench_pr.py that need no build and no browser: its argument checks, and the cache seed a
fresh worktree gets."""
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
