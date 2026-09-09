# Measuring a branch before you open a PR

`bench_pr.py` answers one question about a Ladybird branch: Do the changes in this branch affect how fast the engine runs the benchmarks in this repository? It compiles the branch and its merge-base, runs both against every suite in an interleaved loop, tests the difference for significance, and writes a section you can paste into the body of the PR description:

> The changes in this PR are performance-neutral when measured against our web benchmarks — no test moved beyond what this run resolves (±3.1% for a typical test, ±10.7% for the noisiest tenth).

…or, when something did move:

> The changes in this PR result in a 6.3% speedup in the `MicroWeb/dom/query-selector-class` test in our web benchmarks; every other test is neutral within what this run resolves (±3.1% for a typical test, ±10.7% for the noisiest tenth).

Nothing about the section is handwritten. If the tool hasn’t run against the branch, the PR gets no performance section at all.

## What you need

- A Ladybird checkout with your branch committed. A worktree is fine.
- The Python requirements from this repository (`pip install -r requirements.txt`). A `.venv` beside these scripts is picked up automatically.
- About 24 minutes of an idle machine per run, plus one-off compile time for each arm the first time it sees a commit.
- A machine plugged in to “mains” AC power. The tool refuses to start when the machine is running on battery power.

Everything it writes lives under `$XDG_CACHE_HOME/ladybird-bench` (`~/.cache/ladybird-bench` by default): the two worktrees, the compile logs, one directory of raw results per run, and the calibration record.

## Calibrate the machine once

Before the first real comparison, measure the machine against itself:

```bash
cd "${LADYBIRD_SOURCE_DIR}"          # a checkout on master
/path/to/web-benchmarks/bench_pr.py --calibrate
```

That runs the identical loop with both arms bound to the *same* compiled browser — so every difference it reports is noise. It should report no movers at all:

```
A-vs-A calibration: resolution 3.37% median, 7.67% p90 (85 sub-2ms tests left out)
false movers (should be 0): 0
```

The resolution is the smallest true change the run could have detected, per test, at this sample size and this machine’s noise. A non-zero false-mover count means the machine is too noisy to trust at these settings; in other words, it means you need to close down some other running apps/processes, or raise `--rounds`, and calibrate again.

The record is kept and consulted by later runs — which warn when it’s missing, over 30 days old, or from a different machine, benchmarks revision, or compiler configuration. Only a calibration over the whole suite battery is recorded — so a narrowed experimental one can’t overwrite it.

## Measure a branch

```bash
cd /path/to/ladybird-worktrees/my-branch
/path/to/web-benchmarks/bench_pr.py
```

That fetches `origin/master`, takes the merge-base as the baseline, and refuses to run if the checkout has uncommitted tracked changes — the thing measured has to be the thing you push. Untracked files are ignored — so notes beside the code are fine.

The result is written to `pr-perf-section.md` in the current directory, and printed out to the terminal. Add `--dry-run` to see the plan and the estimate without running anything.

## Reading the output

The details block under the claim carries everything needed to judge it:

```
779 test(s) neutral over 7 paired rounds. Resolution: 3.1% median, 10.7% at the 90th percentile.
86 test(s) run under 2ms and are resolved only to the 0.1ms timer quantum; the resolution
figures leave them out.
Baseline: e6b803be8dc
Branch: ad0ed72c4d0
Benchmarks: c85ef85
Build: Distribution preset, AppleClang 21.0.0.21000333, ThinLTO
Machine: Mac17,7, 18 cores, macOS 27.0
Calibration: A-vs-A on 20260908: 0 false mover(s), resolution ±7.3% p90
Suites: MicroWeb, Speedometer2, Speedometer3, StyleBench, ...
```

When tests *do* move, a table lists each one with its base and head means, the change, and its q-value — the false-discovery rate you accept by believing that row. Two more lines appear when they apply: coverage changes (a test present in only one arm, never reported as a mover), and tests dropped as invalid (a non-positive time).

## What a run can and cannot see

Every claim is bounded by what the run resolves, and a single test moving on its own is the hardest thing to catch: its evidence has to survive a false-discovery correction over some 780 tests. Simulated against the noise one calibration actually measured, at 7 rounds (one fewer than the default, which does slightly better):

| Change | Reported |
|---|---|
| Every Speedometer3 test 3% faster | 100% |
| One typical test 10% faster | 52% |
| One test in a declared `--focus` suite, 5% faster | 40% |
| One typical test 5% faster | 15% |
| One typical test 5% faster, `--rounds 15` | 62% |
| Nothing (A-vs-A) | 0.03 false movers per run |

So a neutral result means “nothing moved by more than the run resolves”, not “nothing changed” — which is exactly what the claim says. Two ways to sharpen it when a single test is the point of the change:

- `--focus WebKitSVG` (or `--focus 'MicroWeb/dom/create-element'`) puts the tests a change targets in their own family, so they aren’t corrected against hundreds of unrelated ones. Declare it before the run; picking the family after seeing the numbers is a good way to fool yourself.
- `--rounds 16` roughly doubles the wait and buys real sensitivity; keep the count even, so that each arm goes first as often as the other. `--iterations 3` averages more work per launch, which cuts the per-round spread but not the degrees of freedom — so it helps much less than rounds do.

## How the measurement works

Each round runs both arms of one suite back-to-back — then the next suite, with the arm order flipped, and the whole round order alternates as well. So the two measurements of a test are seconds apart rather than a battery apart, and slow drift cancels between neighbors. The default round count is even, so that in every suite each arm goes first exactly as often as the other; an odd `--rounds` leaves one arm ahead by a round. The first round is a warmup and is discarded.

For each test, the run takes the log ratio of head-to-base per-round — which makes a speedup and the matching slowdown symmetric, and applies a paired one-sample t-test over the rounds. The resulting p-values go through Benjamini-Hochberg across all tests; without that, 780 tests at alpha 0.05 produce a dozen imaginary movers every single run. A test is reported only if its q-value is under 0.05 *and* it moved by at least 1% *and* by at least 0.2 ms.

That last floor exists because `performance.now()` is coarsened to 0.1ms: every measurement is a multiple of that, tests shorter than a couple of milliseconds are only a few quanta long, and a value sitting on a rounding boundary produces a perfectly-consistent one-quantum “difference” that no amount of statistics can see through. For the same reason, a test’s resolution is never quoted below one quantum of its own time — and the resolution figures in the section leave the sub-2ms tests out.

## Both arms have to be compiled the same way

A comparison between two differently-compiled browsers measures the *compiler*, not the branch. That’s not hypothetical: Until Ladybird’s `CMakeLists.txt` was reordered to define `ENABLE_LTO_FOR_RELEASE` before `compile_options` reads it, a Release or Distribution tree skipped LTO on a first configure and turned it on at the second — so a freshly-created worktree and a reused one differed by a whole optimization mode. An A/B run between two such trees reported 209 tests moving by 3% to 100% — every one of those moves fictional.

So, the tool configures both arms itself with `-DENABLE_LTO_FOR_RELEASE=ON` — however old the commit is. And before any measurement, it compares the compile line and the object-file kind (LLVM bitcode versus native) of one reference TU between the arms. Any difference stops the run, rather than producing a number. If it does stop, delete the offending worktree’s `Build` directory, and start over.

## Preflight

Every check exists because it changes measured times: mains power (blocking), one-minute load above a quarter of the core count (blocking) or a sixth (warning), thermal pressure at `serious` or worse (blocking) or `fair` (warning), an already-running Ladybird (warning: it’s somebody’s browser, so it’s never killed), and the state of the calibration record (warning). `--force` overrides the blocking ones, and leaves it up to you how much trust you want to have/assert about the result.

## Options

| Option | Meaning |
|---|---|
| `--rounds N` | Kept rounds per arm, default 8 and at least 2; an even count keeps the arm order balanced. A warmup round is always run and discarded. |
| `--iterations K` | Benchmark iterations per browser launch, default 1. |
| `--benchmarks A,B` | Suites to run, default all ten. |
| `--focus X [Y ...]` | Suites or `Benchmark/test` keys judged as their own family. |
| `--calibrate` | A-vs-A run against the current commit; records the noise floor. |
| `--dry-run` | Print the plan and the estimate, run nothing. |
| `--force` | Run even though preflight objects. |
| `--ladybird DIR` | The checkout to measure, default the current directory. |
| `--worktree-root DIR` | Where the two arms’ worktrees live. |
| `-o FILE` | Where to write the section, default `pr-perf-section.md`. |

## Re-analyzing a finished run

Every run archives its per-round results and provenance. So, the section can be rebuilt — with different options, or after a change to the analysis — without measuring again:

```bash
A=~/.cache/ladybird-bench/e6b803be8dc..ad0ed72c4d0-20260909-002312
./bench_compare.py --base $A/r{1,2,3,4,5,6,7,8}-base.json --head $A/r{1,2,3,4,5,6,7,8}-head.json \
    --provenance $A/provenance.json --focus WebKitSVG
```

## Tests

The planning logic, the analysis, and bench_pr.py's own argument checks are covered by unit tests that need no browser or build:

```bash
python -m unittest test_bench_plan test_bench_compare test_bench_pr
```
