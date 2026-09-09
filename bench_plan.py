#!/usr/bin/env python3
"""Planning and preflight for an interleaved A/B benchmark run.

Pure decision logic lives here, so it can be tested without a browser or a build; bench_pr.py does the git, compile and
subprocess work.
"""
import datetime
import os
from dataclasses import dataclass

# Every suite this repository ships. The whole battery costs about 78 seconds per arm per round — so nothing is left out
# by default: a run that covers everything makes a broader claim for the same wait.
SUITES = ["MicroWeb", "Speedometer2", "Speedometer3", "StyleBench",
          "StyleBenchConservative", "WebKitBindings", "WebKitCSS", "WebKitDOM",
          "WebKitParser", "WebKitSVG"]

# Wall seconds per run.py invocation of one suite at one iteration, launch included, measured on an 18-core Apple
# silicon Mac. They feed the ETA and nothing else — so another machine gets a wrong estimate, never a wrong measurement.
SUITE_SECONDS = {
    "MicroWeb": 19.2, "Speedometer2": 5.8, "Speedometer3": 6.7, "StyleBench": 5.3,
    "StyleBenchConservative": 5.4, "WebKitBindings": 7.0, "WebKitCSS": 5.5,
    "WebKitDOM": 6.9, "WebKitParser": 5.7, "WebKitSVG": 10.9,
}

# The part of each suite's cost that is the browser launch and the page load; it is paid once per invocation however
# many iterations the suite then runs.
LAUNCH_SECONDS = 2.5

# Kept rounds per arm. Even, so that per suite each arm goes first as often as the other: an odd count leaves one arm
# ahead by a round, and 1/N of whatever going first costs then leaks into every test's mean.
DEFAULT_KEPT_ROUNDS = 8

# A calibration older than this no longer describes the machine: macOS and the benchmarks move, and so does whatever
# else the machine runs.
CALIBRATION_MAX_AGE_DAYS = 30

# The per-test stall limit run.py applies. Its own default is 10s for several suites — which is far too tight; the
# slowest test anywhere is about 2.3s.
PER_TEST_TIMEOUT_SECONDS = 90


@dataclass(frozen=True)
class Round:
    index: int
    is_warmup: bool
    order: tuple


@dataclass(frozen=True)
class Problem:
    message: str
    blocking: bool


def default_suites():
    return list(SUITES)


def round_plan(kept_rounds):
    """Round 0 is a warmup and is discarded. Arm order alternates every round — so that whatever penalty attaches to
    going first cancels out across the run. It cancels exactly only for an even kept count; an odd one leaves one arm
    going first one extra time in every suite."""
    plan = []
    for i in range(kept_rounds + 1):
        order = ("base", "head") if i % 2 == 0 else ("head", "base")
        plan.append(Round(index=i, is_warmup=(i == 0), order=order))
    return plan


def schedule(rnd, suites):
    """The (suite, arm) steps of one round. run.py launches a browser per-suite anyway — so both arms of a suite run
    back to back, and the arm order flips from one suite to the next: the pair is seconds apart, and any drift within
    the round cancels between neighboring suites."""
    steps = []
    for i, suite in enumerate(suites):
        order = rnd.order if i % 2 == 0 else tuple(reversed(rnd.order))
        steps += [(suite, arm) for arm in order]
    return steps


def preflight(on_ac, load1, ncpu, browser_running, thermal_state=0):
    """Conditions that would make a measurement untrustworthy. A running browser is somebody's daily driver, so it warns
    and is never killed. on_ac is None where the power source can't be read, and thermal_state is NSProcessInfo's: 0
    nominal, 1 fair, 2 serious, 3 critical (0 wherever it can't be read)."""
    problems = []
    if on_ac is None:
        problems.append(Problem("Can't tell whether this machine is on AC power; on battery "
                                "the CPU throttles and the numbers drift.", blocking=False))
    elif not on_ac:
        problems.append(Problem("Running on battery power; CPU will be throttled.", blocking=True))
    if thermal_state >= 2:
        problems.append(Problem(f"Thermal state {thermal_state} (serious or worse); the CPU is "
                                "being throttled. Let the machine cool down.", blocking=True))
    elif thermal_state == 1:
        problems.append(Problem("Thermal state fair; the machine is warm and may throttle "
                                "part way through.", blocking=False))
    if load1 > ncpu / 4:
        problems.append(Problem(
            f"1-minute load {load1:.2f} exceeds {ncpu / 4:.2f} (a quarter of {ncpu} cores).", blocking=True))
    elif load1 > ncpu / 6:
        problems.append(Problem(f"1-minute load {load1:.2f} is elevated for {ncpu} cores.", blocking=False))
    if browser_running:
        problems.append(Problem("A Ladybird is already running; it will add noise.", blocking=False))
    return problems


def cache_root():
    """Where builds, archives and the calibration record live, XDG_CACHE_HOME first."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "ladybird-bench")


def lto_state(flags):
    """The link-time-optimization mode a compile line asks for, for provenance."""
    if "-flto=thin" in flags.split():
        return "ThinLTO"
    if any(flag == "-flto" or flag.startswith("-flto=") for flag in flags.split()):
        return "LTO"
    return "no LTO"


def build_parity_problems(flags_by_arm):
    """Both arms must be compiled with the same flags, or the run measures the build rather than the branch.
    flags_by_arm maps arm name to the compile line of one reference object in that arm's tree. The lines have to match
    token for token: the last of a repeated option wins, so the same flags in another order can be another build."""
    (a, a_flags), (b, b_flags) = sorted(flags_by_arm.items())
    a_tokens, b_tokens = a_flags.split(), b_flags.split()
    if a_tokens == b_tokens:
        return []
    only_a = sorted(set(a_tokens) - set(b_tokens))
    only_b = sorted(set(b_tokens) - set(a_tokens))
    detail = "; ".join(f"only {arm}: {' '.join(flags)}" for arm, flags in ((a, only_a), (b, only_b)) if flags)
    detail = detail or "the same flags in a different order or count"
    return [Problem(f"The {a} and {b} builds are compiled differently ({detail}); a comparison "
                    "between them would measure the build, not the change.", blocking=True)]


def noise_floor_problems(floor, now, machine, benchmarks, build=None):
    """Whether the calibration on record (the dict --calibrate wrote, or None) still vouches for this setup. Never
    blocking: the analysis measures its own resolution from the run's spread — and the calibration's job is to have
    shown that an A-vs-A run on this machine reports no movers."""
    if floor is None:
        return [Problem("No calibration on record for this machine; run bench_pr.py --calibrate "
                        "once so the resolution it quotes has been checked against an A-vs-A run.",
                        blocking=False)]
    problems = []
    when = datetime.datetime.strptime(floor["when"], "%Y%m%d-%H%M%S")
    age = (now - when).days
    if age > CALIBRATION_MAX_AGE_DAYS:
        problems.append(Problem(f"The calibration is stale ({age} days old); rerun "
                                "bench_pr.py --calibrate.", blocking=False))
    if floor.get("machine") != machine:
        problems.append(Problem(f"The calibration is from another machine ({floor.get('machine')}); "
                                "rerun bench_pr.py --calibrate here.", blocking=False))
    if floor.get("benchmarks") != benchmarks:
        problems.append(Problem(f"The calibration used benchmarks {floor.get('benchmarks')}, "
                                f"this run uses {benchmarks}; rerun bench_pr.py --calibrate.",
                                blocking=False))
    if floor.get("false_movers", 0):
        problems.append(Problem(f"The calibration reported {floor['false_movers']} false mover(s) "
                                "in an A-vs-A run, so a mover here may be noise.", blocking=False))
    if build is not None and floor.get("build") != build:
        problems.append(Problem(f"The calibration measured a different build ({floor.get('build')}; "
                                f"this run: {build}), e.g. with or without LTO; rerun bench_pr.py --calibrate.",
                                blocking=False))
    return problems


def records_floor(suites):
    """A calibration counts as this machine's record only when it ran the whole battery; a partial one is an experiment,
    and leaves the record alone."""
    return sorted(suites) == sorted(SUITES)


def estimate_seconds(suites, kept_rounds, iterations=1):
    """Every selected suite runs once per arm in every round, warmup included; the launch is paid per invocation and the
    tests themselves per-iteration — so an extra iteration costs less wall time than an extra round."""
    per_suite = sum(LAUNCH_SECONDS + iterations * (SUITE_SECONDS[s] - LAUNCH_SECONDS) for s in suites)
    return (kept_rounds + 1) * 2 * per_suite


def archive_dir(base_sha, head_sha, timestamp):
    return os.path.join(cache_root(), f"{base_sha[:11]}..{head_sha[:11]}-{timestamp}")
