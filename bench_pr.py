#!/usr/bin/env python3
"""Measure a Ladybird branch against its merge-base and emit the PR performance section.

Run it from the branch's checkout; both arms are compiled from that repository into worktrees of their own, and the two
are interleaved suite by suite — so the comparison survives, whatever else the machine is doing.

    /path/to/web-benchmarks/bench_pr.py                    # measure the current branch
    /path/to/web-benchmarks/bench_pr.py --dry-run          # the plan and the ETA, run nothing
    /path/to/web-benchmarks/bench_pr.py --calibrate        # A-vs-A: this machine's resolution
    /path/to/web-benchmarks/bench_pr.py --focus WebKitSVG  # the tests the change targets
    /path/to/web-benchmarks/bench_pr.py --fixed-layout     # one function order per arm, as the build made it

MEASURING-A-BRANCH.md walks through a first run and how to read what comes out.
"""
import argparse
import datetime
import glob
import importlib.util
import json
import os
import platform
import random
import re
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows has no flock; a run there goes without the lock.
    fcntl = None

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
import layout

PLUS_MINUS = bench_compare.PLUS_MINUS

# Progress lines must reach a redirected log as they happen, not at exit.
sys.stdout.reconfigure(line_buffering=True)


def hold_run_lock(root):
    """One run at a time per cache directory: Two runs would build and measure the same worktrees under each other —
    and each would report numbers from binaries the other swapped out. The lock lasts as long as the process, however
    it exits. Returns the open lock file, or None and whatever the holder wrote into it."""
    os.makedirs(root, exist_ok=True)
    handle = open(os.path.join(root, "bench_pr.lock"), "a+")
    if fcntl is None:
        return handle, None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        holder = handle.read().strip() or "no details recorded"
        handle.close()
        return None, holder
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid {os.getpid()} on {platform.node()}, started {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    handle.flush()
    return handle, None


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


def build_dir_of(tree):
    return os.path.join(tree, "Build/distribution")


def ninja_program(build_dir):
    """The ninja CMake configured the tree with — the one Meta/ladybird.py builds with, which needn't be on PATH."""
    cache = os.path.join(build_dir, "CMakeCache.txt")
    text = open(cache).read() if os.path.exists(cache) else ""
    match = re.search(r"^CMAKE_MAKE_PROGRAM:[A-Z]+=(.+)$", text, re.M)
    return match.group(1).strip() if match else "ninja"


def runnable_executables(build_dir, system=None):
    """The executables a benchmark run can start, relative to the build directory: every binary in the app bundle on
    macOS, and the browser and its libexec helpers elsewhere. The browser itself comes last — on macOS its link command
    re-signs the whole bundle, which has to happen after every helper inside it has been relinked."""
    darwin = (system or platform.system()) == "Darwin"
    folder = "bin/Ladybird.app/Contents/MacOS" if darwin else "libexec"
    browser = "bin/Ladybird.app/Contents/MacOS/Ladybird" if darwin else "bin/Ladybird"
    path = os.path.join(build_dir, folder)
    names = sorted(os.listdir(path)) if os.path.isdir(path) else []
    helpers = [f"{folder}/{name}" for name in names if os.path.isfile(os.path.join(path, name))]
    return [rel for rel in helpers if rel != browser] + [browser]


class ArmLayout:
    """One arm's executables and the commands that linked them — so the arm can be relinked with any function order,
    in seconds once the ThinLTO cache holds its codegen. The commands come from the tree's own build rules, the
    codesign-with-entitlements steps chained after them included."""

    STAMP = ".bench-function-order"

    def __init__(self, arm, tree):
        self.arm = arm
        self.tree = tree
        self.build_dir = build_dir_of(tree)
        self.log = os.path.join(bench_plan.cache_root(), f"relink-{arm}.log")
        self.order_file = os.path.join(bench_plan.cache_root(), f"function-order-{arm}.txt")
        self.cache_dir = os.path.join(bench_plan.cache_root(), "thinlto-cache")
        builder = ninja_program(self.build_dir)
        self.links = {}
        for output in runnable_executables(self.build_dir):
            chain = subprocess.run([builder, "-C", self.build_dir, "-t", "commands", output], text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip().splitlines()
            # The last command in the chain is the one that makes the output. Anything else there (a script, a copy)
            # isn't a link, and keeps the order it has.
            if chain and f" -o {output}" in chain[-1]:
                self.links[output] = chain[-1]
        self.symbols = set()
        for output in self.links:
            nm = subprocess.run(["nm", "-P", "--defined-only", os.path.join(self.build_dir, output)], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
            self.symbols |= layout.text_symbols(nm)

    def unsupported(self):
        if not self.links:
            return f"found no link commands for the executables in {self.build_dir}"
        return layout.unsupported_linker(platform.system(), next(reversed(self.links.values())))

    def has_drawn_order(self):
        return os.path.exists(os.path.join(self.tree, self.STAMP))

    def relink(self, seed):
        """Relink every executable with the function order drawn from seed — or, with None, in the order the build
        produced. Returns the wall seconds it took."""
        order_file = None
        if seed is not None:
            with open(self.order_file, "w") as f:
                f.write("\n".join(layout.order_for_seed(self.symbols, seed)) + "\n")
            order_file = self.order_file
        flags = layout.linker_flags(platform.system(), self.cache_dir, order_file)
        start = time.monotonic()
        with open(self.log, "a") as lf:
            which = f"order {seed}" if seed is not None else "default order"
            lf.write(f"=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} {self.arm}: {which}\n")
            lf.flush()
            for output, command in self.links.items():
                rc = subprocess.run(["sh", "-c", layout.with_flags(command, output, flags)], cwd=self.build_dir,
                                    stdout=lf, stderr=subprocess.STDOUT).returncode
                if rc != 0:
                    sys.exit(f"Relinking {output} for the {self.arm} arm failed; see {self.log}")
        stamp = os.path.join(self.tree, self.STAMP)
        if seed is None:
            if os.path.exists(stamp):
                os.remove(stamp)
        else:
            open(stamp, "w").write(str(seed))
        return time.monotonic() - start


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
    ap.add_argument("--fixed-layout", action="store_true",
                    help="measure each arm in the one function order its build produced, not a fresh one per round")
    ap.add_argument("--layout-seed", type=int, metavar="N",
                    help="the seed each round's function orders are drawn from (default: a new one every run)")
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
    if args.calibrate:
        print(f"A-vs-A of {head_sha[:11]}" +
              ("" if args.fixed_layout else ": two builds, a fresh function order per round"))
    else:
        print(f"baseline (merge-base): {base_sha[:11]}")
        print(f"branch head:           {head_sha[:11]}")

    plan = bench_plan.round_plan(args.rounds)
    eta = bench_plan.estimate_seconds(suites, args.rounds, args.iterations, relink=not args.fixed_layout)
    print(f"suites: {', '.join(suites)}" + (f"   focus: {', '.join(args.focus)}" if args.focus else ""))
    print(f"plan: {len(plan)} rounds ({args.rounds} kept + 1 warmup), 2 arms interleaved per suite, "
          f"{args.iterations} iteration(s) per launch" +
          ("" if args.fixed_layout else ", a fresh function order per kept round") +
          f", ETA about {eta / 60:.0f} min")
    if args.dry_run:
        return

    lock, holder = hold_run_lock(bench_plan.cache_root())
    if lock is None:
        sys.exit(f"Refusing to run: another bench_pr.py run holds {bench_plan.cache_root()} ({holder}); its builds "
                 "and measurements would land under this one's. Wait for it to finish.")

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
    # Every round relinks the two arms in different orders — so with drawn orders, even an A-vs-A run needs the two
    # arms in two trees.
    head_tree = (base_tree if args.calibrate and args.fixed_layout
                 else ensure_worktree("head", head_sha, source_repo, root))
    arms = {"base": executable_in(base_tree), "head": executable_in(head_tree)}
    flags = {"base": compile_flags_in(base_tree), "head": compile_flags_in(head_tree)}
    build = (f"Distribution preset, {compiler_in(base_tree)}, {bench_plan.lto_state(flags['base'])}" +
             ("" if args.fixed_layout else ", a fresh function order per round"))
    for p in bench_plan.build_parity_problems(flags):
        print("  BLOCKING: " + p.message)
        sys.exit("The two arms are not comparable; delete the offending worktree's Build "
                 "directory and run this again.")
    if not args.calibrate:
        for p in bench_plan.noise_floor_problems(floor, datetime.datetime.now(), machine, benchmarks_sha, build):
            if "different build" in p.message:
                print("  warning:  " + p.message)

    arm_layouts, run_seed = {}, None
    if args.fixed_layout:
        # A run that stopped part way leaves its last drawn order in the tree, so put the build's own order back. An
        # A-vs-A run here has one tree for both arms, and relinks it once.
        for tree, arm in {head_tree: "head", base_tree: "base"}.items():
            if os.path.exists(os.path.join(tree, ArmLayout.STAMP)):
                ArmLayout(arm, tree).relink(None)
    else:
        run_seed = args.layout_seed if args.layout_seed is not None else random.SystemRandom().randrange(1, 2 ** 31)
        print(f"Preparing function orders (seed {run_seed}) ...")
        for arm, tree in (("base", base_tree), ("head", head_tree)):
            arm_layouts[arm] = ArmLayout(arm, tree)
            problem = arm_layouts[arm].unsupported()
            if problem:
                sys.exit(f"Can't draw function orders for the {arm} arm: {problem}.")
            # The first relink fills the ThinLTO cache, and puts the build's own order back after an interrupted run.
            elapsed = arm_layouts[arm].relink(None)
            print(f"  {arm}: {len(arm_layouts[arm].links)} executables, {len(arm_layouts[arm].symbols)} functions, "
                  f"relinked in {elapsed:.0f}s (watch: tail -f {arm_layouts[arm].log})")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = bench_plan.archive_dir(base_sha, head_sha, stamp)
    os.makedirs(archive, exist_ok=True)

    collected = {"base": [], "head": []}
    round_seeds = {}
    for rnd in plan:
        label = "warmup" if rnd.is_warmup else f"round {rnd.index}/{args.rounds}"
        relinked = ""
        if arm_layouts and not rnd.is_warmup:
            round_seeds[rnd.index] = {arm: layout.round_seed(run_seed, arm, rnd.index) for arm in arm_layouts}
            elapsed = sum(arm_layouts[arm].relink(seed) for arm, seed in round_seeds[rnd.index].items())
            # The relinks leave a gigabyte or so of freshly written executables for the kernel to write back — which
            # Linux would start about 30s later, in the middle of the round (and in a VM, as host disk I/O). So flush it
            # before measuring.
            start = time.monotonic()
            os.sync()
            relinked = (f", fresh function orders relinked in {elapsed:.0f}s and flushed to disk in "
                        f"{time.monotonic() - start:.0f}s")
        print(f"  {label}: {rnd.order[0]} then {rnd.order[1]}, alternating per suite "
              f"(thermal state {thermal_state()}{relinked})")
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

    for arm_layout in arm_layouts.values():
        arm_layout.relink(None)
    if arm_layouts:
        with open(os.path.join(archive, "function-orders.json"), "w") as f:
            json.dump({"seed": run_seed, "rounds": round_seeds}, f, indent=2)

    analysis = bench_compare.analyze(collected["base"], collected["head"], focus=args.focus)
    provenance = {
        "baseline": base_sha[:11], "branch": head_sha[:11], "benchmarks": benchmarks_sha,
        "build": build,
        "machine": machine,
        "suites": ", ".join(suites) + (f"; {args.iterations} iterations per launch" if args.iterations > 1 else ""),
    }
    if run_seed is not None:
        provenance["layout_seed"] = run_seed
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
