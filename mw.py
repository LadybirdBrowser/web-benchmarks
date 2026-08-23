#!/usr/bin/env python3
"""Run one MicroWeb test in both Ladybird and Chromium and print both results + ratio.

    ./mw.py dom/create-element
    ./mw.py create-element                # fuzzy: unique substring is enough
    ./mw.py layout-thrash fill-style-set  # several tests in one go

Each test runs in a fresh browser per engine (no session-aging tax). Chromium runs
jitless by default for an engine-vs-engine comparison; pass --jit to enable the JIT.
"""

import argparse
import http.server
import json
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlencode

SUITE_DIR = Path(__file__).parent / "benchmarks" / "MicroWeb"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.server.result = json.loads(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.server.done.set()

    def log_message(self, *args):
        pass


def resolve_test(name):
    """Accept 'dom/create-element', 'create-element.html', or any unique substring."""
    all_tests = sorted(
        str(path.relative_to(SUITE_DIR))
        for path in SUITE_DIR.glob("*/*.html")
        if path.parent.name != "resources")
    candidate = name if name.endswith(".html") else name + ".html"
    if candidate in all_tests:
        return candidate
    matches = [test for test in all_tests if name in test]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        sys.exit(f"No test matches '{name}'. Tests live in {SUITE_DIR}/<category>/.")
    sys.exit(f"'{name}' is ambiguous:\n  " + "\n  ".join(matches))


def launch_command(browser, url, profile, ladybird_executable, chromium_executable, jit):
    if browser == "ladybird":
        return [ladybird_executable, "--headless=manual", "--profile-path", profile, url]
    command = [chromium_executable, "--no-first-run", "--no-default-browser-check",
               "--disable-background-networking", f"--user-data-dir={profile}",
               "--headless=new", "--window-size=1200,900", url]
    if not jit:
        command.insert(1, "--js-flags=--jitless")
    return command


def profile_directory(browser):
    if browser == "chromium":
        snap_common = Path.home() / "snap" / "chromium" / "common"
        if snap_common.is_dir():
            return tempfile.mkdtemp(prefix="mw-", dir=snap_common)
    return tempfile.mkdtemp(prefix="mw-")


def run_one(browser, test, iterations, timeout, ladybird_executable, chromium_executable, jit):
    os.chdir(SUITE_DIR)
    server = http.server.HTTPServer(("localhost", 0), Handler)
    server.result = None
    server.done = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _, port = server.server_address
    url = f"http://localhost:{port}/single.html?" + urlencode(
        {"test": test, "iterationCount": iterations, "post": "1"})

    profile = profile_directory(browser)
    command = launch_command(browser, url, profile, ladybird_executable, chromium_executable, jit)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finished = server.done.wait(timeout=timeout)
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    server.shutdown()

    if not finished:
        return {"error": f"no result within {timeout:g}s"}
    return server.result


def describe(result):
    if result is None or "error" in (result or {}):
        return None, f"ERROR: {(result or {}).get('error', 'no result')}"
    values = result["values"]
    median = statistics.median(values)
    runs = ", ".join(f"{value:.2f}" for value in values)
    return median, f"median {median:8.2f} ms   [{runs}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tests", nargs="+", help="Test path or unique substring, e.g. dom/create-element")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--jit", action="store_true", help="Run Chromium with its JIT enabled")
    parser.add_argument("--ladybird-executable",
                        default=os.path.join(os.environ.get("LADYBIRD_SOURCE_DIR", os.path.expanduser("~/src/ladybird")),
                                             "Build", "release", "bin", "Ladybird"))
    parser.add_argument("--chromium-executable", default="/snap/bin/chromium")
    args = parser.parse_args()

    for name in args.tests:
        test = resolve_test(name)
        print(f"{test}  (iterations: {args.iterations}, chromium {'jit' if args.jit else 'jitless'})")
        medians = {}
        for browser in ("ladybird", "chromium"):
            result = run_one(browser, test, args.iterations, args.timeout,
                             args.ladybird_executable, args.chromium_executable, args.jit)
            medians[browser], text = describe(result)
            print(f"  {browser:9s} {text}")
        if medians["ladybird"] and medians["chromium"]:
            ratio = medians["ladybird"] / medians["chromium"]
            comparison = f"{ratio:.1f}x slower" if ratio >= 1 else f"{1 / ratio:.1f}x FASTER"
            print(f"  ratio     Ladybird is {comparison}")
        print()


if __name__ == "__main__":
    main()
