"use strict";

// MicroWeb suite runner. Same shape as the imported WebKit suites' benchmark-runner.js,
// but tests live in category directories (dom/, render/, js/, ...) and report as
// suite = category, test = file name.

const configuration = window.microWebBenchmark;
const searchParameters = new URLSearchParams(location.search);
const requestedIterationCount = Number.parseInt(searchParameters.get("iterationCount"));
const iterationCount = requestedIterationCount > 0 ? requestedIterationCount : 1;
// With ?category=dom only that directory's tests run. The harness uses this to give
// each category a fresh browser, keeping session-aging effects out of the numbers.
const categoryFilter = searchParameters.get("category");
const selectedTests = configuration.tests.filter((path) => !categoryFilter || path.startsWith(categoryFilter + "/"));
const frame = document.querySelector("iframe");
const status = document.querySelector("p");

function post(path, body) {
    return fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json;charset=UTF-8" },
        body: JSON.stringify(body),
    });
}

function categoryOf(path) {
    return path.slice(0, path.indexOf("/"));
}

function testNameOf(path) {
    return path.slice(path.indexOf("/") + 1, -".html".length);
}

function loadTest(path) {
    return new Promise((resolve) => {
        frame.onload = resolve;
        frame.src = `${path}?${new URLSearchParams({ iterationCount })}`;
    });
}

// Stay under run.py's per-test timeout so a hung test fails here, where the suite can
// continue, instead of getting the whole browser killed.
const TEST_TIMEOUT_MILLISECONDS = 25000;

function waitForTest(path) {
    return new Promise((resolve, reject) => {
        const startTime = performance.now();
        let lastHeartbeat = startTime;
        const timer = setInterval(() => {
            // A slow engine can spend well over the harness's stall timeout inside one
            // test between the TestStarting and TestComplete posts. Heartbeats tell the
            // harness the suite is alive so it does not kill the browser mid-test.
            if (performance.now() - lastHeartbeat > 5000) {
                lastHeartbeat = performance.now();
                post("/Heartbeat", { benchmark: configuration.name, test: path });
            }
            const state = frame.contentWindow.__webKitPerfTestState;
            if (state && state.error) {
                clearInterval(timer);
                reject(new Error(`${path}: ${state.error}`));
            } else if (state && state.done) {
                clearInterval(timer);
                resolve(state);
            } else if (performance.now() - startTime > TEST_TIMEOUT_MILLISECONDS) {
                clearInterval(timer);
                reject(new Error(`${path} timed out`));
            }
        }, 25);
    });
}

async function runBenchmark() {
    const testResults = [];
    const failedTests = [];
    for (const path of selectedTests) {
        const suite = categoryOf(path);
        const name = testNameOf(path);
        status.textContent = `Running ${suite}/${name}`;
        await post("/TestStarting", { benchmark: configuration.name, suite, test: name });
        // One broken or unsupported test must not sink the other tests' results: record
        // the failure and move on. A failed test simply has no row in the output, which
        // ratios.py treats as missing data rather than a zero.
        try {
            await loadTest(path);
            const state = await waitForTest(path);
            if (state.values.length !== iterationCount)
                throw new Error(`${path} produced ${state.values.length} values, expected ${iterationCount}`);
            testResults.push({ suite, name, values: state.values });
        } catch (error) {
            failedTests.push({ path, message: String(error && error.message || error) });
            console.error(`MicroWeb: ${path} failed: ${error}`);
        }
        await post("/TestComplete", { benchmark: configuration.name, suite, test: name });
    }
    if (failedTests.length)
        status.textContent = `${failedTests.length} tests failed: ${failedTests.map((t) => t.path).join(", ")}`;

    for (let iteration = 0; iteration < iterationCount; ++iteration) {
        const suites = {};
        let total = 0;
        for (const result of testResults) {
            const milliseconds = result.values[iteration];
            if (!(result.suite in suites))
                suites[result.suite] = { total: 0, tests: {} };
            suites[result.suite].tests[result.name] = { total: milliseconds };
            suites[result.suite].total += milliseconds;
            total += milliseconds;
        }
        await post("/IterationComplete", { benchmark: configuration.name, results: { total, tests: suites } });
    }

    status.textContent = "Complete";
    await post("/BenchmarkComplete", { benchmark: configuration.name });
}

runBenchmark().catch((error) => {
    status.textContent = `Failed: ${error.message}`;
    console.error(error);
});
