#!/usr/bin/env python3
import argparse
import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlunparse

from tabulate import tabulate

# How long the browser gets to launch, load the page, and start running the first test.
STARTUP_TIMEOUT_SECONDS = 10

# How long the browser gets to exit after being sent SIGINT at the end of a benchmark.
SHUTDOWN_GRACE_PERIOD_SECONDS = 10

test_results = {}
benchmark_totals = {}
def append_table_data(benchmark, results):
    def append_tests_recursively(benchmark, json_object, suite=None, test=None):
        if isinstance(json_object, dict):
            if "total" in json_object and isinstance(json_object["total"], (int, float)):
                if suite is not None and test is not None:
                    if benchmark not in test_results:
                        test_results[benchmark] = {}
                    if suite not in test_results[benchmark]:
                        test_results[benchmark][suite] = {}
                    if test not in test_results[benchmark][suite]:
                        test_results[benchmark][suite][test] = []
                    test_results[benchmark][suite][test].append(json_object["total"] / 1000)

            if "tests" in json_object and isinstance(json_object["tests"], dict):
                for key, value in json_object["tests"].items():
                    if suite is not None:
                        append_tests_recursively(benchmark, value, suite, key)
                    else:
                        append_tests_recursively(benchmark, value, key)

    append_tests_recursively(benchmark, results)

    if benchmark not in benchmark_totals:
        benchmark_totals[benchmark] = {}

    if "totalTime" not in benchmark_totals[benchmark]:
        benchmark_totals[benchmark]["totalTime"] = []
    benchmark_totals[benchmark]["totalTime"].append(results["total"] / 1000)

    if "score" in results:
        if "reported_score" not in benchmark_totals[benchmark]:
            benchmark_totals[benchmark]["reported_score"] = []
        benchmark_totals[benchmark]["reported_score"].append(results["score"])

class BenchmarkHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        self.server.last_progress_time = time.monotonic()
        if self.path == "/TestStarting":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            json_data = json.loads(post_data.decode('utf-8'))
            self.server.current_test = "/".join(filter(None, (json_data["benchmark"], json_data["suite"], json_data["test"])))
            self.server.phase = "running"
            self.send_response(200)
            self.end_headers()

        elif self.path == "/TestComplete":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            json_data = json.loads(post_data.decode('utf-8'))
            test_name = "/".join(filter(None, (json_data["benchmark"], json_data["suite"], json_data["test"])))
            print(f"Iteration {self.server.iteration_count}: Completed '{test_name}'")
            self.send_response(200)
            self.end_headers()

        elif self.path == "/IterationComplete":
            self.server.iteration_count += 1
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            json_data = json.loads(post_data.decode('utf-8'))
            append_table_data(json_data["benchmark"], json_data["results"])
            self.send_response(200)
            self.end_headers()

        elif self.path == "/BenchmarkComplete":
            self.server.phase = "finished"
            def run_callback():
                if self.server.running_ladybird_process:
                    self.server.running_ladybird_process.send_signal(signal.SIGINT)

            self.send_response(200)
            self.end_headers()
            threading.Thread(target=run_callback, daemon=True).start()
            return
        else:
            self.send_error(404, "No such POST endpoint")


    def log_message(self, format, *args):
        pass


def start_http_server():
    server = HTTPServer(('localhost', 0), BenchmarkHTTPRequestHandler)
    server.running_ladybird_process = None
    server.iteration_count = 1
    server.last_progress_time = time.monotonic()
    server.current_test = None
    server.phase = "startup"
    server.server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.server_thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(server.server_address, timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        print("Error: HTTP server did not start within timeout")
        server.shutdown()
        sys.exit(1)
    return server


def run_benchmark(benchmark_path, runner_url, benchmark_params, ladybird_arguments, timeout, verbose=False):
    current_dir = os.getcwd()
    os.chdir(benchmark_path)
    server = start_http_server()
    profile = tempfile.TemporaryDirectory(prefix="ladybird-benchmark-profile-")

    query = urlencode(benchmark_params)
    _, port = server.server_address
    url = urlunparse(("http", f"localhost:{port}", runner_url, "", query, ""))

    ladybird_cmd = ladybird_arguments + ["--profile-path", profile.name, url]

    try:
        if verbose:
            process = subprocess.Popen(ladybird_cmd)
        else:
            process = subprocess.Popen(
                ladybird_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        server.running_ladybird_process = process

        while True:
            try:
                process.wait(timeout=0.5)
                if server.phase != "finished":
                    print(f"Error: Benchmark process exited with status {process.returncode} before completing.", file=sys.stderr)
                    return False
                return True
            except subprocess.TimeoutExpired:
                stalled_time = time.monotonic() - server.last_progress_time
                if server.phase == "startup":
                    if stalled_time > STARTUP_TIMEOUT_SECONDS:
                        print(f"Error: Benchmark did not start running tests within {STARTUP_TIMEOUT_SECONDS} seconds.", file=sys.stderr)
                        break
                elif server.phase == "running":
                    if timeout and stalled_time > timeout:
                        print(f"Error: Test '{server.current_test}' did not complete within {timeout:g} seconds.", file=sys.stderr)
                        break
                elif server.phase == "finished":
                    if stalled_time > SHUTDOWN_GRACE_PERIOD_SECONDS:
                        process.kill()
                        process.wait()
                        return True

        process.kill()
        process.wait()
        return False

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        process.kill()
        sys.exit(1)
    finally:
        server.shutdown()
        server.server_close()
        server.server_thread.join(timeout=2)
        profile.cleanup()
        os.chdir(current_dir)


def main():
    available_benchmarks = {
        "Speedometer2": { "runner_url": "index.html" },
        "Speedometer3": { "runner_url": "index.html" },
        "StyleBench": { "runner_url": "index.html" },
        "StyleBenchConservative": { "runner_url": "StyleBenchConservative/index.html", "server_root": "." },
        "WebKitBindings": { "runner_url": "index.html", "timeout": 30 },
        "WebKitCSS": { "runner_url": "index.html", "timeout": 30 },
        "WebKitDOM": { "runner_url": "index.html", "timeout": 30 },
        "WebKitParser": { "runner_url": "index.html", "timeout": 30 },
        "WebKitSVG": { "runner_url": "index.html", "timeout": 30 },
    }

    parser = argparse.ArgumentParser(description="Speedometer benchmark runner")
    parser.add_argument("--executable", type=str, help="Path to Ladybird executable", required=True)
    parser.add_argument("--benchmarks", type=str, help="Benchmarks to run (comma-separated)", default="all")
    parser.add_argument("--iterations", type=int, help="Number of iterations to run")
    parser.add_argument("--show-window", action="store_true", help="Show the browser window during the test run")
    parser.add_argument("--output", "-o", default="results.json", help="JSON output file name.")
    parser.add_argument("--timeout", type=float, help="Per-test timeout in seconds; the browser is killed if no test completes within this time (0 to disable)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show stdout and stderr output from the browser")

    args = parser.parse_args()

    benchmarks = {}
    if args.benchmarks == "all":
        benchmarks = available_benchmarks
    else:
        for benchmark_arg in args.benchmarks.split(","):
            assert benchmark_arg in available_benchmarks, f"Invalid benchmark argument: {benchmark_arg}"
            benchmarks[benchmark_arg] = available_benchmarks[benchmark_arg]

    params = []
    if args.iterations:
        params.append(("iterationCount", str(args.iterations)))

    if not Path(args.executable).is_file():
        print(f"Error: Executable '{args.executable}' not found.", file=sys.stderr)
        sys.exit(1)

    ladybird_arguments = [args.executable]
    if not args.show_window:
        ladybird_arguments += ["--headless=manual"]

    benchmarks_dir = Path(__file__).parent / "benchmarks"

    failed_benchmarks = []
    for benchmark in benchmarks:
        if args.benchmarks != "all" and benchmark not in args.benchmarks.split(","):
            continue
        runner_url = available_benchmarks[benchmark]["runner_url"]
        timeout = args.timeout if args.timeout is not None else available_benchmarks[benchmark].get("timeout", 10)
        benchmark_path = benchmarks_dir / benchmark
        if not benchmark_path.exists():
            print(f"Benchmark '{benchmark}' not found in benchmarks directory.", file=sys.stderr)
            sys.exit(1)
        server_root = benchmarks_dir / available_benchmarks[benchmark].get("server_root", benchmark)
        if not run_benchmark(server_root, runner_url, params, ladybird_arguments, timeout, verbose=args.verbose):
            failed_benchmarks.append(benchmark)

    test_times_data = []
    for benchmark, suites in test_results.items():
        for suite, tests in suites.items():
            for test_name, total in tests.items():
                mean_value = statistics.mean(total)
                std_dev = statistics.stdev(total) if len(total) > 1 else 0.0
                min_value = min(total)
                max_value = max(total)
                test_times_data.append([benchmark, suite, test_name, f"{mean_value:.4f} ± {std_dev:.4f}", f"{min_value:.4f} … {max_value:.4f}"])
    benchmark_scores_data = []
    for total in benchmark_totals.items():
        benchmark, values = total
        times = values["totalTime"]
        mean_time = statistics.mean(times)
        std_dev_time = statistics.stdev(times) if len(times) > 1 else 0.0
        min_time = min(times)
        max_time = max(times)
        test_times_data.append([benchmark, "Total", "", f"{mean_time:.4f} ± {std_dev_time:.4f}", f"{min_time:.4f} … {max_time:.4f}"])
        if "reported_score" in values:
            scores = values["reported_score"]
            mean_score = statistics.mean(scores)
            std_dev_score = statistics.stdev(scores) if len(scores) > 1 else 0.0
            min_score = min(scores)
            max_score = max(scores)
            benchmark_scores_data.append([benchmark, f"{mean_score:.2f} ± {std_dev_score:.2f}", f"{min_score:.2f} … {max_score:.2f}", f"{mean_time:.4f} ± {std_dev_time:.4f}", f"{min_time:.4f} … {max_time:.4f}"])
    print()
    print(tabulate(test_times_data, headers=["Benchmark", "Suite", "Test", "Mean ± σ (s)", "Range (s)"]))
    if benchmark_scores_data:
        print()
        print(tabulate(benchmark_scores_data, headers=["Benchmark", "Score Mean ± σ", "Score Range", "Time Mean ± σ (s)", "Time Range (s)"]))

    # The format of this JSON output matches that generated by the js-benchmarks repository.
    formatted_results = {}
    for benchmark, suites in test_results.items():
        formatted_results[benchmark] = {}
        for suite, tests in suites.items():
            for test_name, runs in tests.items():
                key = f"{suite}/{test_name}" if suite else test_name
                mean_value = statistics.mean(runs)
                std_dev = statistics.stdev(runs) if len(runs) > 1 else 0.0
                min_value = min(runs)
                max_value = max(runs)
                formatted_results[benchmark][key] = {
                    "category": "Web",
                    "time": {
                        "mean": mean_value,
                        "stdev": std_dev,
                        "min": min_value,
                        "max": max_value,
                        "runs": runs
                    }
                }

        if benchmark in benchmark_totals:
            totals = benchmark_totals[benchmark]
            if "totalTime" in totals:
                times = totals["totalTime"]
                formatted_results[benchmark]["_total"] = {
                    "time": {
                        "mean": statistics.mean(times),
                        "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
                        "min": min(times),
                        "max": max(times),
                        "runs": times
                    }
                }
            if "reported_score" in totals:
                scores = totals["reported_score"]
                if "_total" not in formatted_results[benchmark]:
                    formatted_results[benchmark]["_total"] = {}
                formatted_results[benchmark]["_total"]["reported_score"] = {
                    "mean": statistics.mean(scores),
                    "stdev": statistics.stdev(scores) if len(scores) > 1 else 0.0,
                    "min": min(scores),
                    "max": max(scores),
                    "runs": scores
                }

    with open(args.output, "w") as f:
        json.dump(formatted_results, f, indent=4)

    if failed_benchmarks:
        print(f"\nError: The following benchmarks failed: {', '.join(failed_benchmarks)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
