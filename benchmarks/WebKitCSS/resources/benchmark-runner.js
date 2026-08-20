"use strict";

const configuration = window.webKitBenchmark;
const searchParameters = new URLSearchParams(location.search);
const requestedIterationCount = Number.parseInt(searchParameters.get("iterationCount"));
const iterationCount = requestedIterationCount > 0 ? requestedIterationCount : 1;
const frame = document.querySelector("iframe");
const status = document.querySelector("p");

function post(path, body) {
    return fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json;charset=UTF-8" },
        body: JSON.stringify(body),
    });
}

function testPath(test) {
    return typeof test === "string" ? test : test.path;
}

function loadTest(test) {
    return new Promise((resolve) => {
        const parameters = new URLSearchParams({ iterationCount });
        if (typeof test !== "string")
            parameters.set("runCount", test.runCount);
        frame.onload = resolve;
        frame.src = `${testPath(test)}?${parameters}`;
    });
}

function waitForTest() {
    return new Promise((resolve, reject) => {
        const timer = setInterval(() => {
            const state = frame.contentWindow.__webKitPerfTestState;
            if (!state)
                return;
            if (state.error) {
                clearInterval(timer);
                reject(new Error(state.error));
            } else if (state.done) {
                clearInterval(timer);
                resolve(state);
            }
        }, 25);
    });
}

function millisecondsFor(value, unit) {
    if (unit === "ms")
        return value;
    throw new Error(`Unsupported WebKit performance test unit: ${unit}`);
}

function testName(path) {
    return path.slice(configuration.suite.length + 1, -".html".length);
}

async function runBenchmark() {
    const testResults = [];
    for (const test of configuration.tests) {
        const path = testPath(test);
        const name = testName(path);
        status.textContent = `Running ${configuration.name}/${name}`;
        await post("/TestStarting", { benchmark: configuration.name, suite: "", test: name });
        await loadTest(test);
        const state = await waitForTest();
        if (state.values.length !== iterationCount)
            throw new Error(`${path} produced ${state.values.length} values, expected ${iterationCount}`);
        testResults.push({ name, values: state.values, unit: state.unit });
        await post("/TestComplete", { benchmark: configuration.name, suite: "", test: name });
    }

    for (let iteration = 0; iteration < iterationCount; ++iteration) {
        const tests = {};
        let total = 0;
        for (const result of testResults) {
            const milliseconds = millisecondsFor(result.values[iteration], result.unit);
            tests[result.name] = { total: milliseconds };
            total += milliseconds;
        }
        const results = {
            total,
            tests: {
                "": { total, tests },
            },
        };
        await post("/IterationComplete", { benchmark: configuration.name, results });
    }

    status.textContent = "Complete";
    await post("/BenchmarkComplete", { benchmark: configuration.name });
}

runBenchmark().catch((error) => {
    status.textContent = `Failed: ${error.message}`;
    console.error(error);
});
