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
        // Optional one-time async preparation (e.g. fetching a fixture), untimed.
        const prepared = test.prepare ? await test.prepare() : undefined;
        const values = [];
        for (let iteration = -1; iteration < iterationCount; iteration++) {
            const ctx = test.setup ? test.setup(iteration, prepared) : prepared === undefined ? null : prepared;
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
function pipelineBench({ cycles, prepare, setup, mutate, iters }) {
    microbench({
        iters: iters || cycles,
        prepare,
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

// --- Speedometer 3 fixtures -------------------------------------------------------------

// TodoMVC markup as the Speedometer 3 apps render it (todomvc-css + data-priority).
function todoTitle(i) {
    const texts = ["Walk the dog", "Buy groceries", "牛乳を買う", "犬の散歩に行く", "Купить молоко", "Погулять с собакой", "Pay the electricity bill", "Water the plants"];
    return texts[i % texts.length] + " " + i;
}

function makeTodoItem(i, completed) {
    const li = makeListItem(i, completed);
    li.setAttribute("data-id", String(i));
    li.setAttribute("data-priority", String(4 - (i % 5)));
    li.querySelector("label").textContent = todoTitle(i);
    return li;
}

function todoItemHTML(i, completed) {
    return `<li data-id="${i}" class="${completed ? "completed" : ""}" data-priority="${4 - (i % 5)}"><div class="view"><input class="toggle" type="checkbox"${completed ? " checked" : ""}><label>${todoTitle(i)}</label><button class="destroy"></button></div></li>`;
}

const TODO_APP_HTML = `<section class="todoapp"><header class="header"><h1>todos</h1><input class="new-todo" placeholder="What needs to be done?"></header><main class="main"><div class="toggle-all-container"><input class="toggle-all" type="checkbox"><label class="toggle-all-label" for="toggle-all">Mark all as complete</label></div><ul class="todo-list show-priority"></ul></main><footer class="footer"><span class="todo-count"><strong>0</strong> items left</span><ul class="filters"><li><a class="selected" href="#/">All</a></li><li><a href="#/active">Active</a></li><li><a href="#/completed">Completed</a></li></ul><button class="clear-completed">Clear completed</button></footer></section>`;

function loadStylesheet(href) {
    return new Promise((resolve, reject) => {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        link.onload = resolve;
        link.onerror = () => reject(new Error("failed to load " + href));
        document.head.appendChild(link);
    });
}

// The Speedometer 3 "Complex DOM" page: the ~6600-element Spectrum shell generated by
// todomvc/big-dom-generator, with big-dom.css and the todo-targeted rules of its app.css.
// The todo app is mounted in .todo-area. Use as a microbench `prepare`; resolves to the
// todo <ul>.
async function loadComplexDOM() {
    document.documentElement.className = "spectrum spectrum--medium spectrum--light";
    await loadStylesheet("../resources/complex-dom/big-dom.css");
    await loadStylesheet("../resources/complex-dom/app.css");
    const html = await (await fetch("../resources/complex-dom/big-dom-body.html")).text();
    sandbox().insertAdjacentHTML("afterbegin", html);
    const area = document.querySelector(".todo-area");
    area.innerHTML = TODO_APP_HTML;
    forceLayout();
    return area.querySelector(".todo-list");
}

function fillTodoList(list, n, completedEvery) {
    list.textContent = "";
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < n; i++)
        fragment.appendChild(makeTodoItem(i, completedEvery ? i % completedEvery === 0 : false));
    list.appendChild(fragment);
    return list;
}

// --- StyleBench-shaped fixtures -------------------------------------------------------
// Seeded, so every browser builds the identical tree and stylesheet.

function seededRandom(seed) {
    let state = seed;
    return (under) => {
        state = (state * 16807) % 2147483647;
        return Math.floor(((state % 1048576) / 1048576) * under);
    };
}

// StyleBench's base style: every element under the sandbox is a small inline-block.
function injectInlineBlockStyle() {
    injectStyleOnce("inline-block-tree", `
        #sandbox { font-size: 10px; line-height: 10px; }
        #sandbox * { display: inline-block; height: 10px; min-width: 10px; }
    `);
}

// A detached tree of `count` elements named elem0..elem9, shaped like StyleBench's: up
// to six levels deep and wider further down, mostly leaves. About half the elements
// carry one or two of classCount classes.
function makeInlineBlockTree(count, { seed = 2, classCount = 200 } = {}) {
    const random = seededRandom(seed);
    const root = document.createElement("div");
    let remaining = count;
    function fill(parent, depth) {
        let width = 0;
        if (depth === 0)
            width = remaining;
        else if (random(6) < 6 - depth)
            width = random(Math.floor(50 * depth / 6));
        for (let i = 0; i < width && remaining > 0; i++) {
            const element = document.createElement("elem" + random(10));
            if (random(2))
                element.className = "class" + random(classCount) + (random(3) ? "" : " class" + random(classCount));
            parent.appendChild(element);
            remaining--;
            fill(element, depth + 1);
        }
    }
    fill(root, 0);
    return root;
}

// `count` rules of random descendant/child selectors over the classes and element names
// of makeInlineBlockTree, each setting a background color.
function makeRuleSheetText(count, { seed = 1, classCount = 200 } = {}) {
    const random = seededRandom(seed);
    let css = "";
    for (let i = 0; i < count; i++) {
        const length = random(6) + 1;
        const parts = [];
        for (let j = 0; j < length; j++) {
            const compound = (random(2) ? "elem" + random(10) : "") + ".class" + random(Math.max(1, Math.round(classCount * (j + 1) / length)));
            parts.push(compound);
            if (j < length - 1)
                parts.push(random(2) ? ">" : "");
        }
        const selector = parts.filter(Boolean).join(" ");
        css += selector + ` { background-color: rgb(${random(256)}, ${random(256)}, ${random(256)}); }\n`;
    }
    return css;
}
