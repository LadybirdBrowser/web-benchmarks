"use strict";

// MicroWeb measurement harness.
//
// Each test page calls microbench({ iters, setup, run }) once. The runner in the parent
// frame reads window.__webKitPerfTestState, so this speaks the same contract as the
// imported WebKit performance suites: values is one elapsed-ms sample per iteration,
// unit is "ms". Tests are time-based over a fixed workload: faster code produces a
// smaller number rather than more runs.
//
// One untimed warm-up iteration runs first. Ladybird quantizes performance.now() to
// 0.1ms, so every test's fixed workload is sized to take at least a few milliseconds
// per iteration in a fast browser.

window.__webKitPerfTestState = { done: false, error: null, values: null, unit: "ms" };

window.addEventListener("error", (event) => {
    window.__webKitPerfTestState.error = event.message;
});
window.addEventListener("unhandledrejection", (event) => {
    window.__webKitPerfTestState.error = String(event.reason);
});

function microbench(test) {
    const state = window.__webKitPerfTestState;
    const requested = Number.parseInt(new URLSearchParams(location.search).get("iterationCount"));
    const iterationCount = requested > 0 ? requested : 1;
    (async () => {
        const values = [];
        for (let iteration = -1; iteration < iterationCount; iteration++) {
            const ctx = test.setup ? test.setup(iteration) : null;
            const start = performance.now();
            const result = test.run(ctx, test.iters);
            if (result && typeof result.then === "function")
                await result;
            const elapsed = performance.now() - start;
            if (iteration >= 0)
                values.push(elapsed);
            if (test.betweenIterations)
                await test.betweenIterations();
            await new Promise((resolve) => setTimeout(resolve, 0));
        }
        state.values = values;
        state.done = true;
    })().catch((error) => {
        state.error = String(error);
    });
}

// A render-pipeline test: each iteration performs `cycles` rounds of mutate followed by a
// forced synchronous style+layout flush. Paint is deliberately outside the timed region
// (it would only measure vsync waits); iterations are separated by a settled frame so no
// backlog leaks between samples.
function pipelineBench({ cycles, setup, mutate, iters }) {
    microbench({
        iters: iters || cycles,
        setup,
        run: (ctx) => {
            for (let k = 0; k < cycles; k++) {
                mutate(ctx, k);
                forceLayout();
            }
        },
        betweenIterations: settleFrame,
    });
}

function forceLayout() {
    return document.body.offsetHeight;
}

function settleFrame() {
    return new Promise((resolve) => {
        requestAnimationFrame(() => setTimeout(resolve, 0));
    });
}

// --- Shared DOM builders -------------------------------------------------------------

const sandbox = () => document.getElementById("sandbox");

let stylesInjected = false;
function ensureListStyles() {
    if (stylesInjected)
        return;
    stylesInjected = true;
    const style = document.createElement("style");
    style.textContent = `
        .todo-list { list-style: none; margin: 0; padding: 0; }
        .todo-list li { border-bottom: 1px solid #ededed; font-size: 24px; }
        .todo-list li.completed label { color: #d9d9d9; text-decoration: line-through; }
        .todo-list li.hidden-item { display: none; }
        .toggle, .destroy { width: 40px; height: 40px; }
        .todo-list label { word-break: break-all; padding: 15px; display: inline-block; }
    `;
    document.head.appendChild(style);
}

function makeListItem(i, completed) {
    const li = document.createElement("li");
    if (completed)
        li.className = "completed";
    const view = document.createElement("div");
    view.className = "view";
    const toggle = document.createElement("input");
    toggle.className = "toggle";
    toggle.type = "checkbox";
    toggle.checked = !!completed;
    const label = document.createElement("label");
    label.textContent = "Something to do " + i + " lorem ipsum dolor sit amet";
    const destroy = document.createElement("button");
    destroy.className = "destroy";
    view.appendChild(toggle);
    view.appendChild(label);
    view.appendChild(destroy);
    li.appendChild(view);
    return li;
}

// Build (or rebuild) the shared attached list and return its <ul>.
function buildList(n) {
    ensureListStyles();
    let list = document.getElementById("list");
    if (!list) {
        list = document.createElement("ul");
        list.id = "list";
        list.className = "todo-list";
        sandbox().appendChild(list);
    }
    list.textContent = "";
    for (let i = 0; i < n; i++)
        list.appendChild(makeListItem(i, false));
    return list;
}

function listItemHTML(i, completed) {
    return `<li${completed ? ' class="completed"' : ""}><div class="view"><input class="toggle" type="checkbox"${completed ? " checked" : ""}><label>Something to do ${i} lorem ipsum dolor sit amet</label><button class="destroy"></button></div></li>`;
}

function listHTML(n, completedUpTo) {
    let out = "";
    for (let i = 0; i < n; i++)
        out += listItemHTML(i, i < (completedUpTo || 0));
    return out;
}

function makeDetachedTree(n) {
    const ul = document.createElement("ul");
    for (let i = 0; i < n; i++) {
        const li = document.createElement("li");
        li.className = "item c" + (i % 10);
        li.setAttribute("data-id", String(i));
        const label = document.createElement("label");
        label.textContent = "item " + i;
        li.appendChild(label);
        ul.appendChild(li);
    }
    return ul;
}

function canvas2d(width, height) {
    // Clear the sandbox so per-iteration setup does not grow the document: a bigger
    // document would make later iterations measure different work than earlier ones.
    sandbox().textContent = "";
    const canvas = document.createElement("canvas");
    canvas.width = width || 800;
    canvas.height = height || 600;
    sandbox().appendChild(canvas);
    return canvas.getContext("2d");
}

const SVG_NS = "http://www.w3.org/2000/svg";

function makeSVG(pathCount) {
    sandbox().textContent = "";
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", "600");
    svg.setAttribute("height", "300");
    for (let i = 0; i < (pathCount || 0); i++) {
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", "M0,0L10,10");
        path.setAttribute("stroke", "steelblue");
        path.setAttribute("fill", "none");
        svg.appendChild(path);
    }
    sandbox().appendChild(svg);
    return svg;
}

function wigglyPathData(seed, points) {
    let d = "M0," + (seed % 7);
    for (let x = 0; x < points; x++)
        d += "L" + x * 20 + "," + ((x * 7919 + seed * 31) % 300);
    return d;
}

// Inject a stylesheet exactly once per page, no matter how many iterations run setup.
const injectedStyleIDs = new Set();
function injectStyleOnce(id, css) {
    if (injectedStyleIDs.has(id))
        return;
    injectedStyleIDs.add(id);
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
}

let uniqueStringCounter = 0;
function uniqueString() {
    return "unique text nobody shaped before " + uniqueStringCounter++;
}

function makeFlexContainer(n) {
    sandbox().textContent = "";
    injectStyleOnce("flex-styles", `
        .flex-container { display: flex; flex-wrap: wrap; width: 600px; }
        .flex-item { flex: 1 1 40px; height: 20px; margin: 1px; background: #dde; }
        .flex-item.wide { flex-basis: 120px; }
    `);
    const container = document.createElement("div");
    container.className = "flex-container";
    for (let i = 0; i < n; i++) {
        const item = document.createElement("div");
        item.className = "flex-item";
        item.textContent = String(i % 10);
        container.appendChild(item);
    }
    sandbox().appendChild(container);
    return container;
}

function makeGrid(columns, n) {
    sandbox().textContent = "";
    injectStyleOnce("grid-styles", `
        .grid-container { display: grid; grid-template-columns: repeat(${columns}, 30px); }
        .grid-item { height: 20px; background: #ded; }
    `);
    const container = document.createElement("div");
    container.className = "grid-container";
    for (let i = 0; i < n; i++) {
        const item = document.createElement("div");
        item.className = "grid-item";
        item.textContent = String(i % 10);
        container.appendChild(item);
    }
    sandbox().appendChild(container);
    return container;
}

function makeTable(rows, columns) {
    sandbox().textContent = "";
    const table = document.createElement("table");
    const tbody = document.createElement("tbody");
    for (let r = 0; r < rows; r++) {
        const tr = document.createElement("tr");
        for (let c = 0; c < columns; c++) {
            const td = document.createElement("td");
            td.textContent = "r" + r + "c" + c;
            tr.appendChild(td);
        }
        tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    sandbox().appendChild(table);
    return table;
}

function makeParagraph(sentences) {
    sandbox().textContent = "";
    const p = document.createElement("p");
    p.style.width = "600px";
    p.textContent = "The quick brown fox jumps over the lazy dog near the river bank. ".repeat(sentences);
    sandbox().appendChild(p);
    return p;
}
