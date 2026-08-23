#!/usr/bin/env python3
"""Generate the MicroWeb test pages and index.html from the spec below.

Each entry becomes one small standalone HTML page that can also be opened directly in a
browser for debugging. Regenerate after editing the spec:

    ./resources/generate.py

Workload sizes (iters/cycles) are fixed so that one iteration takes at least a few
milliseconds in a fast browser: tests are time-based, and Ladybird quantizes
performance.now() to 0.1ms.
"""

import os
import textwrap

SUITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def page(description, body):
    return f"""<!DOCTYPE html>
<html>
<!-- {description} -->
<body>
<div id="sandbox"></div>
<script src="../resources/micro.js"></script>
<script>
{textwrap.dedent(body).strip()}
</script>
</body>
</html>
"""


def micro(description, iters, run, setup=None):
    parts = [f"    iters: {iters},"]
    if setup:
        parts.append(f"    setup: {textwrap.dedent(setup).strip()},")
    parts.append(f"    run: {textwrap.dedent(run).strip()},")
    body = "microbench({\n" + "\n".join(parts) + "\n});"
    return page(description, body)


def pipeline(description, cycles, mutate, setup):
    body = (
        "pipelineBench({\n"
        f"    cycles: {cycles},\n"
        f"    setup: {textwrap.dedent(setup).strip()},\n"
        f"    mutate: {textwrap.dedent(mutate).strip()},\n"
        "});"
    )
    return page(description, body)


TESTS = {}

# ======================================================================================
# dom/ — DOM API primitives, no rendering pipeline involvement.
# ======================================================================================

TESTS["dom/create-element.html"] = micro(
    "document.createElement of a plain div", 50000,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            document.createElement("div");
    }""")

TESTS["dom/create-text-node.html"] = micro(
    "document.createTextNode", 50000,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            document.createTextNode("hello world");
    }""")

TESTS["dom/create-element-ns.html"] = micro(
    "createElementNS in the SVG namespace", 20000,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            document.createElementNS("http://www.w3.org/2000/svg", "path");
    }""")

TESTS["dom/set-attribute.html"] = micro(
    "setAttribute with a cycling value on a detached element", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.setAttribute("data-x", "v" + (i & 7));
    }""")

TESTS["dom/get-attribute.html"] = micro(
    "getAttribute of an existing attribute", 50000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.setAttribute("data-x", "hello");
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.getAttribute("data-x").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/has-attribute.html"] = micro(
    "hasAttribute hit and miss", 50000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.setAttribute("data-x", "hello");
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.hasAttribute(i & 1 ? "data-x" : "data-y") ? 1 : 0;
        if (acc !== iters >> 1) throw new Error("bad result");
    }""")

TESTS["dom/toggle-attribute.html"] = micro(
    "toggleAttribute of a boolean attribute", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.toggleAttribute("hidden");
    }""")

TESTS["dom/class-list-toggle.html"] = micro(
    "classList.toggle on a detached element", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.classList.toggle("on");
    }""")

TESTS["dom/class-list-contains.html"] = micro(
    "classList.contains over a 4-class element", 50000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.className = "alpha beta gamma delta";
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.classList.contains(i & 1 ? "delta" : "nope") ? 1 : 0;
        if (acc !== iters >> 1) throw new Error("bad result");
    }""")

TESTS["dom/class-name-set.html"] = micro(
    "className setter with alternating values", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.className = i & 1 ? "a b c" : "a b";
    }""")

TESTS["dom/id-set.html"] = micro(
    "id setter with cycling values on a detached element", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.id = "x" + (i & 7);
    }""")

TESTS["dom/text-content-set.html"] = micro(
    "textContent setter on a detached element", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.textContent = "value " + (i & 15);
    }""")

TESTS["dom/text-content-read-tree.html"] = micro(
    "textContent read over a 1000-node detached tree", 500,
    setup="() => makeDetachedTree(1000)",
    run="""
    (tree, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += tree.textContent.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/append-remove-detached.html"] = micro(
    "appendChild + remove cycle on detached nodes", 50000,
    setup="""
    () => ({ parent: document.createElement("ul"), child: document.createElement("li") })""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.parent.appendChild(ctx.child);
            ctx.child.remove();
        }
    }""")

TESTS["dom/insert-before-middle.html"] = micro(
    "insertBefore into the middle of a 200-child detached list", 5000,
    setup="""
    () => {
        const ul = makeDetachedTree(200);
        return { ul, extra: document.createElement("li") };
    }""",
    run="""
    (ctx, iters) => {
        const middle = 100;
        for (let i = 0; i < iters; i++) {
            ctx.ul.insertBefore(ctx.extra, ctx.ul.children[middle]);
            ctx.extra.remove();
        }
    }""")

TESTS["dom/clone-node-deep.html"] = micro(
    "cloneNode(true) of a 100-node tree", 500,
    setup="() => makeDetachedTree(100)",
    run="""
    (tree, iters) => {
        for (let i = 0; i < iters; i++)
            tree.cloneNode(true);
    }""")

TESTS["dom/clone-node-shallow.html"] = micro(
    "cloneNode(false) of one element with attributes", 50000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.className = "a b c";
        el.setAttribute("data-id", "42");
        return el;
    }""",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.cloneNode(false);
    }""")

TESTS["dom/template-clone.html"] = micro(
    "template.content.cloneNode(true) of a 10-node item template", 5000,
    setup="""
    () => {
        const template = document.createElement("template");
        template.innerHTML = '<li class="item"><div class="view"><input class="toggle" type="checkbox"><label>text</label><button class="destroy"></button></div></li>';
        return template;
    }""",
    run="""
    (template, iters) => {
        for (let i = 0; i < iters; i++)
            template.content.cloneNode(true);
    }""")

TESTS["dom/dispatch-click.html"] = micro(
    "click() on a button with one listener, bubbling through 3 ancestors", 5000,
    setup="""
    () => {
        sandbox().textContent = "";
        const a = document.createElement("div");
        const b = document.createElement("div");
        const button = document.createElement("button");
        a.appendChild(b);
        b.appendChild(button);
        sandbox().appendChild(a);
        let count = 0;
        button.addEventListener("click", () => count++);
        return button;
    }""",
    run="""
    (button, iters) => {
        for (let i = 0; i < iters; i++)
            button.click();
    }""")

TESTS["dom/dispatch-custom-event.html"] = micro(
    "dispatchEvent of a CustomEvent with one listener", 50000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.addEventListener("x-ev", () => {});
        return el;
    }""",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.dispatchEvent(new CustomEvent("x-ev", { detail: i }));
    }""")

TESTS["dom/add-remove-event-listener.html"] = micro(
    "addEventListener + removeEventListener cycle", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        const listener = () => {};
        for (let i = 0; i < iters; i++) {
            el.addEventListener("click", listener);
            el.removeEventListener("click", listener);
        }
    }""")

TESTS["dom/get-element-by-id.html"] = micro(
    "getElementById in a document with a 200-element list", 50000,
    setup="""
    () => {
        buildList(200);
        const el = document.createElement("div");
        el.id = "needle";
        sandbox().appendChild(el);
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            document.getElementById("needle");
    }""")

TESTS["dom/get-elements-by-class-name.html"] = micro(
    "getElementsByClassName + iterate the live collection (200 hits)", 2000,
    setup="() => buildList(200)",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const collection = document.getElementsByClassName("toggle");
            for (let j = 0; j < collection.length; j++)
                acc += collection[j].nodeType;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/query-selector-class.html"] = micro(
    "querySelector('.needle') matching late in a 200-element list", 5000,
    setup="""
    () => {
        const list = buildList(200);
        list.children[150].classList.add("needle");
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            document.querySelector(".needle");
    }""")

TESTS["dom/query-selector-all-class.html"] = micro(
    "querySelectorAll('.toggle') collecting 200 matches", 2000,
    setup="() => buildList(200)",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += document.querySelectorAll(".toggle").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/query-selector-nth-child.html"] = micro(
    "querySelector('li:nth-child(i) .toggle') for every i, like the Speedometer3 driver", 1,
    setup="() => buildList(300)",
    run="""
    (ctx, iters) => {
        let found = 0;
        for (let i = 1; i <= 300; i++) {
            if (document.querySelector(`li:nth-child(${i}) .toggle`))
                found++;
        }
        if (found !== 300) throw new Error("bad result");
    }""")

TESTS["dom/matches-selector.html"] = micro(
    "element.matches with a descendant selector", 20000,
    setup="""
    () => {
        buildList(50);
        return document.querySelector(".toggle");
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.matches(".todo-list .toggle") ? 1 : 0;
        if (acc !== iters) throw new Error("bad result");
    }""")

TESTS["dom/closest-selector.html"] = micro(
    "element.closest from a leaf to a list-root selector", 20000,
    setup="""
    () => {
        buildList(50);
        return document.querySelector(".toggle");
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.closest(".todo-list") ? 1 : 0;
        if (acc !== iters) throw new Error("bad result");
    }""")

TESTS["dom/node-list-iterate.html"] = micro(
    "indexed iteration over a 200-element static NodeList", 2000,
    setup="""
    () => {
        buildList(200);
        return document.querySelectorAll("li");
    }""",
    run="""
    (nodeList, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            for (let j = 0; j < nodeList.length; j++)
                acc += nodeList[j].nodeType;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/child-nodes-walk.html"] = micro(
    "firstChild/nextSibling walk over 1000 children", 2000,
    setup="() => makeDetachedTree(1000)",
    run="""
    (tree, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            for (let node = tree.firstChild; node; node = node.nextSibling)
                acc++;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/tree-walker.html"] = micro(
    "TreeWalker traversal of a 1000-node tree", 500,
    setup="() => makeDetachedTree(1000)",
    run="""
    (tree, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const walker = document.createTreeWalker(tree, NodeFilter.SHOW_ELEMENT);
            while (walker.nextNode())
                acc++;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/dataset-access.html"] = micro(
    "dataset property read", 50000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.dataset.foo = "bar";
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.dataset.foo.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/node-name-access.html"] = micro(
    "nodeName getter", 50000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.nodeName.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/style-set-property.html"] = micro(
    "style.setProperty('color', ...) on a detached element", 20000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.style.setProperty("color", i & 1 ? "red" : "blue");
    }""")

TESTS["dom/style-css-text.html"] = micro(
    "style.cssText set with a 3-declaration block", 5000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.style.cssText = "color: red; width: " + (i & 63) + "px; display: block;";
    }""")

TESTS["dom/input-value-set.html"] = micro(
    "input.value setter, like the Speedometer3 driver typing", 20000,
    setup="""
    () => {
        const input = document.createElement("input");
        sandbox().appendChild(input);
        return input;
    }""",
    run="""
    (input, iters) => {
        for (let i = 0; i < iters; i++)
            input.value = "Something to buy " + (i & 63);
    }""")

TESTS["dom/checkbox-checked-toggle.html"] = micro(
    "checkbox.checked toggle on a detached input", 50000,
    setup="""
    () => {
        const input = document.createElement("input");
        input.type = "checkbox";
        return input;
    }""",
    run="""
    (input, iters) => {
        for (let i = 0; i < iters; i++)
            input.checked = !input.checked;
    }""")

# ======================================================================================
# render/ — mutations followed by a forced synchronous style+layout flush.
# Paint is outside the timed region; these isolate the invalidation-to-layout pipeline.
# ======================================================================================

TESTS["render/forced-layout-noop.html"] = pipeline(
    "offsetHeight with nothing invalidated: the flush floor", 50,
    setup="() => buildList(500)",
    mutate="() => {}")

TESTS["render/class-toggle-one.html"] = pipeline(
    "toggle a paint-only class on one item of a 500-item list, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].classList.toggle("completed");
    }""")

TESTS["render/display-toggle-one.html"] = pipeline(
    "toggle display:none on one item of a 500-item list, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].classList.toggle("hidden-item");
    }""")

TESTS["render/display-toggle-one-large.html"] = pipeline(
    "toggle display:none on one item of a 2000-item list: does cost scale with document size?", 10,
    setup="() => buildList(2000)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 2000].classList.toggle("hidden-item");
    }""")

TESTS["render/visibility-toggle-one.html"] = pipeline(
    "toggle visibility:hidden on one item, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        const item = list.children[(k * 37) % 500];
        item.style.visibility = item.style.visibility === "hidden" ? "" : "hidden";
    }""")

TESTS["render/color-change-one.html"] = pipeline(
    "change color on one item, then force layout (paint-only property)", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].style.color = k & 1 ? "rgb(200, 0, 0)" : "rgb(0, 0, 200)";
    }""")

TESTS["render/text-change-one.html"] = pipeline(
    "change one label's text, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].querySelector("label").textContent = "changed " + k;
    }""")

TESTS["render/width-change-container.html"] = pipeline(
    "alternate the list container's width, then force layout (invalidates every line)", 20,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.style.width = k & 1 ? "80%" : "90%";
    }""")

TESTS["render/transform-change-one.html"] = pipeline(
    "change transform on one item, then force layout (should not need layout)", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].style.transform = "translateX(" + (k & 7) + "px)";
    }""")

TESTS["render/opacity-change-one.html"] = pipeline(
    "change opacity on one item, then force layout (should not need layout)", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].style.opacity = k & 1 ? "0.5" : "1";
    }""")

TESTS["render/append-one-item.html"] = pipeline(
    "append one new item to a 500-item list, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.appendChild(makeListItem(1000 + k, false));
    }""")

TESTS["render/insert-middle-item.html"] = pipeline(
    "insert one new item into the middle of a 500-item list, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        list.insertBefore(makeListItem(1000 + k, false), list.children[250]);
    }""")

TESTS["render/remove-one-item.html"] = pipeline(
    "remove one item from a 500-item list, then force layout", 50,
    setup="() => buildList(550)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 500].remove();
    }""")

TESTS["render/append-100-items.html"] = pipeline(
    "append 100 items one by one, forcing layout once at the end of each batch", 5,
    setup="() => { const list = buildList(0); return list; }",
    mutate="""
    (list, k) => {
        for (let i = 0; i < 100; i++)
            list.appendChild(makeListItem(k * 100 + i, false));
    }""")

TESTS["render/inner-html-replace-list.html"] = pipeline(
    "replace a 200-item list's innerHTML, then force layout (the jQuery TodoMVC pattern)", 10,
    setup="() => buildList(200)",
    mutate="""
    (list, k) => {
        list.innerHTML = listHTML(200, k % 200);
    }""")

TESTS["render/layout-thrash.html"] = pipeline(
    "interleaved class writes and offsetHeight reads (25 write+read pairs per cycle)", 4,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        for (let i = 0; i < 25; i++) {
            list.children[(k * 25 + i) % 500].classList.toggle("hidden-item");
            forceLayout();
        }
    }""")

TESTS["render/get-bounding-client-rect.html"] = micro(
    "getBoundingClientRect over a settled 200-item list", 2000,
    setup="""
    () => {
        const list = buildList(200);
        forceLayout();
        return list;
    }""",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += list.children[i % 200].getBoundingClientRect().top;
        if (acc === 0) throw new Error("bad result");
    }""")

TESTS["render/offset-top-read.html"] = micro(
    "offsetTop over a settled 200-item list", 5000,
    setup="""
    () => {
        const list = buildList(200);
        forceLayout();
        return list;
    }""",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += list.children[i % 200].offsetTop;
        if (acc === 0) throw new Error("bad result");
    }""")

TESTS["render/computed-style-read.html"] = micro(
    "getComputedStyle().display over a settled 200-item list", 2000,
    setup="""
    () => {
        const list = buildList(200);
        forceLayout();
        return list;
    }""",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += getComputedStyle(list.children[i % 200]).display.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["render/computed-style-width-read.html"] = micro(
    "getComputedStyle().width (layout-dependent) over a settled 200-item list", 1000,
    setup="""
    () => {
        const list = buildList(200);
        forceLayout();
        return list;
    }""",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += getComputedStyle(list.children[i % 200]).width.length;
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# js/ — pure JavaScript, LibJS vs V8-jitless. No DOM.
# ======================================================================================

TESTS["js/string-concat.html"] = micro(
    "string += in a loop", 100000,
    run="""
    (ctx, iters) => {
        let out = "";
        for (let i = 0; i < iters; i++)
            out += "x";
        if (out.length !== iters) throw new Error("bad result");
    }""")

TESTS["js/string-number-concat.html"] = micro(
    "building small strings from numbers", 100000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ("item " + (i & 1023)).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/template-literal.html"] = micro(
    "template literal interpolation", 100000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += `value ${i & 255} of ${iters}`.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/string-slice.html"] = micro(
    "slice of a 1000-char string", 100000,
    setup="() => \"abcdefghij\".repeat(100)",
    run="""
    (s, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += s.slice(i & 255, (i & 255) + 100).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/string-index-of.html"] = micro(
    "indexOf near the end of a 1000-char string", 20000,
    setup="() => \"abcdefghij\".repeat(100) + \"needle\"",
    run="""
    (s, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += s.indexOf("needle");
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/string-split-join.html"] = micro(
    "split on comma then join, 100 fields", 5000,
    setup="() => Array.from({ length: 100 }, (unused, i) => \"field\" + i).join(\",\")",
    run="""
    (s, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += s.split(",").join(";").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/string-to-lower.html"] = micro(
    "toLowerCase of a mixed-case 100-char string", 50000,
    setup="() => \"AbCdEfGhIj\".repeat(10)",
    run="""
    (s, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += s.toLowerCase().length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/regex-test.html"] = micro(
    "RegExp.test with a class-like pattern", 50000,
    setup="() => /^todo-(item|list)-[0-9]+$/",
    run="""
    (re, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += re.test(i & 1 ? "todo-item-42" : "not-a-match") ? 1 : 0;
        if (acc !== iters >> 1) throw new Error("bad result");
    }""")

TESTS["js/regex-replace.html"] = micro(
    "global replace over a 1000-char string", 10000,
    setup="() => \"the quick brown fox \".repeat(50)",
    run="""
    (s, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += s.replace(/quick/g, "slow").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/json-parse.html"] = micro(
    "JSON.parse of a 100-item array of objects", 2000,
    setup="""
    () => JSON.stringify(Array.from({ length: 100 }, (unused, i) => ({ id: i, title: "todo " + i, completed: !(i & 1) })))""",
    run="""
    (s, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += JSON.parse(s).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/json-stringify.html"] = micro(
    "JSON.stringify of a 100-item array of objects", 2000,
    setup="""
    () => Array.from({ length: 100 }, (unused, i) => ({ id: i, title: "todo " + i, completed: !(i & 1) }))""",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += JSON.stringify(data).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/array-push.html"] = micro(
    "push into a fresh array, 1000 elements per round", 2000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const a = [];
            for (let j = 0; j < 1000; j++)
                a.push(j);
            acc += a.length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/array-map-filter-reduce.html"] = micro(
    "map + filter + reduce chain over 100 elements", 5000,
    setup="() => Array.from({ length: 100 }, (unused, i) => i)",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += data.map((x) => x * 2).filter((x) => x & 2).reduce((a, b) => a + b, 0);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/array-sort-numbers.html"] = micro(
    "sort of a 100-number array with a comparator", 2000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const a = Array.from({ length: 100 }, (unused, j) => (j * 7919 + i) % 1000);
            a.sort((x, y) => x - y);
            acc += a[0];
        }
        if (acc < 0) throw new Error("bad result");
    }""")

TESTS["js/array-spread.html"] = micro(
    "spread of a 10-element array into a literal", 50000,
    setup="() => [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += [...data, i].length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/for-of-iteration.html"] = micro(
    "for-of over a 1000-element array", 5000,
    setup="() => Array.from({ length: 1000 }, (unused, i) => i)",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            for (const value of data)
                acc += value;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/map-ops.html"] = micro(
    "Map set/get/has over a cycling key space", 20000,
    setup="() => new Map()",
    run="""
    (map, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const key = "k" + (i & 255);
            map.set(key, i);
            acc += map.get(key) + (map.has(key) ? 1 : 0);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/set-ops.html"] = micro(
    "Set add/has/delete over a cycling key space", 20000,
    setup="() => new Set()",
    run="""
    (set, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const key = i & 255;
            set.add(key);
            acc += set.has(key) ? 1 : 0;
            if (i & 1)
                set.delete(key);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/object-literal.html"] = micro(
    "object literal creation with 5 properties", 100000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const o = { id: i, title: "t", completed: false, priority: i & 3, tags: null };
            acc += o.id;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/object-spread.html"] = micro(
    "object spread copying 5 properties plus one override", 50000,
    setup="() => ({ id: 1, title: \"t\", completed: false, priority: 2, tags: null })",
    run="""
    (base, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const o = { ...base, completed: !!(i & 1) };
            acc += o.id;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/object-keys-entries.html"] = micro(
    "Object.keys + Object.entries of a 10-property object", 20000,
    setup="""
    () => Object.fromEntries(Array.from({ length: 10 }, (unused, i) => ["key" + i, i]))""",
    run="""
    (obj, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += Object.keys(obj).length + Object.entries(obj).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/closure-calls.html"] = micro(
    "creating and calling a closure over a local", 100000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const add = (x) => x + i;
            acc += add(1);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/class-instantiation.html"] = micro(
    "new of a small class with a constructor", 100000,
    setup="""
    () => class Todo {
        constructor(id, title) {
            this.id = id;
            this.title = title;
            this.completed = false;
        }
    }""",
    run="""
    (Todo, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += new Todo(i, "t").id;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/prototype-method-call.html"] = micro(
    "calling a prototype method through a 2-level chain", 100000,
    setup="""
    () => {
        class Base { value() { return 1; } }
        class Derived extends Base {}
        return new Derived();
    }""",
    run="""
    (obj, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += obj.value();
        if (acc !== iters) throw new Error("bad result");
    }""")

TESTS["js/getter-setter.html"] = micro(
    "accessor property read+write", 100000,
    setup="""
    () => ({
        _x: 0,
        get x() { return this._x; },
        set x(v) { this._x = v; },
    })""",
    run="""
    (obj, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            obj.x = i;
            acc += obj.x & 1;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/promise-chain.html"] = micro(
    "await through a 10-link resolved-promise chain, 100 chains per iteration", 1,
    run="""
    async (ctx) => {
        let acc = 0;
        for (let c = 0; c < 100; c++) {
            let p = Promise.resolve(0);
            for (let i = 0; i < 10; i++)
                p = p.then((v) => v + 1);
            acc += await p;
        }
        if (acc !== 1000) throw new Error("bad result");
    }""")

TESTS["js/try-catch-throw.html"] = micro(
    "throw + catch of an Error", 20000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            try {
                if (i >= 0)
                    throw new Error("expected");
            } catch (e) {
                acc++;
            }
        }
        if (acc !== iters) throw new Error("bad result");
    }""")

# ======================================================================================
# canvas/ — 2D canvas primitives, the chartjs suite's diet.
# ======================================================================================

TESTS["canvas/fill-style-set.html"] = micro(
    "fillStyle assignment from rgba() and hex strings", 20000,
    setup="() => canvas2d()",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.fillStyle = i & 1 ? "rgba(54, 162, 235, 0.5)" : "#abcdef";
    }""")

TESTS["canvas/stroke-style-set.html"] = micro(
    "strokeStyle assignment from rgb() strings", 20000,
    setup="() => canvas2d()",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.strokeStyle = i & 1 ? "rgb(255, 99, 132)" : "rgb(54, 162, 235)";
    }""")

TESTS["canvas/arc-fill.html"] = micro(
    "beginPath + arc + fill scatter points", 5000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillStyle = "rgba(54, 162, 235, 0.5)";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.beginPath();
            ctx.arc((i * 37) % 800, (i * 91) % 600, 3, 0, 2 * Math.PI);
            ctx.fill();
        }
    }""")

TESTS["canvas/arc-stroke-fill.html"] = micro(
    "arc with both fill and stroke, like chartjs points", 5000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillStyle = "rgba(255, 99, 132, 0.5)";
        ctx.strokeStyle = "rgb(255, 99, 132)";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.beginPath();
            ctx.arc((i * 53) % 800, (i * 71) % 600, 3, 0, 2 * Math.PI);
            ctx.fill();
            ctx.stroke();
        }
    }""")

TESTS["canvas/fill-rect.html"] = micro(
    "small fillRect calls", 20000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillStyle = "#336699";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.fillRect((i * 37) % 800, (i * 91) % 600, 4, 4);
    }""")

TESTS["canvas/line-path.html"] = micro(
    "one polyline of many lineTo segments, stroked once", 5,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.strokeStyle = "#993366";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let r = 0; r < iters; r++) {
            ctx.beginPath();
            for (let i = 0; i < 5000; i++)
                ctx.lineTo((i * 17) % 800, (i * 43) % 600);
            ctx.stroke();
        }
    }""")

TESTS["canvas/save-restore.html"] = micro(
    "save + translate + restore cycle", 20000,
    setup="() => canvas2d()",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.save();
            ctx.translate(1, 1);
            ctx.restore();
        }
    }""")

TESTS["canvas/fill-text.html"] = micro(
    "fillText of short labels", 2000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.font = "12px sans-serif";
        ctx.fillStyle = "#222222";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.fillText("label " + (i & 31), (i * 61) % 700, (i * 37) % 580);
    }""")

TESTS["canvas/measure-text.html"] = micro(
    "measureText of short labels", 2000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.font = "12px sans-serif";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ctx.measureText("label " + (i & 31)).width;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["canvas/clear-rect.html"] = micro(
    "full-canvas clearRect", 2000,
    setup="() => canvas2d()",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.clearRect(0, 0, 800, 600);
    }""")

TESTS["canvas/get-image-data.html"] = micro(
    "getImageData of a 10x10 region", 500,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillRect(0, 0, 100, 100);
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ctx.getImageData(0, 0, 10, 10).data.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["canvas/put-image-data.html"] = micro(
    "putImageData of a 100x100 block", 1000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillStyle = "#446688";
        ctx.fillRect(0, 0, 100, 100);
        return { ctx, block: ctx.getImageData(0, 0, 100, 100) };
    }""",
    run="""
    (c, iters) => {
        for (let i = 0; i < iters; i++)
            c.ctx.putImageData(c.block, (i * 13) % 200, (i * 7) % 200);
    }""")

TESTS["canvas/gradient-fill.html"] = micro(
    "createLinearGradient + fillRect", 2000,
    setup="() => canvas2d()",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            const gradient = ctx.createLinearGradient(0, 0, 100, 100);
            gradient.addColorStop(0, "#ff0000");
            gradient.addColorStop(1, "#0000ff");
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, 100, 100);
        }
    }""")

# ======================================================================================
# svg/ — SVG DOM and layout, the Stockcharts / observable-plot diet.
# ======================================================================================

TESTS["svg/path-d-parse.html"] = micro(
    "setAttribute('d') with a 30-point path on a detached path element", 2000,
    setup="() => document.createElementNS(SVG_NS, \"path\")",
    run="""
    (path, iters) => {
        for (let i = 0; i < iters; i++)
            path.setAttribute("d", wigglyPathData(i, 30));
    }""")

TESTS["svg/path-d-attached.html"] = pipeline(
    "rewrite the 'd' of all 100 attached paths, then force layout (the zoom pattern)", 10,
    setup="() => makeSVG(100)",
    mutate="""
    (svg, k) => {
        const paths = svg.children;
        for (let i = 0; i < paths.length; i++)
            paths[i].setAttribute("d", wigglyPathData(k * 100 + i, 30));
    }""")

TESTS["svg/transform-attribute.html"] = pipeline(
    "rewrite transform on all 100 attached paths, then force layout (the pan pattern)", 20,
    setup="() => makeSVG(100)",
    mutate="""
    (svg, k) => {
        const paths = svg.children;
        for (let i = 0; i < paths.length; i++)
            paths[i].setAttribute("transform", "translate(" + (k & 15) + ", " + (i & 7) + ")");
    }""")

TESTS["svg/create-path-elements.html"] = pipeline(
    "create and append 100 fresh paths, then force layout (the render pattern)", 5,
    setup="() => makeSVG(0)",
    mutate="""
    (svg, k) => {
        svg.textContent = "";
        for (let i = 0; i < 100; i++) {
            const path = document.createElementNS(SVG_NS, "path");
            path.setAttribute("d", wigglyPathData(k * 100 + i, 30));
            path.setAttribute("stroke", "steelblue");
            path.setAttribute("fill", "none");
            svg.appendChild(path);
        }
    }""")

TESTS["svg/class-toggle.html"] = pipeline(
    "toggle a class on one of 100 attached paths, then force layout", 50,
    setup="""
    () => {
        const style = document.createElement("style");
        style.textContent = ".highlight { stroke: crimson; stroke-width: 3px; }";
        document.head.appendChild(style);
        return makeSVG(100);
    }""",
    mutate="""
    (svg, k) => {
        svg.children[(k * 7) % 100].classList.toggle("highlight");
    }""")

TESTS["svg/text-content.html"] = pipeline(
    "rewrite 50 <text> labels, then force layout (the axis-label pattern)", 10,
    setup="""
    () => {
        const svg = makeSVG(0);
        for (let i = 0; i < 50; i++) {
            const text = document.createElementNS(SVG_NS, "text");
            text.setAttribute("x", String(i * 12));
            text.setAttribute("y", "150");
            text.textContent = "0";
            svg.appendChild(text);
        }
        return svg;
    }""",
    mutate="""
    (svg, k) => {
        const labels = svg.children;
        for (let i = 0; i < labels.length; i++)
            labels[i].textContent = String((k * 50 + i) % 1000);
    }""")

TESTS["svg/get-bbox.html"] = micro(
    "getBBox of paths in a settled 100-path SVG", 2000,
    setup="""
    () => {
        const svg = makeSVG(100);
        forceLayout();
        return svg;
    }""",
    run="""
    (svg, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += svg.children[i % 100].getBBox().width;
        if (acc < 0) throw new Error("bad result");
    }""")

TESTS["svg/view-box-change.html"] = pipeline(
    "alternate the viewBox of a 100-path SVG, then force layout (the zoom-extent pattern)", 10,
    setup="() => makeSVG(100)",
    mutate="""
    (svg, k) => {
        svg.setAttribute("viewBox", k & 1 ? "0 0 300 150" : "0 0 600 300");
    }""")

# ======================================================================================
# parse/ — HTML parsing and serialization.
# ======================================================================================

TESTS["parse/inner-html-fragment.html"] = micro(
    "innerHTML of one 5-element list item on a detached div", 5000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.innerHTML = '<li class="x"><div class="view"><input class="toggle" type="checkbox"><label>hello world ' + (i & 7) + '</label><button class="destroy"></button></div></li>';
    }""")

TESTS["parse/inner-html-1kb.html"] = micro(
    "innerHTML of a ~1KB 10-item list on a detached div", 2000,
    setup="() => ({ el: document.createElement(\"div\"), markup: \"<ul>\" + listHTML(10) + \"</ul>\" })",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.el.innerHTML = ctx.markup;
    }""")

TESTS["parse/inner-html-10kb.html"] = micro(
    "innerHTML of a ~15KB 100-item list on a detached div", 200,
    setup="() => ({ el: document.createElement(\"div\"), markup: \"<ul>\" + listHTML(100) + \"</ul>\" })",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.el.innerHTML = ctx.markup;
    }""")

TESTS["parse/inner-html-table.html"] = micro(
    "innerHTML of a 50-row table on a detached div", 500,
    setup="""
    () => {
        let rows = "";
        for (let i = 0; i < 50; i++)
            rows += "<tr><td>" + i + "</td><td>name " + i + "</td><td><b>bold</b></td></tr>";
        return { el: document.createElement("div"), markup: "<table><tbody>" + rows + "</tbody></table>" };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.el.innerHTML = ctx.markup;
    }""")

TESTS["parse/dom-parser.html"] = micro(
    "DOMParser.parseFromString of a ~15KB document", 200,
    setup="() => \"<!DOCTYPE html><html><body><ul>\" + listHTML(100) + \"</ul></body></html>\"",
    run="""
    (markup, iters) => {
        const parser = new DOMParser();
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += parser.parseFromString(markup, "text/html").body.children.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["parse/outer-html-serialize.html"] = micro(
    "outerHTML serialization of a 100-item list", 500,
    setup="""
    () => {
        const el = document.createElement("div");
        el.innerHTML = "<ul>" + listHTML(100) + "</ul>";
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += el.outerHTML.length;
        if (!acc) throw new Error("bad result");
    }""")


# ======================================================================================
# shadow/ — custom elements and shadow DOM, the WebComponents and Lit diet.
# ======================================================================================

TESTS["shadow/attach-shadow.html"] = micro(
    "attachShadow + populate a small shadow tree", 2000,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            const host = document.createElement("div");
            const shadow = host.attachShadow({ mode: "open" });
            shadow.innerHTML = "<style>span { color: rebeccapurple; }</style><span>hi</span>";
        }
    }""")

TESTS["shadow/create-defined-element.html"] = micro(
    "createElement of a defined custom element (constructor runs)", 20000,
    setup="""
    () => {
        if (!customElements.get("x-item")) {
            customElements.define("x-item", class extends HTMLElement {
                constructor() {
                    super();
                    this.todo = null;
                }
            });
        }
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            document.createElement("x-item");
    }""")

TESTS["shadow/define-and-upgrade.html"] = micro(
    "define() upgrading 200 existing elements, unique tag each round", 20,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            window.__upgradeCounter = (window.__upgradeCounter || 0) + 1;
            const tag = "x-up-" + window.__upgradeCounter;
            sandbox().textContent = "";
            for (let j = 0; j < 200; j++)
                sandbox().appendChild(document.createElement(tag));
            customElements.define(tag, class extends HTMLElement {
                connectedCallback() { this.upgraded = true; }
            });
        }
    }""")

TESTS["shadow/connected-callback.html"] = micro(
    "append + remove of a custom element with connected/disconnected callbacks", 5000,
    setup="""
    () => {
        if (!customElements.get("x-conn")) {
            customElements.define("x-conn", class extends HTMLElement {
                connectedCallback() { this.on = true; }
                disconnectedCallback() { this.on = false; }
            });
        }
        sandbox().textContent = "";
        return document.createElement("x-conn");
    }""",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++) {
            sandbox().appendChild(el);
            el.remove();
        }
    }""")

TESTS["shadow/attribute-changed-callback.html"] = micro(
    "setAttribute on an observed attribute of a custom element", 20000,
    setup="""
    () => {
        if (!customElements.get("x-attr")) {
            customElements.define("x-attr", class extends HTMLElement {
                static get observedAttributes() { return ["data-x"]; }
                attributeChangedCallback(name, oldValue, newValue) { this.last = newValue; }
            });
        }
        return document.createElement("x-attr");
    }""",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.setAttribute("data-x", "v" + (i & 7));
    }""")

TESTS["shadow/slot-reassignment.html"] = micro(
    "append + remove a light-DOM child of a host with a <slot>", 5000,
    setup="""
    () => {
        sandbox().textContent = "";
        const host = document.createElement("div");
        host.attachShadow({ mode: "open" }).innerHTML = "<div class=\\"wrap\\"><slot></slot></div>";
        sandbox().appendChild(host);
        return { host, child: document.createElement("span") };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.host.appendChild(ctx.child);
            ctx.child.remove();
        }
    }""")

TESTS["shadow/host-style-toggle.html"] = pipeline(
    "toggle a class on a shadow host with :host(.on) styling, then force layout", 30,
    setup="""
    () => {
        sandbox().textContent = "";
        const hosts = [];
        for (let i = 0; i < 100; i++) {
            const host = document.createElement("div");
            const shadow = host.attachShadow({ mode: "open" });
            shadow.innerHTML = "<style>:host { display: block; } :host(.on) span { color: crimson; font-weight: bold; }</style><span>item " + i + "</span>";
            sandbox().appendChild(host);
            hosts.push(host);
        }
        return hosts;
    }""",
    mutate="""
    (hosts, k) => {
        hosts[(k * 7) % 100].classList.toggle("on");
    }""")

TESTS["shadow/composed-event.html"] = micro(
    "composed bubbling event dispatched from inside a shadow tree", 20000,
    setup="""
    () => {
        sandbox().textContent = "";
        const host = document.createElement("div");
        const shadow = host.attachShadow({ mode: "open" });
        const inner = document.createElement("button");
        shadow.appendChild(inner);
        sandbox().appendChild(host);
        let count = 0;
        host.addEventListener("x-ev", () => count++);
        return inner;
    }""",
    run="""
    (inner, iters) => {
        for (let i = 0; i < iters; i++)
            inner.dispatchEvent(new CustomEvent("x-ev", { bubbles: true, composed: true }));
    }""")

TESTS["shadow/query-in-shadow.html"] = micro(
    "querySelector inside a 100-element shadow root", 5000,
    setup="""
    () => {
        sandbox().textContent = "";
        const host = document.createElement("div");
        const shadow = host.attachShadow({ mode: "open" });
        let markup = "";
        for (let i = 0; i < 100; i++)
            markup += "<div class=\\"row r" + (i % 10) + "\\">row " + i + "</div>";
        shadow.innerHTML = markup;
        shadow.lastElementChild.classList.add("needle");
        sandbox().appendChild(host);
        return shadow;
    }""",
    run="""
    (shadow, iters) => {
        let found = 0;
        for (let i = 0; i < iters; i++)
            found += shadow.querySelector(".needle") ? 1 : 0;
        if (found !== iters) throw new Error("bad result");
    }""")

TESTS["shadow/clone-host-tree.html"] = micro(
    "cloneNode(true) of a tree with 100 custom-element hosts", 200,
    setup="""
    () => {
        if (!customElements.get("x-clone")) {
            customElements.define("x-clone", class extends HTMLElement {
                constructor() { super(); this.data = null; }
            });
        }
        const root = document.createElement("div");
        for (let i = 0; i < 100; i++) {
            const host = document.createElement("x-clone");
            host.textContent = "item " + i;
            root.appendChild(host);
        }
        return root;
    }""",
    run="""
    (root, iters) => {
        for (let i = 0; i < iters; i++)
            root.cloneNode(true);
    }""")

# ======================================================================================
# events/ — dispatch shapes beyond the basics in dom/.
# ======================================================================================

TESTS["events/deep-bubble.html"] = micro(
    "bubbling custom event through a 30-deep ancestor chain", 5000,
    setup="""
    () => {
        sandbox().textContent = "";
        let parent = sandbox();
        for (let i = 0; i < 30; i++) {
            const div = document.createElement("div");
            parent.appendChild(div);
            parent = div;
        }
        let count = 0;
        sandbox().addEventListener("x-deep", () => count++);
        return parent;
    }""",
    run="""
    (leaf, iters) => {
        for (let i = 0; i < iters; i++)
            leaf.dispatchEvent(new CustomEvent("x-deep", { bubbles: true }));
    }""")

TESTS["events/many-listeners.html"] = micro(
    "dispatch to a target with 10 listeners for the event", 20000,
    setup="""
    () => {
        const el = document.createElement("div");
        for (let i = 0; i < 10; i++)
            el.addEventListener("x-ev", () => {});
        return el;
    }""",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++)
            el.dispatchEvent(new CustomEvent("x-ev"));
    }""")

TESTS["events/capture-and-bubble.html"] = micro(
    "capture listener at root plus bubble listener at leaf, 10-deep chain", 10000,
    setup="""
    () => {
        sandbox().textContent = "";
        let parent = sandbox();
        for (let i = 0; i < 10; i++) {
            const div = document.createElement("div");
            parent.appendChild(div);
            parent = div;
        }
        let count = 0;
        sandbox().addEventListener("x-ev", () => count++, { capture: true });
        parent.addEventListener("x-ev", () => count++);
        return parent;
    }""",
    run="""
    (leaf, iters) => {
        for (let i = 0; i < iters; i++)
            leaf.dispatchEvent(new CustomEvent("x-ev", { bubbles: true }));
    }""")

TESTS["events/stop-propagation.html"] = micro(
    "stopPropagation halfway up a 10-deep chain", 20000,
    setup="""
    () => {
        sandbox().textContent = "";
        let parent = sandbox();
        let middle = null;
        for (let i = 0; i < 10; i++) {
            const div = document.createElement("div");
            parent.appendChild(div);
            parent = div;
            if (i === 5)
                middle = div;
        }
        middle.addEventListener("x-ev", (event) => event.stopPropagation());
        return parent;
    }""",
    run="""
    (leaf, iters) => {
        for (let i = 0; i < iters; i++)
            leaf.dispatchEvent(new CustomEvent("x-ev", { bubbles: true }));
    }""")

TESTS["events/mouse-event-constructor.html"] = micro(
    "new MouseEvent with an init dictionary", 50000,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            new MouseEvent("click", { bubbles: true, cancelable: true, clientX: i & 255, clientY: i & 127 });
    }""")

TESTS["events/keyboard-event-dispatch.html"] = micro(
    "keydown + keyup dispatch on an input, like the Speedometer3 driver typing", 10000,
    setup="""
    () => {
        sandbox().textContent = "";
        const input = document.createElement("input");
        sandbox().appendChild(input);
        let count = 0;
        input.addEventListener("keyup", () => count++);
        return input;
    }""",
    run="""
    (input, iters) => {
        for (let i = 0; i < iters; i++) {
            input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
            input.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
        }
    }""")

TESTS["events/input-change-events.html"] = micro(
    "value set + input + change event dispatch on a real input", 10000,
    setup="""
    () => {
        sandbox().textContent = "";
        const input = document.createElement("input");
        sandbox().appendChild(input);
        let count = 0;
        input.addEventListener("input", () => count++);
        input.addEventListener("change", () => count++);
        return input;
    }""",
    run="""
    (input, iters) => {
        for (let i = 0; i < iters; i++) {
            input.value = "text " + (i & 63);
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }""")

TESTS["events/delegated-handler.html"] = micro(
    "delegation: container click handler resolving event.target.closest('.destroy')", 5000,
    setup="""
    () => {
        const list = buildList(100);
        let count = 0;
        list.addEventListener("click", (event) => {
            if (event.target.closest(".destroy"))
                count++;
        });
        return list.querySelectorAll(".destroy");
    }""",
    run="""
    (buttons, iters) => {
        for (let i = 0; i < iters; i++)
            buttons[i % buttons.length].click();
    }""")

TESTS["events/focus-blur.html"] = micro(
    "focus() alternating between two inputs", 1000,
    setup="""
    () => {
        sandbox().textContent = "";
        const first = document.createElement("input");
        const second = document.createElement("input");
        sandbox().appendChild(first);
        sandbox().appendChild(second);
        return [first, second];
    }""",
    run="""
    (inputs, iters) => {
        for (let i = 0; i < iters; i++)
            inputs[i & 1].focus();
    }""")


# ======================================================================================
# style/ — stylesheet parsing, registration, selector matching and invalidation breadth.
# ======================================================================================

TESTS["style/insert-style-500-rules.html"] = micro(
    "append + remove a <style> with 500 class rules, forcing style each time", 10,
    setup="""
    () => {
        buildList(100);
        let css = "";
        for (let i = 0; i < 500; i++)
            css += ".generated-" + i + " { color: rgb(" + (i % 255) + ", 0, 0); padding-left: " + (i % 7) + "px; }\\n";
        return css;
    }""",
    run="""
    (css, iters) => {
        for (let i = 0; i < iters; i++) {
            const style = document.createElement("style");
            style.textContent = css;
            document.head.appendChild(style);
            forceLayout();
            style.remove();
            forceLayout();
        }
    }""")

TESTS["style/constructed-stylesheet.html"] = micro(
    "new CSSStyleSheet + replaceSync of 500 rules", 10,
    setup="""
    () => {
        let css = "";
        for (let i = 0; i < 500; i++)
            css += ".constructed-" + i + " { color: rgb(0, " + (i % 255) + ", 0); }\\n";
        return css;
    }""",
    run="""
    (css, iters) => {
        for (let i = 0; i < iters; i++) {
            const sheet = new CSSStyleSheet();
            sheet.replaceSync(css);
            if (sheet.cssRules.length !== 500) throw new Error("bad result");
        }
    }""")

TESTS["style/class-invalidation-breadth.html"] = pipeline(
    "toggle a container class that restyles all 500 descendants, then force layout", 10,
    setup="""
    () => {
        injectStyleOnce("breadth", ".flip li label { color: seagreen; letter-spacing: 1px; }");
        return buildList(500);
    }""",
    mutate="""
    (list, k) => {
        list.classList.toggle("flip");
    }""")

TESTS["style/has-selector-invalidation.html"] = pipeline(
    "toggle a class watched by a :has() rule, then force layout", 20,
    setup="""
    () => {
        injectStyleOnce("has-rule", ".todo-list:has(.selected) { background: #fffbe6; } .todo-list:has(.selected) li { border-left: 2px solid gold; }");
        return buildList(200);
    }""",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 200].classList.toggle("selected");
    }""")

TESTS["style/checked-sibling-invalidation.html"] = pipeline(
    "toggle checkbox checkedness driving a :checked ~ sibling rule, then force layout", 30,
    setup="""
    () => {
        injectStyleOnce("checked-rule", ".toggle:checked ~ label { text-decoration: line-through; color: #d9d9d9; }");
        return buildList(200);
    }""",
    mutate="""
    (list, k) => {
        const toggle = list.children[(k * 37) % 200].querySelector(".toggle");
        toggle.checked = !toggle.checked;
    }""")

TESTS["style/attribute-selector-invalidation.html"] = pipeline(
    "toggle an attribute watched by an attribute selector, then force layout", 30,
    setup="""
    () => {
        injectStyleOnce("attr-rule", "li[data-state=\\"on\\"] { background: #eef; } li[data-state=\\"on\\"] label { font-style: italic; }");
        return buildList(200);
    }""",
    mutate="""
    (list, k) => {
        const item = list.children[(k * 37) % 200];
        item.setAttribute("data-state", item.getAttribute("data-state") === "on" ? "off" : "on");
    }""")

TESTS["style/css-variable-root-change.html"] = pipeline(
    "change a custom property on the container feeding 300 var() consumers, then force layout", 10,
    setup="""
    () => {
        injectStyleOnce("var-rule", ".todo-list { --accent: rgb(10, 20, 30); } .todo-list li label { color: var(--accent); }");
        return buildList(300);
    }""",
    mutate="""
    (list, k) => {
        list.style.setProperty("--accent", k & 1 ? "rgb(200, 30, 30)" : "rgb(30, 30, 200)");
    }""")

TESTS["style/css-variable-read.html"] = micro(
    "getComputedStyle().getPropertyValue of a custom property", 5000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.style.setProperty("--x", "42px");
        sandbox().appendChild(el);
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += getComputedStyle(el).getPropertyValue("--x").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["style/match-media.html"] = micro(
    "matchMedia evaluation with a varying width query", 5000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += window.matchMedia("(max-width: " + (2000 + (i & 255)) + "px)").matches ? 1 : 0;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["style/insert-delete-rule.html"] = micro(
    "CSSOM insertRule + deleteRule on a live sheet", 2000,
    setup="""
    () => {
        const style = document.createElement("style");
        style.textContent = ".base-rule { color: black; }";
        document.head.appendChild(style);
        return style.sheet;
    }""",
    run="""
    (sheet, iters) => {
        for (let i = 0; i < iters; i++) {
            sheet.insertRule(".dynamic-rule { color: rgb(" + (i % 255) + ", 0, 0); }", 0);
            sheet.deleteRule(0);
        }
    }""")

TESTS["style/computed-transform-read.html"] = micro(
    "getComputedStyle().transform of a transformed element", 5000,
    setup="""
    () => {
        const el = document.createElement("div");
        el.style.transform = "translate(10px, 20px) scale(1.5)";
        sandbox().appendChild(el);
        return el;
    }""",
    run="""
    (el, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += getComputedStyle(el).transform.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["style/append-under-big-sheet.html"] = pipeline(
    "append + remove one item while a 2000-rule sheet is active, then force layout", 20,
    setup="""
    () => {
        let css = "";
        for (let i = 0; i < 2000; i++)
            css += ".bulk-" + i + " .inner { color: rgb(" + (i % 255) + ", 10, 10); }\\n";
        injectStyleOnce("big-sheet", css);
        return buildList(200);
    }""",
    mutate="""
    (list, k) => {
        if (k & 1)
            list.lastElementChild.remove();
        else
            list.appendChild(makeListItem(1000 + k, false));
    }""")

# ======================================================================================
# layout/ — layout modes beyond the flat block list in render/.
# ======================================================================================

TESTS["layout/flex-wrap-toggle-one.html"] = pipeline(
    "toggle one item's flex-basis class in a 200-item wrapping flex row, then force layout", 30,
    setup="() => makeFlexContainer(200)",
    mutate="""
    (container, k) => {
        container.children[(k * 37) % 200].classList.toggle("wide");
    }""")

TESTS["layout/flex-basis-change.html"] = pipeline(
    "change one item's inline flex-basis in a 200-item flex row, then force layout", 30,
    setup="() => makeFlexContainer(200)",
    mutate="""
    (container, k) => {
        container.children[(k * 37) % 200].style.flexBasis = (40 + (k & 31)) + "px";
    }""")

TESTS["layout/flex-append-item.html"] = pipeline(
    "append one item to a 200-item flex row, then force layout", 30,
    setup="() => makeFlexContainer(200)",
    mutate="""
    (container, k) => {
        const item = document.createElement("div");
        item.className = "flex-item";
        item.textContent = String(k % 10);
        container.appendChild(item);
    }""")

TESTS["layout/grid-place-change.html"] = pipeline(
    "change one item's grid-column in a 20x20 grid, then force layout", 30,
    setup="() => makeGrid(20, 400)",
    mutate="""
    (container, k) => {
        container.children[(k * 37) % 400].style.gridColumn = String(1 + (k % 20));
    }""")

TESTS["layout/grid-append-auto.html"] = pipeline(
    "append one auto-placed item to a 400-cell grid, then force layout", 30,
    setup="() => makeGrid(20, 400)",
    mutate="""
    (container, k) => {
        const item = document.createElement("div");
        item.className = "grid-item";
        item.textContent = String(k % 10);
        container.appendChild(item);
    }""")

TESTS["layout/table-cell-text.html"] = pipeline(
    "change one cell's text in a 200x5 table, then force layout", 30,
    setup="() => makeTable(200, 5)",
    mutate="""
    (table, k) => {
        const rows = table.tBodies[0].rows;
        rows[(k * 37) % 200].cells[k % 5].textContent = "edited " + k;
    }""")

TESTS["layout/table-append-row.html"] = pipeline(
    "append one row to a 200x5 table, then force layout", 30,
    setup="() => makeTable(200, 5)",
    mutate="""
    (table, k) => {
        const tr = document.createElement("tr");
        for (let c = 0; c < 5; c++) {
            const td = document.createElement("td");
            td.textContent = "new" + c;
            tr.appendChild(td);
        }
        table.tBodies[0].appendChild(tr);
    }""")

TESTS["layout/table-column-width.html"] = pipeline(
    "widen one cell, which re-sizes its whole table column, then force layout", 20,
    setup="() => makeTable(200, 5)",
    mutate="""
    (table, k) => {
        table.tBodies[0].rows[0].cells[2].style.width = k & 1 ? "150px" : "50px";
    }""")

TESTS["layout/abspos-move.html"] = pipeline(
    "move an absolutely positioned box over a 200-item list, then force layout", 50,
    setup="""
    () => {
        const list = buildList(200);
        const box = document.createElement("div");
        box.style.cssText = "position: absolute; width: 50px; height: 50px; background: tomato;";
        sandbox().appendChild(box);
        return box;
    }""",
    mutate="""
    (box, k) => {
        box.style.left = (k & 63) + "px";
        box.style.top = ((k * 7) & 63) + "px";
    }""")

TESTS["layout/abspos-many-siblings.html"] = pipeline(
    "move one of 200 absolutely positioned siblings, then force layout", 50,
    setup="""
    () => {
        sandbox().textContent = "";
        const container = document.createElement("div");
        container.style.cssText = "position: relative; height: 400px;";
        for (let i = 0; i < 200; i++) {
            const box = document.createElement("div");
            box.style.cssText = "position: absolute; width: 10px; height: 10px; background: #46a; left: " + (i % 40) * 15 + "px; top: " + Math.floor(i / 40) * 15 + "px;";
            container.appendChild(box);
        }
        sandbox().appendChild(container);
        return container;
    }""",
    mutate="""
    (container, k) => {
        container.children[(k * 37) % 200].style.left = ((k & 31) * 17) + "px";
    }""")

TESTS["layout/deep-nesting-text-change.html"] = pipeline(
    "change the innermost text of a 100-deep nested block tree, then force layout", 30,
    setup="""
    () => {
        sandbox().textContent = "";
        let parent = sandbox();
        for (let i = 0; i < 100; i++) {
            const div = document.createElement("div");
            div.style.paddingLeft = "1px";
            parent.appendChild(div);
            parent = div;
        }
        return parent;
    }""",
    mutate="""
    (innermost, k) => {
        innermost.textContent = "depth 100, edit " + k;
    }""")

TESTS["layout/paragraph-width-reflow.html"] = pipeline(
    "alternate the width of a 200-sentence paragraph, then force layout (full line rebuild)", 10,
    setup="() => makeParagraph(200)",
    mutate="""
    (p, k) => {
        p.style.width = k & 1 ? "500px" : "600px";
    }""")

TESTS["layout/paragraph-word-edit.html"] = pipeline(
    "replace the first word of a 200-sentence paragraph, then force layout", 20,
    setup="() => makeParagraph(200)",
    mutate="""
    (p, k) => {
        const text = p.firstChild;
        text.replaceData(0, 3, k & 1 ? "One" : "The");
    }""")

TESTS["layout/float-toggle.html"] = pipeline(
    "toggle float:left on one of 100 boxes with text, then force layout", 30,
    setup="""
    () => {
        sandbox().textContent = "";
        const container = document.createElement("div");
        container.style.width = "600px";
        for (let i = 0; i < 100; i++) {
            const box = document.createElement("div");
            box.textContent = "box " + i + " with some text inside it";
            box.style.width = "120px";
            container.appendChild(box);
        }
        sandbox().appendChild(container);
        return container;
    }""",
    mutate="""
    (container, k) => {
        const box = container.children[(k * 7) % 100];
        box.style.cssFloat = box.style.cssFloat === "left" ? "" : "left";
    }""")

TESTS["layout/relative-offset.html"] = pipeline(
    "change a position:relative item's left offset, then force layout", 50,
    setup="""
    () => {
        const list = buildList(200);
        const item = list.children[100];
        item.style.position = "relative";
        return item;
    }""",
    mutate="""
    (item, k) => {
        item.style.left = (k & 15) + "px";
    }""")


# ======================================================================================
# text/ — text shaping, fonts, and text-driven layout.
# ======================================================================================

TESTS["text/shape-unique-strings.html"] = pipeline(
    "set 20 labels to never-seen-before strings, then force layout (shaping cache miss)", 20,
    setup="() => buildList(100)",
    mutate="""
    (list, k) => {
        for (let i = 0; i < 20; i++)
            list.children[i].querySelector("label").textContent = uniqueString();
    }""")

TESTS["text/shape-repeated-strings.html"] = pipeline(
    "set 20 labels to one of two known strings, then force layout (shaping cache hit)", 20,
    setup="() => buildList(100)",
    mutate="""
    (list, k) => {
        const text = k & 1 ? "a well-known label text" : "the other label text";
        for (let i = 0; i < 20; i++)
            list.children[i].querySelector("label").textContent = text;
    }""")

TESTS["text/font-family-switch.html"] = pipeline(
    "switch the container's font-family, re-shaping 200 items, then force layout", 10,
    setup="() => buildList(200)",
    mutate="""
    (list, k) => {
        list.style.fontFamily = k & 1 ? "serif" : "sans-serif";
    }""")

TESTS["text/font-size-change.html"] = pipeline(
    "change the container's font-size, then force layout", 10,
    setup="() => buildList(200)",
    mutate="""
    (list, k) => {
        list.style.fontSize = k & 1 ? "18px" : "16px";
    }""")

TESTS["text/rtl-mixed-reflow.html"] = pipeline(
    "reflow a paragraph mixing Hebrew and Latin at alternating widths (bidi)", 10,
    setup="""
    () => {
        sandbox().textContent = "";
        const p = document.createElement("p");
        p.style.width = "600px";
        p.textContent = "The word \\u05e9\\u05dc\\u05d5\\u05dd means peace and \\u05ea\\u05d5\\u05d3\\u05d4 means thanks. ".repeat(50);
        sandbox().appendChild(p);
        return p;
    }""",
    mutate="""
    (p, k) => {
        p.style.width = k & 1 ? "500px" : "600px";
    }""")

TESTS["text/word-break-long-word.html"] = pipeline(
    "reflow an unbroken 5000-char word under word-break: break-all", 10,
    setup="""
    () => {
        sandbox().textContent = "";
        const p = document.createElement("p");
        p.style.cssText = "width: 600px; word-break: break-all;";
        p.textContent = "abcdefghij".repeat(500);
        sandbox().appendChild(p);
        return p;
    }""",
    mutate="""
    (p, k) => {
        p.style.width = k & 1 ? "500px" : "600px";
    }""")

TESTS["text/inner-text-read.html"] = micro(
    "innerText read of a 200-item list after a small mutation (forces layout per read)", 50,
    setup="() => buildList(200)",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            list.children[i % 200].classList.toggle("completed");
            acc += list.innerText.length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["text/range-client-rects.html"] = micro(
    "getClientRects of a Range spanning a settled paragraph", 1000,
    setup="""
    () => {
        const p = makeParagraph(50);
        forceLayout();
        return p;
    }""",
    run="""
    (p, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const range = document.createRange();
            range.setStart(p.firstChild, i % 100);
            range.setEnd(p.firstChild, (i % 100) + 200);
            acc += range.getClientRects().length;
        }
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# edit/ — contenteditable, Selection, and Range: the TipTap and CodeMirror diet.
# ======================================================================================

TESTS["edit/exec-insert-text.html"] = micro(
    "execCommand insertText into a focused contenteditable, 200 chars per round", 1,
    setup="""
    () => {
        sandbox().textContent = "";
        const editor = document.createElement("div");
        editor.contentEditable = "true";
        editor.style.cssText = "width: 600px; min-height: 40px;";
        sandbox().appendChild(editor);
        editor.focus();
        return editor;
    }""",
    run="""
    (editor, iters) => {
        for (let i = 0; i < 200; i++)
            document.execCommand("insertText", false, "x");
        if (!editor.textContent.includes("x")) throw new Error("bad result");
    }""")

TESTS["edit/exec-bold-toggle.html"] = micro(
    "select a word in contenteditable and toggle bold via execCommand, 50 toggles", 1,
    setup="""
    () => {
        sandbox().textContent = "";
        const editor = document.createElement("div");
        editor.contentEditable = "true";
        editor.textContent = "some words to make bold repeatedly";
        sandbox().appendChild(editor);
        editor.focus();
        return editor;
    }""",
    run="""
    (editor, iters) => {
        const selection = getSelection();
        for (let i = 0; i < 50; i++) {
            const range = document.createRange();
            range.selectNodeContents(editor);
            selection.removeAllRanges();
            selection.addRange(range);
            document.execCommand("bold");
            document.execCommand("bold");
            editor.normalize();
        }
    }""")

TESTS["edit/selection-collapse-extend.html"] = micro(
    "Selection collapse + extend across list items", 2000,
    setup="""
    () => {
        const list = buildList(100);
        return { list, selection: getSelection() };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            const label = ctx.list.children[i % 100].querySelector("label");
            ctx.selection.collapse(label.firstChild, 0);
            ctx.selection.extend(label.firstChild, 5);
        }
    }""")

TESTS["edit/range-surround.html"] = micro(
    "Range.surroundContents wrapping text in a span, then unwrapping", 300,
    setup="""
    () => {
        sandbox().textContent = "";
        const p = document.createElement("p");
        p.textContent = "wrap some of this text in a span repeatedly";
        sandbox().appendChild(p);
        return p;
    }""",
    run="""
    (p, iters) => {
        for (let i = 0; i < iters; i++) {
            const range = document.createRange();
            range.setStart(p.firstChild, 5);
            range.setEnd(p.firstChild, 9);
            const span = document.createElement("span");
            range.surroundContents(span);
            span.replaceWith(...span.childNodes);
            p.normalize();
        }
    }""")

TESTS["edit/range-extract-insert.html"] = micro(
    "Range.extractContents + insertNode putting the content back", 300,
    setup="""
    () => {
        sandbox().textContent = "";
        const p = document.createElement("p");
        p.textContent = "extract a slice of this sentence and put it back";
        sandbox().appendChild(p);
        return p;
    }""",
    run="""
    (p, iters) => {
        for (let i = 0; i < iters; i++) {
            const range = document.createRange();
            range.setStart(p.firstChild, 8);
            range.setEnd(p.firstChild, 15);
            const fragment = range.extractContents();
            range.insertNode(fragment);
            p.normalize();
        }
    }""")

TESTS["edit/range-set-points.html"] = micro(
    "createRange + setStart/setEnd across a 200-item list", 20000,
    setup="() => buildList(200)",
    run="""
    (list, iters) => {
        for (let i = 0; i < iters; i++) {
            const range = document.createRange();
            range.setStart(list.children[i % 200], 0);
            range.setEnd(list.children[(i + 5) % 200], 0);
        }
    }""")

TESTS["edit/selection-to-string.html"] = micro(
    "select a whole 200-item list and read Selection.toString()", 100,
    setup="""
    () => {
        const list = buildList(200);
        return { list, selection: getSelection() };
    }""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            ctx.selection.selectAllChildren(ctx.list);
            acc += ctx.selection.toString().length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["edit/textarea-value-events.html"] = micro(
    "textarea value append + input event, 200 keystrokes per round", 5,
    setup="""
    () => {
        sandbox().textContent = "";
        const textarea = document.createElement("textarea");
        sandbox().appendChild(textarea);
        let count = 0;
        textarea.addEventListener("input", () => count++);
        return textarea;
    }""",
    run="""
    (textarea, iters) => {
        for (let r = 0; r < iters; r++) {
            textarea.value = "";
            for (let i = 0; i < 200; i++) {
                textarea.value += "x";
                textarea.dispatchEvent(new Event("input", { bubbles: true }));
            }
        }
    }""")

# ======================================================================================
# observers/ — MutationObserver and friends.
# ======================================================================================

TESTS["observers/mutation-observer-records.html"] = micro(
    "200 observed attribute mutations + takeRecords", 100,
    setup="""
    () => {
        const list = buildList(200);
        const observer = new MutationObserver(() => {});
        observer.observe(list, { attributes: true, subtree: true });
        return { list, observer };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            for (let j = 0; j < 200; j++)
                ctx.list.children[j].setAttribute("data-v", String(i));
            if (ctx.observer.takeRecords().length !== 200) throw new Error("bad result");
        }
    }""")

TESTS["observers/mutation-observer-delivery.html"] = micro(
    "async delivery of a 200-mutation batch to a MutationObserver callback", 50,
    setup="""
    () => {
        const list = buildList(200);
        return list;
    }""",
    run="""
    async (list, iters) => {
        for (let i = 0; i < iters; i++) {
            let received = 0;
            const delivered = new Promise((resolve) => {
                const observer = new MutationObserver((records) => {
                    received = records.length;
                    observer.disconnect();
                    resolve();
                });
                observer.observe(list, { childList: true, attributes: true, subtree: true });
            });
            for (let j = 0; j < 200; j++)
                list.children[j].setAttribute("data-v", String(i));
            await delivered;
            if (received !== 200) throw new Error("bad result");
        }
    }""")

TESTS["observers/resize-observer-churn.html"] = micro(
    "ResizeObserver observe + unobserve of 100 elements", 100,
    setup="""
    () => {
        const list = buildList(100);
        return { list, observer: new ResizeObserver(() => {}) };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            for (let j = 0; j < 100; j++)
                ctx.observer.observe(ctx.list.children[j]);
            for (let j = 0; j < 100; j++)
                ctx.observer.unobserve(ctx.list.children[j]);
        }
    }""")

TESTS["observers/intersection-observer-churn.html"] = micro(
    "IntersectionObserver observe + unobserve of 100 elements", 100,
    setup="""
    () => {
        const list = buildList(100);
        return { list, observer: new IntersectionObserver(() => {}) };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            for (let j = 0; j < 100; j++)
                ctx.observer.observe(ctx.list.children[j]);
            for (let j = 0; j < 100; j++)
                ctx.observer.unobserve(ctx.list.children[j]);
        }
    }""")

TESTS["observers/abort-controller.html"] = micro(
    "AbortController + signal-bound listener + abort", 5000,
    setup="() => document.createElement(\"div\")",
    run="""
    (el, iters) => {
        for (let i = 0; i < iters; i++) {
            const controller = new AbortController();
            el.addEventListener("click", () => {}, { signal: controller.signal });
            controller.abort();
        }
    }""")

# ======================================================================================
# timers/ — task and microtask scheduling.
# ======================================================================================

# NOTE: a *chained* setTimeout test would measure the spec's 4ms nested-timeout clamp
# (which Chromium enforces), not scheduler speed. Schedule a flat batch instead.
TESTS["timers/set-timeout-batch.html"] = micro(
    "100 independent setTimeout(0) callbacks scheduled at once", 1,
    run="""
    () => new Promise((resolve) => {
        let remaining = 100;
        for (let i = 0; i < 100; i++) {
            setTimeout(() => {
                if (--remaining === 0)
                    resolve();
            }, 0);
        }
    })""")

TESTS["timers/queue-microtask-chain.html"] = micro(
    "chain of 1000 queueMicrotask hops", 1,
    run="""
    () => new Promise((resolve) => {
        let remaining = 1000;
        const hop = () => {
            if (--remaining === 0)
                resolve();
            else
                queueMicrotask(hop);
        };
        queueMicrotask(hop);
    })""")

TESTS["timers/message-channel-ping-pong.html"] = micro(
    "200 MessageChannel round trips", 1,
    run="""
    () => new Promise((resolve) => {
        const channel = new MessageChannel();
        let remaining = 200;
        channel.port1.onmessage = () => channel.port1.postMessage(0);
        channel.port2.onmessage = () => {
            if (--remaining === 0)
                resolve();
            else
                channel.port2.postMessage(0);
        };
        channel.port2.postMessage(0);
    })""")

TESTS["timers/promise-all-fanout.html"] = micro(
    "Promise.all over 1000 already-resolved promises", 1,
    run="""
    async () => {
        const promises = [];
        for (let i = 0; i < 1000; i++)
            promises.push(Promise.resolve(i));
        const results = await Promise.all(promises);
        if (results.length !== 1000) throw new Error("bad result");
    }""")

TESTS["timers/async-await-loop.html"] = micro(
    "await of an already-resolved promise in a 1000-iteration loop", 1,
    run="""
    async () => {
        let acc = 0;
        for (let i = 0; i < 1000; i++)
            acc += await Promise.resolve(1);
        if (acc !== 1000) throw new Error("bad result");
    }""")


# ======================================================================================
# js/ round two — Proxy-based reactivity (the Vue 3 diet) and more idioms.
# ======================================================================================

TESTS["js/proxy-get-set.html"] = micro(
    "property get + set through a Proxy with forwarding traps", 50000,
    setup="""
    () => new Proxy({ count: 0 }, {
        get(target, key) { return target[key]; },
        set(target, key, value) { target[key] = value; return true; },
    })""",
    run="""
    (proxy, iters) => {
        for (let i = 0; i < iters; i++)
            proxy.count = proxy.count + 1;
        if (proxy.count !== iters) throw new Error("bad result");
    }""")

TESTS["js/proxy-has-delete.html"] = micro(
    "in-operator and delete through Proxy traps", 50000,
    setup="""
    () => new Proxy({}, {
        has(target, key) { return key in target; },
        deleteProperty(target, key) { delete target[key]; return true; },
        set(target, key, value) { target[key] = value; return true; },
    })""",
    run="""
    (proxy, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            proxy.x = i;
            acc += "x" in proxy ? 1 : 0;
            delete proxy.x;
        }
        if (acc !== iters) throw new Error("bad result");
    }""")

TESTS["js/reflect-get.html"] = micro(
    "Reflect.get with a receiver", 100000,
    setup="() => ({ value: 42 })",
    run="""
    (obj, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += Reflect.get(obj, "value", obj);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/define-property-accessors.html"] = micro(
    "Object.defineProperty installing an accessor pair (Vue 2 reactivity)", 20000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const obj = {};
            let backing = i;
            Object.defineProperty(obj, "x", {
                get() { return backing; },
                set(v) { backing = v; },
            });
            acc += obj.x & 1;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/weakmap-dep-tracking.html"] = micro(
    "WeakMap get-or-create dependency tracking pattern", 50000,
    setup="""
    () => {
        const targets = Array.from({ length: 64 }, () => ({}));
        return { deps: new WeakMap(), targets };
    }""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const target = ctx.targets[i & 63];
            let dep = ctx.deps.get(target);
            if (!dep) {
                dep = new Set();
                ctx.deps.set(target, dep);
            }
            dep.add("effect" + (i & 7));
            acc += dep.size;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/generator-iteration.html"] = micro(
    "iterating a generator producing 100 values", 5000,
    setup="""
    () => function* counter() {
        for (let i = 0; i < 100; i++)
            yield i;
    }""",
    run="""
    (counter, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            for (const value of counter())
                acc += value;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/custom-iterator.html"] = micro(
    "for-of over an object with a hand-written Symbol.iterator", 5000,
    setup="""
    () => ({
        [Symbol.iterator]() {
            let i = 0;
            return { next: () => (i < 100 ? { value: i++, done: false } : { value: undefined, done: true }) };
        },
    })""",
    run="""
    (iterable, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            for (const value of iterable)
                acc += value;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/destructuring-defaults.html"] = micro(
    "object destructuring with defaults in a function signature", 100000,
    setup="""
    () => ({ fn: ({ id, title = "untitled", completed = false } = {}) => (completed ? 0 : id) })""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ctx.fn({ id: i });
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/spread-call-args.html"] = micro(
    "calling a function with spread arguments", 100000,
    setup="""
    () => ({ args: [1, 2, 3, 4, 5], fn: (a, b, c, d, e) => a + b + c + d + e })""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ctx.fn(...ctx.args);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/string-from-char-code.html"] = micro(
    "String.fromCharCode + charCodeAt round trip", 50000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += String.fromCharCode(65 + (i & 25)).charCodeAt(0);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/encode-uri-component.html"] = micro(
    "encodeURIComponent + decodeURIComponent of a query-ish string", 20000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += decodeURIComponent(encodeURIComponent("name=todo item " + (i & 63) + "&done=true")).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/parse-number.html"] = micro(
    "parseFloat + parseInt + Number() of numeric strings", 50000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += parseFloat("3.14159") + parseInt("42", 10) + Number("2.718" + (i & 7));
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/to-fixed.html"] = micro(
    "Number.prototype.toFixed of chart-ish values", 50000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ((i * 0.1234567) % 1000).toFixed(2).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/date-iso.html"] = micro(
    "Date construction from ms + toISOString + getTime", 20000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const date = new Date(1700000000000 + i * 60000);
            acc += date.toISOString().length + (date.getTime() & 1);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/math-trig.html"] = micro(
    "sin/cos/sqrt/atan2 loop, the chart-projection diet", 50000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += Math.sin(i * 0.01) + Math.cos(i * 0.02) + Math.sqrt(i & 1023) + Math.atan2(i & 63, 7);
        if (acc === 0) throw new Error("bad result");
    }""")

TESTS["js/float64-array.html"] = micro(
    "Float64Array fill + transform + reduce, 1000 elements", 2000,
    setup="() => new Float64Array(1000)",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            for (let j = 0; j < data.length; j++)
                data[j] = j * 0.5 + i;
            for (let j = 0; j < data.length; j++)
                acc += data[j];
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/structured-clone.html"] = micro(
    "structuredClone of a 100-item array of objects", 500,
    setup="""
    () => Array.from({ length: 100 }, (unused, i) => ({ id: i, title: "todo " + i, completed: !(i & 1) }))""",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += structuredClone(data).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/array-includes.html"] = micro(
    "Array includes + indexOf over a 100-element array", 20000,
    setup="() => Array.from({ length: 100 }, (unused, i) => \"item\" + i)",
    run="""
    (data, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += (data.includes("item99") ? 1 : 0) + data.indexOf("item" + (i & 63));
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# canvas/ round two.
# ======================================================================================

TESTS["canvas/path2d-fill.html"] = micro(
    "constructing a Path2D of 100 segments and filling it", 1000,
    setup="() => canvas2d()",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            const path = new Path2D();
            for (let j = 0; j < 100; j++)
                path.lineTo((j * 17 + i) % 800, (j * 43) % 600);
            path.closePath();
            ctx.fill(path);
        }
    }""")

TESTS["canvas/draw-image-canvas.html"] = micro(
    "drawImage from another canvas, unscaled", 2000,
    setup="""
    () => {
        const source = document.createElement("canvas");
        source.width = 100;
        source.height = 100;
        const sourceContext = source.getContext("2d");
        sourceContext.fillStyle = "#824";
        sourceContext.fillRect(0, 0, 100, 100);
        return { ctx: canvas2d(), source };
    }""",
    run="""
    (c, iters) => {
        for (let i = 0; i < iters; i++)
            c.ctx.drawImage(c.source, (i * 13) % 700, (i * 7) % 500);
    }""")

TESTS["canvas/draw-image-scaled.html"] = micro(
    "drawImage from another canvas with 2x scaling", 2000,
    setup="""
    () => {
        const source = document.createElement("canvas");
        source.width = 100;
        source.height = 100;
        const sourceContext = source.getContext("2d");
        sourceContext.fillStyle = "#284";
        sourceContext.fillRect(0, 0, 100, 100);
        return { ctx: canvas2d(), source };
    }""",
    run="""
    (c, iters) => {
        for (let i = 0; i < iters; i++)
            c.ctx.drawImage(c.source, (i * 13) % 500, (i * 7) % 300, 200, 200);
    }""")

TESTS["canvas/set-transform-draw.html"] = micro(
    "setTransform before each small fillRect", 10000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillStyle = "#357";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.setTransform(1, 0, 0, 1, i & 255, (i * 3) & 255);
            ctx.fillRect(0, 0, 4, 4);
        }
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    }""")

TESTS["canvas/global-alpha-composite.html"] = micro(
    "globalAlpha + globalCompositeOperation change before each draw", 10000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.fillStyle = "#573";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.globalAlpha = i & 1 ? 0.5 : 1.0;
            ctx.globalCompositeOperation = i & 1 ? "multiply" : "source-over";
            ctx.fillRect((i * 37) % 800, (i * 91) % 600, 4, 4);
        }
        ctx.globalAlpha = 1.0;
        ctx.globalCompositeOperation = "source-over";
    }""")

TESTS["canvas/bezier-path-stroke.html"] = micro(
    "bezierCurveTo path of 50 segments, stroked", 1000,
    setup="""
    () => {
        const ctx = canvas2d();
        ctx.strokeStyle = "#735";
        return ctx;
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            ctx.beginPath();
            ctx.moveTo(0, 300);
            for (let j = 0; j < 50; j++)
                ctx.bezierCurveTo(j * 16, (j * 31 + i) % 600, j * 16 + 5, (j * 17) % 600, j * 16 + 10, 300);
            ctx.stroke();
        }
    }""")

TESTS["canvas/to-data-url.html"] = micro(
    "toDataURL of a 100x100 canvas", 50,
    setup="""
    () => {
        sandbox().textContent = "";
        const canvas = document.createElement("canvas");
        canvas.width = 100;
        canvas.height = 100;
        sandbox().appendChild(canvas);
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#123456";
        ctx.fillRect(0, 0, 100, 100);
        return canvas;
    }""",
    run="""
    (canvas, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += canvas.toDataURL().length;
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# svg/ round two.
# ======================================================================================

TESTS["svg/use-element.html"] = pipeline(
    "instantiate 100 <use> references to a defs symbol, then force layout", 10,
    setup="""
    () => {
        const svg = makeSVG(0);
        const defs = document.createElementNS(SVG_NS, "defs");
        const group = document.createElementNS(SVG_NS, "g");
        group.id = "shared-shape";
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", "M0,0L10,10L20,0Z");
        path.setAttribute("fill", "steelblue");
        group.appendChild(path);
        defs.appendChild(group);
        svg.appendChild(defs);
        return svg;
    }""",
    mutate="""
    (svg, k) => {
        while (svg.children.length > 1)
            svg.lastElementChild.remove();
        for (let i = 0; i < 100; i++) {
            const use = document.createElementNS(SVG_NS, "use");
            use.setAttribute("href", "#shared-shape");
            use.setAttribute("x", String((i % 20) * 30));
            use.setAttribute("y", String(Math.floor(i / 20) * 30));
            svg.appendChild(use);
        }
    }""")

TESTS["svg/gradient-shapes.html"] = pipeline(
    "100 rects filled by one linearGradient, gradient stop recolored, then force layout", 10,
    setup="""
    () => {
        const svg = makeSVG(0);
        const defs = document.createElementNS(SVG_NS, "defs");
        const gradient = document.createElementNS(SVG_NS, "linearGradient");
        gradient.id = "shared-gradient";
        const stop = document.createElementNS(SVG_NS, "stop");
        stop.setAttribute("offset", "0");
        stop.setAttribute("stop-color", "tomato");
        gradient.appendChild(stop);
        defs.appendChild(gradient);
        svg.appendChild(defs);
        for (let i = 0; i < 100; i++) {
            const rect = document.createElementNS(SVG_NS, "rect");
            rect.setAttribute("x", String((i % 20) * 30));
            rect.setAttribute("y", String(Math.floor(i / 20) * 30));
            rect.setAttribute("width", "25");
            rect.setAttribute("height", "25");
            rect.setAttribute("fill", "url(#shared-gradient)");
            svg.appendChild(rect);
        }
        return stop;
    }""",
    mutate="""
    (stop, k) => {
        stop.setAttribute("stop-color", k & 1 ? "steelblue" : "tomato");
    }""")

TESTS["svg/dasharray-change.html"] = pipeline(
    "change stroke-dasharray on all 100 paths, then force layout", 20,
    setup="() => makeSVG(100)",
    mutate="""
    (svg, k) => {
        const paths = svg.children;
        for (let i = 0; i < paths.length; i++)
            paths[i].setAttribute("stroke-dasharray", k & 1 ? "4 2" : "8 4");
    }""")

TESTS["svg/circle-attr-change.html"] = pipeline(
    "move 200 scatter circles via cx/cy attributes, then force layout (the Perf-Dashboard pattern)", 20,
    setup="""
    () => {
        const svg = makeSVG(0);
        for (let i = 0; i < 200; i++) {
            const circle = document.createElementNS(SVG_NS, "circle");
            circle.setAttribute("r", "3");
            circle.setAttribute("fill", "seagreen");
            svg.appendChild(circle);
        }
        return svg;
    }""",
    mutate="""
    (svg, k) => {
        const circles = svg.children;
        for (let i = 0; i < circles.length; i++) {
            circles[i].setAttribute("cx", String((i * 3 + k * 7) % 600));
            circles[i].setAttribute("cy", String((i * 7919 + k) % 300));
        }
    }""")

TESTS["svg/text-rotate-labels.html"] = pipeline(
    "rotate 50 axis labels via transform, then force layout", 10,
    setup="""
    () => {
        const svg = makeSVG(0);
        for (let i = 0; i < 50; i++) {
            const text = document.createElementNS(SVG_NS, "text");
            text.setAttribute("x", String(i * 12));
            text.setAttribute("y", "150");
            text.textContent = "lbl" + i;
            svg.appendChild(text);
        }
        return svg;
    }""",
    mutate="""
    (svg, k) => {
        const labels = svg.children;
        for (let i = 0; i < labels.length; i++)
            labels[i].setAttribute("transform", "rotate(" + (k & 1 ? -45 : -30) + " " + i * 12 + " 150)");
    }""")

TESTS["svg/path-total-length.html"] = micro(
    "getTotalLength + getPointAtLength of a 30-point path (the d3 measurement pattern)", 500,
    setup="""
    () => {
        const svg = makeSVG(1);
        const path = svg.querySelector("path");
        path.setAttribute("d", wigglyPathData(7, 30));
        forceLayout();
        return path;
    }""",
    run="""
    (path, iters) => {
        if (!path.getTotalLength())
            throw new Error("getTotalLength returned 0; unsupported here, so there is nothing meaningful to measure");
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const length = path.getTotalLength();
            acc += path.getPointAtLength(length * ((i & 15) / 16)).x;
        }
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# parse/ round two.
# ======================================================================================

TESTS["parse/insert-adjacent-html.html"] = micro(
    "insertAdjacentHTML beforeend of one item, growing then resetting a list", 2000,
    setup="() => ({ list: buildList(0), counter: 0 })",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            if (ctx.list.children.length > 200)
                ctx.list.textContent = "";
            ctx.list.insertAdjacentHTML("beforeend", listItemHTML(i, false));
        }
    }""")

TESTS["parse/contextual-fragment.html"] = micro(
    "Range.createContextualFragment of a list item", 2000,
    setup="""
    () => {
        const range = document.createRange();
        range.selectNodeContents(document.body);
        return range;
    }""",
    run="""
    (range, iters) => {
        for (let i = 0; i < iters; i++)
            range.createContextualFragment(listItemHTML(i, false));
    }""")

TESTS["parse/xml-dom-parser.html"] = micro(
    "DOMParser.parseFromString of a ~10KB XML document", 200,
    setup="""
    () => {
        let items = "";
        for (let i = 0; i < 100; i++)
            items += "<item id=\\"" + i + "\\"><title>todo " + i + "</title><completed>" + (i & 1 ? "yes" : "no") + "</completed></item>";
        return "<?xml version=\\"1.0\\"?><list>" + items + "</list>";
    }""",
    run="""
    (markup, iters) => {
        const parser = new DOMParser();
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += parser.parseFromString(markup, "application/xml").documentElement.children.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["parse/entity-heavy.html"] = micro(
    "innerHTML with many character entities and attributes", 300,
    setup="""
    () => {
        let markup = "";
        for (let i = 0; i < 20; i++)
            markup += "<p title=\\"caf&eacute; &amp; r&eacute;sum&eacute; " + i + "\\">&lt;tag&gt; &quot;quoted&quot; &copy; &mdash; &nbsp; text</p>";
        return { el: document.createElement("div"), markup };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            ctx.el.innerHTML = ctx.markup;
    }""")

# ======================================================================================
# frameworks/ — composite DOM patterns every framework's reconciler leans on.
# ======================================================================================

TESTS["frameworks/keyed-reorder.html"] = micro(
    "keyed list diff-apply: move 50 items to new positions via insertBefore", 150,
    setup="() => buildList(100)",
    run="""
    (list, iters) => {
        for (let i = 0; i < iters; i++) {
            for (let j = 0; j < 50; j++)
                list.insertBefore(list.children[(j * 13 + i) % 100], list.children[(j * 7) % 100]);
        }
    }""")

TESTS["frameworks/replace-children.html"] = micro(
    "replaceChildren swapping a 100-item list wholesale", 100,
    setup="""
    () => {
        const list = buildList(100);
        const spare = [];
        for (let i = 0; i < 100; i++)
            spare.push(makeListItem(1000 + i, false));
        return { list, spare, current: null };
    }""",
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++) {
            const previous = Array.from(ctx.list.children);
            ctx.list.replaceChildren(...ctx.spare);
            ctx.spare = previous;
        }
    }""")

TESTS["frameworks/fragment-batch-insert.html"] = micro(
    "DocumentFragment built with 100 items, appended in one shot", 100,
    setup="() => buildList(0)",
    run="""
    (list, iters) => {
        for (let i = 0; i < iters; i++) {
            list.textContent = "";
            const fragment = document.createDocumentFragment();
            for (let j = 0; j < 100; j++)
                fragment.appendChild(makeListItem(j, false));
            list.appendChild(fragment);
        }
    }""")

TESTS["frameworks/is-connected-contains.html"] = micro(
    "isConnected + contains checks across a 200-item list", 20000,
    setup="""
    () => {
        const list = buildList(200);
        return { list, detached: document.createElement("li") };
    }""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const item = ctx.list.children[i % 200];
            acc += (item.isConnected ? 1 : 0) + (ctx.list.contains(item) ? 1 : 0) + (ctx.list.contains(ctx.detached) ? 1 : 0);
        }
        if (acc !== iters * 2) throw new Error("bad result");
    }""")

TESTS["frameworks/template-instantiate-fill.html"] = micro(
    "clone a template and fill its slots by query + textContent (the Lit render shape)", 2000,
    setup="""
    () => {
        const template = document.createElement("template");
        template.innerHTML = '<li class="item"><div class="view"><input class="toggle" type="checkbox"><label class="title"></label><span class="count"></span></div></li>';
        return template;
    }""",
    run="""
    (template, iters) => {
        for (let i = 0; i < iters; i++) {
            const instance = template.content.cloneNode(true);
            instance.querySelector(".title").textContent = "todo " + (i & 63);
            instance.querySelector(".count").textContent = String(i & 7);
            instance.querySelector(".toggle").checked = !!(i & 1);
        }
    }""")

TESTS["frameworks/compare-document-position.html"] = micro(
    "compareDocumentPosition-based ordering checks across a 200-item list", 10000,
    setup="() => buildList(200)",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const a = list.children[i % 200];
            const b = list.children[(i * 7 + 1) % 200];
            acc += a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? 1 : 0;
        }
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# urlstate/ — URL machinery and same-document history, the SPA-navigation diet.
# ======================================================================================

TESTS["urlstate/url-parse.html"] = micro(
    "new URL of an absolute URL with query and fragment", 20000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += new URL("https://example.com/articles/section/" + (i & 63) + "?page=2&sort=asc#comments").pathname.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["urlstate/url-search-params.html"] = micro(
    "URLSearchParams build + read + serialize", 20000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const params = new URLSearchParams("a=1&b=two&c=3");
            params.set("page", String(i & 63));
            acc += params.get("b").length + params.toString().length;
        }
        if (!acc) throw new Error("bad result");
    }""")

# Chromium throttles same-document history navigations (~200-call budget per frame,
# crbug.com/1038223); exceeding it stalls the *next* page load. Keep the whole run,
# warm-up included, under that budget.
TESTS["urlstate/history-replace-state.html"] = micro(
    "history.replaceState with a small state object", 30,
    run="""
    (ctx, iters) => {
        for (let i = 0; i < iters; i++)
            history.replaceState({ page: i & 63 }, "", "?page=" + (i & 63));
    }""")

TESTS["urlstate/text-encode-decode.html"] = micro(
    "TextEncoder.encode + TextDecoder.decode of a 1KB string", 5000,
    setup="""
    () => ({ encoder: new TextEncoder(), decoder: new TextDecoder(), text: "hello wörld ünïcode ".repeat(50) })""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += ctx.decoder.decode(ctx.encoder.encode(ctx.text)).length;
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# storage/ — synchronous storage APIs.
# ======================================================================================

TESTS["storage/local-storage.html"] = micro(
    "localStorage setItem + getItem of small values", 5000,
    setup="() => localStorage.clear()",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            localStorage.setItem("key" + (i & 31), "value " + i);
            acc += localStorage.getItem("key" + (i & 31)).length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["storage/session-storage.html"] = micro(
    "sessionStorage setItem + getItem of small values", 5000,
    setup="() => sessionStorage.clear()",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            sessionStorage.setItem("key" + (i & 31), "value " + i);
            acc += sessionStorage.getItem("key" + (i & 31)).length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["storage/cookie.html"] = micro(
    "document.cookie write + read", 1000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            document.cookie = "bench" + (i & 7) + "=value" + i + "; path=/";
            acc += document.cookie.length;
        }
        if (!acc) throw new Error("bad result");
    }""")


def main():
    index_entries = []
    for path in sorted(TESTS):
        full = os.path.join(SUITE_DIR, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(TESTS[path])
        index_entries.append(f'        "{path}",')

    index = f"""<!DOCTYPE html>
<meta charset="utf-8">
<title>MicroWeb Performance Tests</title>
<p>Starting MicroWeb</p>
<iframe width="800" height="600"></iframe>
<script>
window.microWebBenchmark = {{
    name: "MicroWeb",
    tests: [
{chr(10).join(index_entries)}
    ],
}};
</script>
<script src="resources/benchmark-runner.js"></script>
"""
    with open(os.path.join(SUITE_DIR, "index.html"), "w") as f:
        f.write(index)
    print(f"Generated {len(TESTS)} tests + index.html")


if __name__ == "__main__":
    main()
