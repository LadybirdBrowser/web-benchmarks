#!/usr/bin/env python3
"""Function-order randomization for the two arms of an A/B run.

Where the linker puts each function decides which functions share a cache line, an i-cache set or a branch-predictor
entry — and in a ThinLTO build, a change anywhere moves every function placed after it. So a branch can make a test it
never touches several percent faster or slower, and one binary per arm is a single draw of that: Every round measures
the same draw again, so the rounds agree with each other, and the paired analysis reports a confident mover.

So each kept round relinks both arms with a function order of its own: the same code, sorted by a seeded hash, and
handed to the linker as an order file (-order_file on macOS, lld's --symbol-ordering-file on Linux). A layout effect
then changes from round to round like any other noise, and the analysis sees it as spread; a real change holds under
every order.

Pure decision logic lives here, so it can be tested without a build; bench_pr.py runs nm and the link commands.
"""
import hashlib
import re
import shlex

# nm -P type letters for code: T and t are global and local text everywhere, and W and w are ELF's weak definitions —
# which is where inline functions and template instantiations land.
TEXT_TYPES = frozenset("TtWw")

# How long an unused ThinLTO cache entry is kept: long enough that the next run against the same merge-base still finds
# the base arm's codegen there.
CACHE_PRUNE_AFTER_SECONDS = 14 * 24 * 3600


def text_symbols(nm_output):
    """The code symbols in `nm -P --defined-only` output, spelled the way the linker spells them (Mach-O's leading
    underscore included) — which is what an order file has to say. AArch64 ELF's $x/$d mapping symbols mark where code
    and data start inside a section; they aren't functions, and every section has one."""
    symbols = set()
    for line in nm_output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in TEXT_TYPES and not fields[0].startswith("$"):
            symbols.add(fields[0])
    return symbols


def order_for_seed(symbols, seed):
    """Every symbol, in an order drawn from the seed. It's a sort by a keyed hash rather than a shuffle, so a name's
    place depends on nothing but the seed and the name itself — not on nm's output order, and not on which other names
    the arm happens to define."""
    key = seed.to_bytes(8, "little")
    return sorted(symbols, key=lambda name: hashlib.blake2b(name.encode(), digest_size=8, key=key).digest())


def round_seed(run_seed, arm, round_index):
    """The seed of one arm's function order in one round: distinct per arm and per round, so no two binaries in a run
    share an order — and reproducible from the run's seed alone."""
    digest = hashlib.blake2b(f"{run_seed}:{arm}:{round_index}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little")


def linker_flags(system, cache_dir, order_file=None):
    """What a relink adds to the compiler driver's command line. The ThinLTO cache is what makes a relink cheap: An
    order file changes where the linker places code, not what codegen makes of it — so after an arm's first relink,
    every module is a cache hit, and even WebContent relinks in about 3s rather than 45s."""
    if system == "Darwin":
        flags = [f"-Wl,-cache_path_lto,{cache_dir}", f"-Wl,-prune_after_lto,{CACHE_PRUNE_AFTER_SECONDS}"]
        if order_file:
            flags.append(f"-Wl,-order_file,{order_file}")
        return flags
    flags = [f"-Wl,--thinlto-cache-dir={cache_dir}",
             f"-Wl,--thinlto-cache-policy=prune_after={CACHE_PRUNE_AFTER_SECONDS}s"]
    if order_file:
        # One order file serves every executable, so most of its names are missing from any one of them.
        flags += [f"-Wl,--symbol-ordering-file={order_file}", "-Wl,--no-warn-symbol-ordering"]
    return flags


def unsupported_linker(system, link_command):
    """Why a tree's links can't take an order file, or None when they can. macOS links with Apple's ld, which takes
    -order_file. On Linux, Ladybird links with lld when it can find it (Meta/CMake/use_linker.cmake), and with mold or
    the compiler's default linker otherwise — which spell the flags differently, or have no ThinLTO cache to make a
    relink cheap."""
    if system == "Darwin":
        return None
    if "-fuse-ld=lld" in shlex.split(link_command):
        return None
    match = re.search(r"-fuse-ld=(\S+)", link_command)
    found = match.group(1) if match else "the compiler's default linker"
    return (f"this tree links with {found}, and a fresh function order per round needs lld; install lld and "
            "reconfigure, or pass --fixed-layout")


def with_flags(link_command, output, flags):
    """The link command with the flags added just before its -o — so they reach the link itself, and not the codesign
    or anything else CMake chains after it."""
    pattern = re.compile(r"(?<=\s)-o " + re.escape(output) + r"(?=\s|$)")
    matches = pattern.findall(link_command)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one '-o {output}' in the link command, found {len(matches)}")
    extra = " ".join(shlex.quote(flag) for flag in flags)
    return pattern.sub(lambda m: f"{extra} {m.group(0)}", link_command, count=1)
