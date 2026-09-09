#!/usr/bin/env python3
"""Measure a Ladybird branch against its merge-base and emit the PR performance section.

Run it from the branch's checkout; both arms are compiled from that repository into worktrees of their own, and the two
are interleaved suite by suite — so the comparison survives, whatever else the machine is doing.

    /path/to/web-benchmarks/bench_pr.py                    # measure the current branch
    /path/to/web-benchmarks/bench_pr.py --dry-run          # the plan and the ETA, run nothing
    /path/to/web-benchmarks/bench_pr.py --calibrate        # A-vs-A: this machine's resolution
    /path/to/web-benchmarks/bench_pr.py --focus WebKitSVG  # the tests the change targets

MEASURING-A-BRANCH.md walks through a first run and how to read what comes out.
"""
import argparse
import datetime
import glob
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Bumped whenever the compile recipe changes, so trees made the old way are redone.
BUILD_STAMP = "lto-on"

# The analysis needs scipy, which requirements.txt installs; re-exec under the virtualenv beside this script when the
# interpreter that started us lacks it.
if importlib.util.find_spec("scipy") is None:
    venv_python = next((p for p in (os.path.join(HERE, ".venv/bin/python"),
                                    os.path.join(HERE, ".venv/Scripts/python.exe"))
                        if os.path.exists(p)), None)
    if os.environ.get("BENCH_PR_REEXEC") or not venv_python:
        sys.exit("scipy is missing. Install the requirements (pip install -r "
                 f"{os.path.join(HERE, 'requirements.txt')}), either in a .venv beside this "
                 "script or in the interpreter you run it with.")
    os.execve(venv_python, [venv_python] + sys.argv, dict(os.environ, BENCH_PR_REEXEC="1"))

sys.path.insert(0, HERE)
import bench_compare
import bench_plan

PLUS_MINUS = bench_compare.PLUS_MINUS

# Progress lines must reach a redirected log as they happen, not at exit.
sys.stdout.reconfigure(line_buffering=True)


def sh(cmd, cwd=None, check=True, capture=True):
    return subprocess.run(cmd, cwd=cwd, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def git(args, cwd, check=True):
    proc = sh(["git"] + args, cwd=cwd, check=check)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def resolve_revisions(worktree, calibrate):
    # Untracked files never reach a push, so notes and scratch files beside the code don't count as a dirty tree.
    if git(["status", "--porcelain", "--untracked-files=no"], worktree):
        sys.exit("Refusing to run: the worktree has uncommitted changes, so the measured head "
                 "is not what you would push.")
    head = git(["rev-parse", "HEAD"], worktree)
    if calibrate:
        return head, head  # A-vs-A: the same build in both arms
    print("Fetching origin master ...")
    sh(["git", "fetch", "origin", "master"], cwd=worktree)
    base = git(["merge-base", "HEAD", "origin/master"], worktree)
    if base == head:
        sys.exit("Refusing to run: HEAD is the merge-base, so there is nothing to measure.")
    return base, head


def executable_in(tree):
    if platform.system() == "Darwin":
        return os.path.join(tree, "Build/distribution/bin/Ladybird.app/Contents/MacOS/Ladybird")
    return os.path.join(tree, "Build/distribution/bin/Ladybird")


def seed_caches(source_repo, tree):
    """Copy the source tree's Build/caches (ccache and the vcpkg binary cache) into a fresh worktree, so its first build
    restores rather than compiles. -c clones on APFS; GNU cp spells that --reflink=auto, and copies the bytes where it
    can't."""
    caches = os.path.join(source_repo, "Build/caches")
    if not os.path.isdir(caches):
        return
    clone = ["-Rc"] if platform.system() == "Darwin" else ["-R", "--reflink=auto"]
    if sh(["cp", *clone, caches, os.path.join(tree, "Build/caches")], check=False).returncode != 0:
        print("  couldn't seed Build/caches from the source tree; the first build compiles everything")


def ensure_worktree(slot, sha, source_repo, worktree_root):
    """A persistent detached worktree per arm, so ccache stays warm across branches."""
    os.makedirs(worktree_root, exist_ok=True)
    tree = os.path.join(worktree_root, f"ladybird-bench-{slot}")
    if not os.path.isdir(tree):
        print(f"Creating {tree} ...")
        sh(["git", "worktree", "add", "--detach", tree, sha], cwd=source_repo)
        os.makedirs(os.path.join(tree, "Build"), exist_ok=True)
        seed_caches(source_repo, tree)
        sh(["git", "clone", "--reference-if-able", os.path.join(source_repo, "Build/vcpkg"),
            "--dissociate", "https://github.com/microsoft/vcpkg.git",
            os.path.join(tree, "Build/vcpkg")], check=False)
    elif git(["rev-parse", "HEAD"], tree) != sha:
        sh(["git", "checkout", "--detach", sha], cwd=tree)

    stamp = os.path.join(tree, ".bench-built-sha")
    built = open(stamp).read().strip() if os.path.exists(stamp) else None
    if built == f"{sha} {BUILD_STAMP}" and os.path.exists(executable_in(tree)):
        print(f"  {slot}: {sha[:11]} already built")
        return tree

    log = os.path.join(bench_plan.cache_root(), f"compile-{slot}.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    print(f"  {slot}: building {sha[:11]} (watch: tail -f {log})")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env["BUILD_PRESET"] = "Distribution"
    # The presets append $VCPKG_BINARY_SOURCES after the tree's own cache. This machine's Distribution packages sit in
    # vcpkg's default archive — so add it, plus the source tree's cache read-only: a worktree then restores instead of
    # rebuilding all 72 ports.
    env["VCPKG_BINARY_SOURCES"] = (
        f"files,{vcpkg_archives()},readwrite;"
        f"files,{os.path.join(source_repo, 'Build/caches/vcpkg-binary-cache')},read")
    # What Meta/ladybird.py exports before it configures; the presets find the vcpkg toolchain through VCPKG_ROOT.
    env["VCPKG_ROOT"] = os.path.join(tree, "Build/vcpkg")
    env["PATH"] = env.get("PATH", "") + os.pathsep + env["VCPKG_ROOT"]
    with open(log, "w") as lf:
        # A Ladybird tree that tests ENABLE_LTO_FOR_RELEASE before defining the option skips LTO on a first configure,
        # while a re-configured tree has it. Define it on the command line, ahead of any CMakeLists, and configure every
        # time: both arms then get the same compile line however old the commit is, and whatever the tree did before.
        steps = ([sys.executable, "Meta/ladybird.py", "vcpkg"],
                 ["cmake", "--preset", "Distribution", "-S", tree, "-B",
                  os.path.join(tree, "Build/distribution"), "-DENABLE_LTO_FOR_RELEASE=ON"],
                 [sys.executable, "Meta/ladybird.py", "build", "ladybird"])
        for step in steps:
            rc = subprocess.run(step, cwd=tree, env=env, stdout=lf, stderr=subprocess.STDOUT).returncode
            if rc != 0:
                sys.exit(f"Build failed for {slot} at {sha[:11]}; see {log}")
    open(stamp, "w").write(f"{sha} {BUILD_STAMP}")
    return tree


def compile_flags_in(tree):
    """The compile line of one reference object in the tree, from the generated build rules: what the compiler was
    actually invoked with, LTO included."""
    rules = os.path.join(tree, "Build/distribution/build.ninja")
    flags = ""
    if os.path.exists(rules):
        text = open(rules).read()
        start = text.find("DOM/Document.cpp.o:")
        match = re.search(r"^\s*FLAGS = (.*)$", text[start:], re.M) if start >= 0 else None
        flags = match.group(1).strip() if match else ""
    # The rules say what the next build will do; the object says what the last one did. An LTO object is LLVM bitcode, a
    # plain one is Mach-O or ELF.
    objects = glob.glob(os.path.join(tree, "Build/distribution/Libraries/LibWeb/**/DOM/Document.cpp.o"),
                        recursive=True)
    kind = "missing"
    if objects:
        with open(objects[0], "rb") as f:
            magic = f.read(4)
        kind = "bitcode" if magic in (b"\xde\xc0\x17\x0b", b"BC\xc0\xde") else "native"
    return f"{flags} [object:{kind}]"


def compiler_in(tree):
    """The compiler CMake configured the tree with, from its own record."""
    for path in glob.glob(os.path.join(tree, "Build/distribution/CMakeFiles/*/CMakeCXXCompiler.cmake")):
        text = open(path).read()
        ident = re.search(r'CMAKE_CXX_COMPILER_ID "([^"]+)"', text)
        version = re.search(r'CMAKE_CXX_COMPILER_VERSION "([^"]+)"', text)
        if ident and version:
            return f"{ident.group(1)} {version.group(1)}"
    return "unknown compiler"


def run_suite(executable, suite, iterations, out_path):
    """One run.py invocation for one suite. Retries a startup stall, which run.py's hardcoded 10-second
    STARTUP_TIMEOUT_SECONDS makes possible on a briefly busy machine."""
    cmd = [sys.executable, os.path.join(HERE, "run.py"),
           "--executable", executable, "--benchmarks", suite, "--iterations", str(iterations),
           "--timeout", str(bench_plan.PER_TEST_TIMEOUT_SECONDS), "-o", out_path]
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    for attempt in range(3):
        proc = subprocess.run(cmd, cwd=HERE, text=True, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode == 0:
            return True
        if "did not start running tests" in proc.stdout and attempt < 2:
            print(f"      startup stall, retrying ({attempt + 1}/2)")
            time.sleep(5)
            continue
        sys.stderr.write(proc.stdout[-2000:])
        return False
    return False


def vcpkg_archives():
    """vcpkg's own default archive directory, where a Ladybird tree's dependencies already sit; adding it to
    VCPKG_BINARY_SOURCES lets a fresh worktree restore them, instead of compiling all 70-odd ports again."""
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "vcpkg", "archives")
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "vcpkg", "archives")


def thermal_state():
    """NSProcessInfo's thermal state (0 nominal .. 3 critical), read through JXA since pmset -g therm reports nothing on
    Apple silicon. Elsewhere there's no portable equivalent, so the run goes ahead and says nothing about heat."""
    if platform.system() != "Darwin":
        return 0
    out = sh(["osascript", "-l", "JavaScript", "-e",
              "ObjC.import('Foundation'); $.NSProcessInfo.processInfo.thermalState"], check=False).stdout
    return int(out.strip()) if out.strip().isdigit() else 0


def on_ac_power():
    """True, False, or None where the power source can't be read."""
    if platform.system() == "Darwin":
        out = sh(["pmset", "-g", "batt"], check=False).stdout
        return "AC Power" in out if "Power" in out else None
    states = glob.glob("/sys/class/power_supply/*/online")
    if states:
        return any(open(path).read().strip() == "1" for path in states)
    return None


def machine_state():
    load1 = os.getloadavg()[0]
    ncpu = os.cpu_count() or 1
    pattern = ("Ladybird.app/Contents/MacOS/Ladybird" if platform.system() == "Darwin"
               else "bin/Ladybird")
    running = bool(sh(["pgrep", "-f", pattern], check=False).stdout.strip())
    return on_ac_power(), load1, ncpu, running, thermal_state()


def machine_description(ncpu):
    if platform.system() == "Darwin":
        model = sh(["sysctl", "-n", "hw.model"], check=False).stdout.strip() or platform.machine()
        return f"{model}, {ncpu} cores, macOS {platform.mac_ver()[0]}"
    return f"{platform.machine()}, {ncpu} cores, {platform.system()} {platform.release()}"


def run_pair(rnd, suite, order, arms, iterations, archive, label):
    """Both arms of one suite, in the schedule's order for that suite. A failed arm retries the pair once — so a single
    stall doesn't throw away the round."""
    for attempt in (1, 2):
        outs = {}
        for arm in order:
            out = os.path.join(archive, f"r{rnd.index}-{arm}-{suite}.json")
            if not run_suite(arms[arm], suite, iterations, out):
                print(f"      {arm} arm failed on {suite} in {label}" +
                      ("; redoing the pair" if attempt == 1 else ""))
                break
            outs[arm] = out
        else:
            return outs
    sys.exit(f"Aborting: {suite} failed twice in {label}. A partial arm is not comparable.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=bench_plan.DEFAULT_KEPT_ROUNDS)
    ap.add_argument("--iterations", type=int, default=1,
                    help="benchmark iterations per browser launch; averages in-process noise")
    ap.add_argument("--benchmarks", default=",".join(bench_plan.default_suites()))
    ap.add_argument("--focus", nargs="*", default=[],
                    help="suites or benchmark/test keys the change targets; judged as their own family")
    ap.add_argument("--calibrate", action="store_true", help="A-vs-A run to measure this machine's resolution")
    ap.add_argument("--ladybird", default=os.getcwd(), metavar="DIR",
                    help="the Ladybird checkout to measure (default: the current directory)")
    ap.add_argument("--worktree-root", default=os.path.join(bench_plan.cache_root(), "worktrees"),
                    metavar="DIR", help="where the two arms' worktrees live")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even if preflight objects")
    ap.add_argument("-o", "--output", default="pr-perf-section.md")
    args = ap.parse_args()
    if args.rounds < 2:
        ap.error("--rounds must be at least 2; one round can't tell a change from noise")

    worktree = os.path.abspath(args.ladybird)
    if not os.path.exists(os.path.join(worktree, "Meta/ladybird.py")):
        sys.exit(f"{worktree} is not a Ladybird checkout (no Meta/ladybird.py). Run this from the "
                 "branch you want to measure, or pass --ladybird.")
    source_repo = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], worktree)
    source_repo = os.path.dirname(source_repo) if source_repo.endswith(".git") else worktree
    suites = args.benchmarks.split(",")

    base_sha, head_sha = resolve_revisions(worktree, args.calibrate)
    print(f"baseline (merge-base): {base_sha[:11]}" if not args.calibrate else f"A-vs-A of {head_sha[:11]}")
    if not args.calibrate:
        print(f"branch head:           {head_sha[:11]}")

    plan = bench_plan.round_plan(args.rounds)
    eta = bench_plan.estimate_seconds(suites, args.rounds, args.iterations)
    print(f"suites: {', '.join(suites)}" + (f"   focus: {', '.join(args.focus)}" if args.focus else ""))
    print(f"plan: {len(plan)} rounds ({args.rounds} kept + 1 warmup), 2 arms interleaved per suite, "
          f"{args.iterations} iteration(s) per launch, ETA about {eta / 60:.0f} min")
    if args.dry_run:
        return

    on_ac, load1, ncpu, running, thermal = machine_state()
    machine = machine_description(ncpu)
    benchmarks_sha = git(["rev-parse", "--short", "HEAD"], HERE, check=False) or "unknown"
    problems = bench_plan.preflight(on_ac, load1, ncpu, running, thermal)
    floor_path = os.path.join(bench_plan.cache_root(), "noise-floor.json")
    os.makedirs(bench_plan.cache_root(), exist_ok=True)
    floor = json.load(open(floor_path)) if os.path.exists(floor_path) else None
    if not args.calibrate:
        problems += bench_plan.noise_floor_problems(floor, datetime.datetime.now(), machine, benchmarks_sha)
    for p in problems:
        print(("  BLOCKING: " if p.blocking else "  warning:  ") + p.message)
    if any(p.blocking for p in problems) and not args.force:
        sys.exit("Preflight failed. Fix the above, or pass --force.")

    if platform.system() == "Darwin":
        # Hold off idle sleep for as long as this process lives; the run is long enough to hit the sleep timer on a
        # machine that's otherwise untouched.
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])

    print("Preparing builds ...")
    root = os.path.abspath(args.worktree_root)
    base_tree = ensure_worktree("base", base_sha, source_repo, root)
    head_tree = base_tree if args.calibrate else ensure_worktree("head", head_sha, source_repo, root)
    arms = {"base": executable_in(base_tree), "head": executable_in(head_tree)}
    flags = {"base": compile_flags_in(base_tree), "head": compile_flags_in(head_tree)}
    build = f"Distribution preset, {compiler_in(base_tree)}, {bench_plan.lto_state(flags['base'])}"
    for p in bench_plan.build_parity_problems(flags):
        print("  BLOCKING: " + p.message)
        sys.exit("The two arms are not comparable; delete the offending worktree's Build "
                 "directory and run this again.")
    if not args.calibrate:
        for p in bench_plan.noise_floor_problems(floor, datetime.datetime.now(), machine, benchmarks_sha, build):
            if "different build" in p.message:
                print("  warning:  " + p.message)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = bench_plan.archive_dir(base_sha, head_sha, stamp)
    os.makedirs(archive, exist_ok=True)

    collected = {"base": [], "head": []}
    for rnd in plan:
        label = "warmup" if rnd.is_warmup else f"round {rnd.index}/{args.rounds}"
        print(f"  {label}: {rnd.order[0]} then {rnd.order[1]}, alternating per suite "
              f"(thermal state {thermal_state()})")
        orders = {}
        for suite, arm in bench_plan.schedule(rnd, suites):
            orders.setdefault(suite, []).append(arm)
        merged = {"base": {}, "head": {}}
        for suite in suites:
            outs = run_pair(rnd, suite, orders[suite], arms, args.iterations, archive, label)
            for arm, out in outs.items():
                with open(out) as f:
                    merged[arm].update(json.load(f))
        for arm in merged:
            # The whole round per arm, the shape bench_compare's CLI takes for a re-analysis.
            with open(os.path.join(archive, f"r{rnd.index}-{arm}.json"), "w") as f:
                json.dump(merged[arm], f, indent=4)
            if not rnd.is_warmup:
                collected[arm].append(merged[arm])

    analysis = bench_compare.analyze(collected["base"], collected["head"], focus=args.focus)
    provenance = {
        "baseline": base_sha[:11], "branch": head_sha[:11], "benchmarks": benchmarks_sha,
        "build": build,
        "machine": machine,
        "suites": ", ".join(suites) + (f"; {args.iterations} iterations per launch" if args.iterations > 1 else ""),
    }
    if floor and not args.calibrate:
        provenance["calibration"] = (f"A-vs-A on {floor['when'][:8]}: {floor['false_movers']} false mover(s), "
                                     f"resolution {PLUS_MINUS}{floor['p90_pct']:.1f}% p90")

    if args.calibrate:
        print(f"\nA-vs-A calibration: resolution {analysis.resolution_median_pct:.2f}% median, "
              f"{analysis.resolution_p90_pct:.2f}% p90 ({analysis.quantized_count} sub-2ms tests left out)")
        print(f"false movers (should be 0): {len(analysis.movers)}")
        if analysis.movers:
            print("  " + ", ".join(f"{m.test} {m.effect_pct:+.1f}%" for m in analysis.movers))
            print("  Non-zero here means this machine is too noisy to trust at these settings.")
        if bench_plan.records_floor(suites):
            json.dump({"median_pct": analysis.resolution_median_pct, "p90_pct": analysis.resolution_p90_pct,
                       "rounds": args.rounds, "iterations": args.iterations, "suites": suites,
                       "false_movers": len(analysis.movers), "machine": machine, "build": build,
                       "benchmarks": benchmarks_sha, "when": stamp}, open(floor_path, "w"), indent=2)
            print(f"written to {floor_path}")
        else:
            print(f"partial suite set, so not recorded as this machine's calibration (raw results: {archive})")
        return

    with open(os.path.join(archive, "provenance.json"), "w") as f:
        json.dump(provenance, f, indent=2)
    markdown = bench_compare.render_markdown(analysis, provenance)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(markdown)
    print("\n" + markdown)
    print(f"written to {os.path.abspath(args.output)}   (raw results: {archive})")


if __name__ == "__main__":
    main()
