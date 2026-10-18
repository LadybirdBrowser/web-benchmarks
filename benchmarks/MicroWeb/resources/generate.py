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


def micro(description, iters, run, setup=None, prepare=None):
    parts = [f"    iters: {iters},"]
    if prepare:
        parts.append(f"    prepare: {textwrap.dedent(prepare).strip()},")
    if setup:
        parts.append(f"    setup: {textwrap.dedent(setup).strip()},")
    parts.append(f"    run: {textwrap.dedent(run).strip()},")
    body = "microbench({\n" + "\n".join(parts) + "\n});"
    return page(description, body)


def pipeline(description, cycles, mutate, setup, prepare=None):
    body = (
        "pipelineBench({\n"
        f"    cycles: {cycles},\n"
        + (f"    prepare: {textwrap.dedent(prepare).strip()},\n" if prepare else "")
        + f"    setup: {textwrap.dedent(setup).strip()},\n"
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


# ######################################################################################
# Speedometer-mined additions: operation shapes taken from the Speedometer 2/3
# workloads (TodoMVC apps per framework, the Complex-DOM shell, NewsSite, the editors,
# the charts) that the sections above do not cover.
# ######################################################################################

# ======================================================================================
# complex/ — the Speedometer 3 "Complex DOM" suites: the todo app embedded in the
# ~6600-element Spectrum shell from todomvc/big-dom-generator, styled by big-dom.css and
# the todo-targeted rules of its app.css (:not(.completed), [data-priority], :checked ~).
# ======================================================================================

COMPLEX_PREPARE = "() => loadComplexDOM()"

TESTS["complex/add-100-items.html"] = pipeline(
    "append 100 todo items to the Complex-DOM page's list, then force layout (Adding100Items)", 2,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => { list.textContent = \"\"; forceLayout(); return list; }",
    mutate="""
    (list, k) => {
        for (let i = 0; i < 100; i++)
            list.appendChild(makeTodoItem(k * 100 + i, false));
    }""")

TESTS["complex/append-one-item.html"] = pipeline(
    "append one todo item to the Complex-DOM page, then force layout (per-event rendering frameworks)", 30,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 50)",
    mutate="""
    (list, k) => {
        list.appendChild(makeTodoItem(50 + k, false));
    }""")

TESTS["complex/complete-one-item.html"] = pipeline(
    "toggle 'completed' on one of 100 todo items in the Complex-DOM page, then force layout (CompletingAllItems)", 60,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 100].classList.toggle("completed");
    }""")

TESTS["complex/complete-all-items.html"] = pipeline(
    "set className 'completed' on all 100 todo items in the Complex-DOM page, then force layout once", 4,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    mutate="""
    (list, k) => {
        const value = k & 1 ? "" : "completed";
        for (const li of list.children)
            li.className = value;
    }""")

TESTS["complex/remove-one-item.html"] = pipeline(
    "remove the last of the todo items in the Complex-DOM page, then force layout (DeletingAllItems)", 30,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    mutate="""
    (list, k) => {
        list.lastElementChild.remove();
    }""")

TESTS["complex/remove-100-items.html"] = micro(
    "remove 100 todo items last to first in the Complex-DOM page, then force layout; 10 rounds", 10,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => { fillTodoList(list, 1000); forceLayout(); return list; }",
    run="""
    (list, iters) => {
        for (let round = 0; round < iters; round++) {
            for (let i = 0; i < 100; i++)
                list.lastElementChild.remove();
            forceLayout();
        }
        if (list.childElementCount !== 0) throw new Error("bad result");
    }""")

TESTS["complex/checkbox-click-delegated.html"] = pipeline(
    "click() a todo checkbox in the Complex-DOM page; a delegated change handler toggles the item class and footer count; then force layout", 30,
    prepare="""
    async () => {
        const list = await loadComplexDOM();
        fillTodoList(list, 100);
        const count = document.querySelector(".todo-count strong");
        let active = 100;
        list.addEventListener("change", (event) => {
            const done = event.target.closest("li").classList.toggle("completed");
            active += done ? -1 : 1;
            count.textContent = String(active);
        });
        return Array.from(list.querySelectorAll(".toggle"));
    }""",
    setup="(iteration, toggles) => toggles",
    mutate="""
    (toggles, k) => {
        toggles[(k * 37) % 100].click();
    }""")

TESTS["complex/priority-attribute-change.html"] = pipeline(
    "change data-priority on one todo item, matched by app.css [data-priority] rules in the Complex-DOM page, then force layout", 60,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 100].setAttribute("data-priority", String(k % 5));
    }""")

TESTS["complex/label-text-change.html"] = pipeline(
    "change one todo label's text in the Complex-DOM page, then force layout", 30,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => { fillTodoList(list, 100); return Array.from(list.querySelectorAll(\"label\")); }",
    mutate="""
    (labels, k) => {
        labels[(k * 37) % 100].textContent = todoTitle(k + 1000);
    }""")

TESTS["complex/computed-style-after-toggle.html"] = micro(
    "toggle 'completed' on one todo item then read getComputedStyle(label).textDecorationLine, in the Complex-DOM page", 250,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => { fillTodoList(list, 100); forceLayout(); return list; }",
    run="""
    (list, iters) => {
        let struck = 0;
        for (let i = 0; i < iters; i++) {
            const li = list.children[(i * 13) % 100];
            li.classList.toggle("completed");
            if (getComputedStyle(li.querySelector("label")).textDecorationLine.includes("line-through")) struck++;
        }
        if (!struck) throw new Error("bad result");
    }""")

TESTS["complex/query-selector-all-toggle.html"] = micro(
    "document.querySelectorAll('.toggle') on the ~6600-element Complex-DOM page (the Speedometer driver's lookup)", 500,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const all = document.querySelectorAll(".toggle");
            acc += all.length;
        }
        if (acc !== 100 * iters) throw new Error("bad result " + acc);
    }""")

TESTS["complex/query-selector-all-after-mutation.html"] = micro(
    "append a todo item, then document.querySelectorAll('.destroy') on the Complex-DOM page (query after DOM change)", 400,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            list.appendChild(makeTodoItem(100 + i, false));
            acc += document.querySelectorAll(".destroy").length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["complex/body-class-unused.html"] = pipeline(
    "toggle a <body> class no selector references in the Complex-DOM page, then force layout (invalidation should prove it irrelevant)", 80,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => fillTodoList(list, 100)",
    mutate="""
    (list, k) => {
        document.body.classList.toggle("unused-state-class");
    }""")

TESTS["complex/body-class-restyle.html"] = pipeline(
    "toggle a <body> class that descendant rules depend on (letter-spacing of every menu/tree label) in the Complex-DOM page, then force layout", 4,
    prepare="""
    async () => {
        const list = await loadComplexDOM();
        injectStyleOnce("complex-state", ".app-state .spectrum-TreeView-itemLabel, .app-state .spectrum-Menu-itemLabel, .app-state .todo-area label { letter-spacing: 0.5px; }");
        return fillTodoList(list, 100);
    }""",
    setup="(iteration, list) => list",
    mutate="""
    (list, k) => {
        document.body.classList.toggle("app-state");
    }""")

TESTS["complex/item-bounding-rect.html"] = micro(
    "getBoundingClientRect of todo items in the settled Complex-DOM page (the driver's mouse-event coordinate lookup)", 2000,
    prepare=COMPLEX_PREPARE,
    setup="(iteration, list) => { fillTodoList(list, 100); forceLayout(); return Array.from(list.children); }",
    run="""
    (items, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += items[i % 100].getBoundingClientRect().height > 0 ? 1 : 0;
        if (acc !== iters) throw new Error("bad result");
    }""")

# ======================================================================================
# frameworks/ additions — the render and dispatch shapes of individual TodoMVC apps.
# ======================================================================================

TESTS["frameworks/es5-domparser-rerender.html"] = pipeline(
    "re-render a 100-item list the ES5 TodoMVC way: String.replace template, DOMParser, replaceChildren(...childNodes), then force layout", 10,
    setup="""
    () => {
        ensureListStyles();
        sandbox().innerHTML = "<ul class='todo-list'></ul>";
        return sandbox().firstChild;
    }""",
    mutate="""
    (list, k) => {
        const template = '<li data-id="{{id}}" class="{{completed}}"><div class="view"><input class="toggle" type="checkbox" {{checked}}><label>{{title}}</label><button class="destroy"></button></div></li>';
        let view = "";
        for (let i = 0; i < 100; i++) {
            const done = (i + k) % 3 === 0;
            view += template.replace("{{id}}", i).replace("{{completed}}", done ? "completed" : "").replace("{{checked}}", done ? "checked" : "").replace("{{title}}", todoTitle(i));
        }
        const doc = new DOMParser().parseFromString(view, "text/html");
        list.replaceChildren(...doc.body.childNodes);
        if (list.childElementCount !== 100) throw new Error("bad result");
    }""")

TESTS["frameworks/es5-delegate-lookup.html"] = micro(
    "ES5 TodoMVC $delegate: querySelectorAll(selector, list) + Array.prototype.indexOf.call(matches, target) per event", 2000,
    setup="() => { const list = buildList(100); return { list, toggles: Array.from(list.querySelectorAll('.toggle')) }; }",
    run="""
    ({ list, toggles }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += Array.prototype.indexOf.call(list.querySelectorAll(".toggle"), toggles[i % 100]);
        if (acc <= 0) throw new Error("bad result");
    }""")

TESTS["frameworks/web-component-item-create.html"] = micro(
    "construct the TodoMVC-WebComponents todo-item: importNode(template) into an open shadow root with adoptedStyleSheets, 7 querySelectors, 3 observed attributes, append", 500,
    setup="""
    () => {
        if (!window.TodoItem) {
            const template = document.createElement("template");
            template.innerHTML = '<li class="todo-item"><div class="display-todo"><label class="toggle-todo-label"><input class="toggle-todo-input" type="checkbox"></label><span class="todo-item-text" tabindex="0"></span><button class="remove-todo-button"></button></div><div class="edit-todo-container"><label class="edit-todo-label"></label><input class="edit-todo-input" type="text"></div></li>';
            const sheet = new CSSStyleSheet();
            sheet.replaceSync(".todo-item{position:relative;font-size:24px;border-bottom:1px solid #ededed}.todo-item.completed .todo-item-text{color:#949494;text-decoration:line-through}.toggle-todo-input{width:40px;height:40px}.edit-todo-container{display:none}");
            window.TodoItem = class extends HTMLElement {
                static get observedAttributes() { return ["itemid", "itemtitle", "itemcompleted"]; }
                constructor() {
                    super();
                    const node = document.importNode(template.content, true);
                    this.item = node.querySelector(".todo-item");
                    this.toggleLabel = node.querySelector(".toggle-todo-label");
                    this.toggleInput = node.querySelector(".toggle-todo-input");
                    this.todoText = node.querySelector(".todo-item-text");
                    this.todoButton = node.querySelector(".remove-todo-button");
                    this.editLabel = node.querySelector(".edit-todo-label");
                    this.editInput = node.querySelector(".edit-todo-input");
                    this.shadow = this.attachShadow({ mode: "open" });
                    this.shadow.adoptedStyleSheets = [sheet];
                    this.shadow.append(node);
                }
                attributeChangedCallback(name, oldValue, newValue) {
                    if (name === "itemtitle") { this.todoText.textContent = newValue; this.editInput.value = newValue; }
                    else if (name === "itemcompleted") this.toggleInput.checked = newValue === "true";
                }
            };
            customElements.define("todo-item", window.TodoItem);
        }
        sandbox().innerHTML = "<ul></ul>";
        return sandbox().firstChild;
    }""",
    run="""
    (list, iters) => {
        for (let i = 0; i < iters; i++) {
            const element = new TodoItem();
            element.setAttribute("itemid", String(i));
            element.setAttribute("itemtitle", todoTitle(i));
            element.setAttribute("itemcompleted", "false");
            list.append(element);
            element.setAttribute("data-priority", String(4 - (i % 5)));
        }
        if (list.childElementCount !== iters) throw new Error("bad result");
    }""")

TESTS["frameworks/lit-template-instance.html"] = micro(
    "lit-html TemplateInstance: importNode of a template with <!--?lit$...$--> markers, TreeWalker walk to find parts, insert child-part text nodes, set attribute/property parts", 2000,
    setup="""
    () => {
        const template = document.createElement("template");
        template.innerHTML = '<li class="todo"><div class="view"><input class="toggle" type="checkbox"><label><!--?lit$1234$--></label><button class="destroy"></button></div><input class="edit" type="text"></li>';
        sandbox().innerHTML = "<ul></ul>";
        return { template, list: sandbox().firstChild };
    }""",
    run="""
    ({ template, list }, iters) => {
        let parts = 0;
        for (let i = 0; i < iters; i++) {
            const fragment = document.importNode(template.content, true);
            const walker = document.createTreeWalker(fragment, 129);
            let node, li = null, toggle = null;
            while ((node = walker.nextNode()) !== null) {
                if (node.nodeType === 8) {
                    node.parentNode.insertBefore(document.createTextNode(todoTitle(i)), node);
                    parts++;
                } else if (node.localName === "li") li = node;
                else if (node.className === "toggle") toggle = node;
            }
            li.setAttribute("class", i & 1 ? "todo completed" : "todo");
            toggle.checked = (i & 1) === 1;
            list.appendChild(fragment);
        }
        if (parts !== iters) throw new Error("bad result");
    }""")

TESTS["frameworks/react-root-delegation.html"] = micro(
    "React 17 root event delegation: one native click listener on the root walks target.parentNode collecting __reactProps$ handlers and calls them with a synthetic event", 5000,
    setup="""
    () => {
        const list = buildList(100);
        const key = "__reactProps$x1y2z3";
        let toggled = 0;
        for (const li of list.children) {
            li[key] = { className: "", children: null };
            li.firstChild[key] = { className: "view" };
            li.querySelector(".toggle")[key] = { onClick: () => { toggled++; }, onChange: () => {} };
        }
        const root = sandbox();
        if (!root.reactListener) {
            root.reactListener = (nativeEvent) => {
                const listeners = [];
                for (let node = nativeEvent.target; node && node !== root; node = node.parentNode) {
                    const props = node[key];
                    if (props && typeof props.onClick === "function") listeners.push([node, props.onClick]);
                }
                const synthetic = { nativeEvent, type: nativeEvent.type, target: nativeEvent.target, currentTarget: null };
                for (const [node, listener] of listeners) { synthetic.currentTarget = node; listener(synthetic); }
            };
            root.addEventListener("click", root.reactListener);
        }
        return { toggles: Array.from(list.querySelectorAll(".toggle")), count: () => toggled };
    }""",
    run="""
    ({ toggles, count }, iters) => {
        for (let i = 0; i < iters; i++)
            toggles[i % 100].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        if (count() !== iters) throw new Error("bad result " + count());
    }""")

TESTS["frameworks/vue-reactive-proxy.html"] = micro(
    "Vue 3 reactivity: Proxy get trap with track() into WeakMap/Map/Set deps and set trap with Reflect.set + trigger(), 2 reads + 1 write per op", 50000,
    setup="""
    () => {
        const targetMap = new WeakMap();
        const effect = {};
        const track = (target, key) => {
            let depsMap = targetMap.get(target);
            if (!depsMap) targetMap.set(target, (depsMap = new Map()));
            let dep = depsMap.get(key);
            if (!dep) depsMap.set(key, (dep = new Set()));
            if (!dep.has(effect)) dep.add(effect);
        };
        const state = { triggered: 0 };
        const trigger = (target, key) => { const deps = targetMap.get(target); if (deps && deps.get(key)) state.triggered++; };
        const handler = {
            get(target, key, receiver) { const result = Reflect.get(target, key, receiver); track(target, key); return result; },
            set(target, key, value, receiver) { const old = target[key]; const result = Reflect.set(target, key, value, receiver); if (old !== value) trigger(target, key); return result; },
        };
        const items = [];
        for (let i = 0; i < 100; i++) items.push(new Proxy({ id: i, title: "todo " + i, completed: false }, handler));
        return { items, state };
    }""",
    run="""
    ({ items, state }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const item = items[i % 100];
            acc += item.id + item.title.length;
            item.completed = !item.completed;
        }
        if (!acc || !state.triggered) throw new Error("bad result");
    }""")

TESTS["frameworks/redux-spread-map.html"] = micro(
    "Redux/useReducer toggle: todos.map(t => t.id === id ? {...t, completed: !t.completed} : t) over 100 todos", 2000,
    setup="""
    () => {
        const todos = [];
        for (let i = 0; i < 100; i++) todos.push({ id: "t" + i, title: todoTitle(i), completed: false, priority: i % 5 });
        return todos;
    }""",
    run="""
    (todos, iters) => {
        let state = todos;
        for (let i = 0; i < iters; i++) {
            const id = "t" + (i % 100);
            state = state.map((t) => (t.id === id ? { ...t, completed: !t.completed } : t));
        }
        if (state.length !== 100) throw new Error("bad result");
    }""")

TESTS["frameworks/backbone-item-render.html"] = pipeline(
    "Backbone TodoView.render: li.innerHTML = item template on 100 existing items, then force layout once", 10,
    setup="""
    () => {
        const list = buildList(100);
        return Array.from(list.children);
    }""",
    mutate="""
    (items, k) => {
        for (let i = 0; i < 100; i++) {
            const title = todoTitle(i + k);
            items[i].innerHTML = `<div class="view"><input class="toggle" type="checkbox"${(i + k) & 1 ? " checked" : ""}><label>${title}</label><button class="destroy"></button></div><input class="edit" value="${title}">`;
        }
    }""")

TESTS["frameworks/jquery-full-rerender.html"] = pipeline(
    "jQuery TodoMVC render(): rebuild a 100-item list string with a Handlebars-like loop, set innerHTML, rebuild the footer, then force layout", 10,
    setup="""
    () => {
        ensureListStyles();
        sandbox().innerHTML = "<ul class='todo-list'></ul><footer><span class='todo-count'></span></footer>";
        return { list: sandbox().firstChild, footer: sandbox().lastChild };
    }""",
    mutate="""
    ({ list, footer }, k) => {
        const todos = [];
        for (let i = 0; i < 100; i++) todos.push({ id: i, title: todoTitle(i), completed: (i + k) % 4 === 0 });
        list.innerHTML = todos.map((t) => `<li${t.completed ? ' class="completed"' : ""} data-id="${t.id}"><div class="view"><input class="toggle" type="checkbox"${t.completed ? " checked" : ""}><label>${t.title}</label><button class="destroy"></button></div><input class="edit" value="${t.title}"></li>`).join("");
        const active = todos.filter((t) => !t.completed).length;
        footer.innerHTML = `<span class="todo-count"><strong>${active}</strong> ${active === 1 ? "item" : "items"} left</span>`;
    }""")

TESTS["frameworks/svelte-text-data.html"] = pipeline(
    "Svelte set_data: write text-node .data of 100 labels and the footer count, then force layout once", 20,
    setup="""
    () => {
        const list = buildList(100);
        return Array.from(list.querySelectorAll("label"), (label) => label.firstChild);
    }""",
    mutate="""
    (texts, k) => {
        for (let i = 0; i < 100; i++)
            texts[i].data = todoTitle(i + (k & 1) * 100);
    }""")

TESTS["frameworks/angular-dirty-check.html"] = micro(
    "Angular-style change detection: compare 100 components' 4 bound values against their last values, update the DOM only where changed (one change per pass)", 500,
    setup="""
    () => {
        const list = buildList(100);
        const views = Array.from(list.children, (li, i) => ({
            li, label: li.querySelector("label"), toggle: li.querySelector(".toggle"),
            model: { title: "Something to do " + i + " lorem ipsum dolor sit amet", completed: false, editing: false, priority: i % 5 },
            last: { title: "Something to do " + i + " lorem ipsum dolor sit amet", completed: false, editing: false, priority: i % 5 },
        }));
        return views;
    }""",
    run="""
    (views, iters) => {
        let writes = 0;
        for (let i = 0; i < iters; i++) {
            views[i % 100].model.completed = !views[i % 100].model.completed;
            for (const view of views) {
                const { model, last } = view;
                if (model.title !== last.title) { view.label.textContent = last.title = model.title; writes++; }
                if (model.completed !== last.completed) { view.li.classList.toggle("completed", (last.completed = model.completed)); view.toggle.checked = model.completed; writes++; }
                if (model.editing !== last.editing) { view.li.classList.toggle("editing", (last.editing = model.editing)); writes++; }
                if (model.priority !== last.priority) { view.li.dataset.priority = last.priority = model.priority; writes++; }
            }
        }
        if (writes !== iters) throw new Error("bad result " + writes);
    }""")

TESTS["frameworks/preact-diff-props.html"] = micro(
    "Preact diffProps: compare old/new props objects key by key and apply className, style object, data-* and event-handler props to an element", 20000,
    setup="""
    () => {
        const el = document.createElement("li");
        const handlers = [() => 1, () => 2];
        const propsList = [];
        for (let i = 0; i < 8; i++)
            propsList.push({ class: i & 1 ? "completed" : "", "data-priority": String(i % 5), style: { opacity: i & 2 ? "0.5" : "1" }, onClick: handlers[i & 1], title: "t" + (i & 3) });
        return { el, propsList };
    }""",
    run="""
    ({ el, propsList }, iters) => {
        let old = {}, applied = 0;
        for (let i = 0; i < iters; i++) {
            const props = propsList[i & 7];
            for (const name in old) if (!(name in props)) { el.removeAttribute(name); applied++; }
            for (const name in props) {
                const value = props[name];
                if (old[name] === value) continue;
                if (name === "class") el.className = value;
                else if (name === "style") { for (const s in value) el.style[s] = value[s]; }
                else if (name[0] === "o" && name[1] === "n") el["l" + name.slice(2).toLowerCase()] = value;
                else el.setAttribute(name, value);
                applied++;
            }
            old = props;
        }
        if (!applied) throw new Error("bad result");
    }""")

TESTS["frameworks/vdom-create-element.html"] = micro(
    "React/Preact createElement: build a 6-node vnode tree per todo item with props objects, keys and children arrays", 20000,
    setup="""
    () => {
        const h = (type, props, ...children) => ({ type, props: props || {}, key: props && props.key !== undefined ? props.key : null, children, ref: null, _dom: null });
        return h;
    }""",
    run="""
    (h, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const vnode = h("li", { key: i, className: i & 1 ? "completed" : "" },
                h("div", { className: "view" },
                    h("input", { className: "toggle", type: "checkbox", checked: (i & 1) === 1, onChange: null }),
                    h("label", { onDblClick: null }, "Todo " + (i & 63)),
                    h("button", { className: "destroy", onClick: null })));
            acc += vnode.children[0].children.length;
        }
        if (acc !== 3 * iters) throw new Error("bad result");
    }""")

# ======================================================================================
# render/ additions — Speedometer step shapes not covered above.
# ======================================================================================

TESTS["render/complete-100-items.html"] = pipeline(
    "set className 'completed' on all 100 todo items, then force layout once (CompletingAllItems, batched frameworks)", 20,
    setup="() => { ensureListStyles(); return buildList(100); }",
    mutate="""
    (list, k) => {
        const value = k & 1 ? "" : "completed";
        for (const li of list.children)
            li.className = value;
    }""")

TESTS["render/check-100-checkboxes.html"] = pipeline(
    "set .checked on 100 todo checkboxes, then force layout once", 20,
    setup="() => Array.from(buildList(100).querySelectorAll('.toggle'))",
    mutate="""
    (toggles, k) => {
        for (const toggle of toggles)
            toggle.checked = !(k & 1);
    }""")

TESTS["render/remove-100-items.html"] = micro(
    "remove 100 todo items last to first with removeChild, then force layout; 20 rounds (DeletingAllItems)", 20,
    setup="""
    () => {
        const list = buildList(0);
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < 2000; i++) fragment.appendChild(makeTodoItem(i, false));
        list.appendChild(fragment);
        forceLayout();
        return list;
    }""",
    run="""
    (list, iters) => {
        for (let round = 0; round < iters; round++) {
            for (let i = 99; i >= 0; i--)
                list.removeChild(list.lastElementChild);
            forceLayout();
        }
        if (list.childElementCount !== 0) throw new Error("bad result");
    }""")

TESTS["render/prepend-100-items.html"] = pipeline(
    "insertBefore(item, list.firstChild) 100 times, then force layout once", 5,
    setup="() => buildList(0)",
    mutate="""
    (list, k) => {
        list.textContent = "";
        for (let i = 0; i < 100; i++)
            list.insertBefore(makeTodoItem(i, false), list.firstChild);
    }""")

TESTS["render/clear-list-text-content.html"] = pipeline(
    "list.textContent = '' on a 100-item list, then refill it with insertAdjacentHTML strings, then force layout", 10,
    setup="() => buildList(100)",
    mutate="""
    (list, k) => {
        list.textContent = "";
        let html = "";
        for (let i = 0; i < 100; i++) html += todoItemHTML(i, (i + k) % 3 === 0);
        list.insertAdjacentHTML("beforeend", html);
    }""")

TESTS["render/filter-display-none.html"] = pipeline(
    "filter a 100-item list by setting style.display on every item (web-components/ES5 filtering), then force layout", 20,
    setup="() => Array.from(buildList(100).children)",
    mutate="""
    (items, k) => {
        for (let i = 0; i < 100; i++)
            items[i].style.display = (i + k) % 3 === 0 ? "none" : "";
    }""")

TESTS["render/page-remount.html"] = pipeline(
    "NewsSite route change: tear down and rebuild a ~600-element article page (header, nav, 6 sections of article cards), then force layout", 3,
    setup="""
    () => {
        injectStyleOnce("news-styles", `
            .page { font: 16px/1.5 sans-serif; }
            .page header, .page nav { display: flex; gap: 12px; padding: 8px; }
            .page nav a { padding-inline: 8px; }
            .page section { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-block: 16px; }
            .page article { border: 1px solid #ddd; padding: 8px; }
            .page article h3 { font-size: 18px; margin: 0 0 8px; }
            .page article p { margin: 0; }
        `);
        sandbox().textContent = "";
        return sandbox();
    }""",
    mutate="""
    (root, k) => {
        root.textContent = "";
        const page = document.createElement("div");
        page.className = "page";
        const header = document.createElement("header");
        header.textContent = "The Daily Broadcast";
        page.appendChild(header);
        const nav = document.createElement("nav");
        for (const name of ["Front Page", "US", "World", "Politics", "Business", "Opinion", "Health"]) {
            const a = document.createElement("a");
            a.href = "#/" + name.toLowerCase();
            a.textContent = name;
            nav.appendChild(a);
        }
        page.appendChild(nav);
        for (let s = 0; s < 6; s++) {
            const section = document.createElement("section");
            for (let a = 0; a < 12; a++) {
                const article = document.createElement("article");
                const h3 = document.createElement("h3");
                h3.textContent = "Headline " + (k * 100 + s * 12 + a) + " about the economy";
                const p = document.createElement("p");
                p.textContent = "The quick brown fox jumps over the lazy dog near the river bank while reporters gather. ".repeat(2);
                const ul = document.createElement("ul");
                for (let t = 0; t < 3; t++) { const li = document.createElement("li"); li.textContent = "tag" + t; ul.appendChild(li); }
                article.append(h3, p, ul);
                section.appendChild(article);
            }
            page.appendChild(section);
        }
        root.appendChild(page);
    }""")

# ======================================================================================
# dom/ additions
# ======================================================================================

TESTS["dom/query-selector-data-id.html"] = micro(
    "list.querySelector('[data-id=\"N\"]') with the selector string built per lookup (ES5/ES6 TodoMVC qs)", 15000,
    setup="() => fillTodoList(buildList(0), 100)",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += list.querySelector('[data-id="' + (i % 100) + '"]').childElementCount;
        if (acc !== iters) throw new Error("bad result");
    }""")

TESTS["dom/set-remove-attribute-attached.html"] = micro(
    "setAttribute + removeAttribute pair on attached todo items", 20000,
    setup="() => Array.from(fillTodoList(buildList(0), 100).children)",
    run="""
    (items, iters) => {
        for (let i = 0; i < iters; i++) {
            const li = items[i % 100];
            li.setAttribute("aria-checked", "v" + (i & 3));
            li.removeAttribute("aria-checked");
        }
        if (items[3].hasAttribute("aria-checked")) throw new Error("bad result");
    }""")

TESTS["dom/dataset-write.html"] = micro(
    "dataset property write on attached elements (Angular/Lit attribute bindings)", 20000,
    setup="() => Array.from(fillTodoList(buildList(0), 100).children)",
    run="""
    (items, iters) => {
        for (let i = 0; i < iters; i++)
            items[i % 100].dataset.priority = String(i % 5);
        if (items[1].dataset.priority === undefined) throw new Error("bad result");
    }""")

TESTS["dom/get-attribute-parse-int.html"] = micro(
    "parseInt(li.dataset.id) + parseInt(getAttribute('data-priority')) on attached todo items", 50000,
    setup="() => Array.from(fillTodoList(buildList(0), 100).children)",
    run="""
    (items, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const li = items[i % 100];
            acc += parseInt(li.dataset.id, 10) + parseInt(li.getAttribute("data-priority"), 10);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/children-index.html"] = micro(
    "list.children[i] + childElementCount + childNodes.length on a 100-item list", 50000,
    setup="() => buildList(100)",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += list.children[i % 100].childElementCount + list.childNodes.length;
        if (acc !== 101 * iters) throw new Error("bad result");
    }""")

TESTS["dom/create-comment-anchor.html"] = micro(
    "createComment('') + createTextNode appended as anchors (Vue fragments, Lit markers, React text)", 20000,
    setup="() => document.createElement(\"div\")",
    run="""
    (host, iters) => {
        host.textContent = "";
        for (let i = 0; i < iters; i++) {
            host.appendChild(document.createComment(""));
            host.appendChild(document.createTextNode("x" + (i & 15)));
        }
        if (host.childNodes.length !== 2 * iters) throw new Error("bad result");
    }""")

TESTS["dom/remove-attached-item.html"] = micro(
    "element.remove() of attached todo items (no layout flush), list rebuilt untimed", 10000,
    setup="""
    () => {
        const list = buildList(0);
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < 10000; i++) fragment.appendChild(makeTodoItem(i, false));
        list.appendChild(fragment);
        return list;
    }""",
    run="""
    (list, iters) => {
        for (let i = 0; i < iters; i++)
            list.lastElementChild.remove();
        if (list.childElementCount !== 0) throw new Error("bad result");
    }""")

TESTS["dom/tree-walker-comments.html"] = micro(
    "createTreeWalker(SHOW_COMMENT) search through a 100-item list with comment anchors (Lit/Vue hydration)", 1000,
    setup="""
    () => {
        const list = buildList(100);
        for (const li of list.children) li.firstChild.insertBefore(document.createComment("?lit$1$"), li.firstChild.firstChild);
        return list;
    }""",
    run="""
    (list, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const walker = document.createTreeWalker(list, NodeFilter.SHOW_COMMENT);
            while (walker.nextNode()) acc++;
        }
        if (acc !== 100 * iters) throw new Error("bad result " + acc);
    }""")

TESTS["dom/class-name-read.html"] = micro(
    "className read + classList.contains on attached items (jQuery hasClass, Backbone)", 50000,
    setup="() => Array.from(fillTodoList(buildList(0), 100, 3).children)",
    run="""
    (items, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const li = items[i % 100];
            acc += li.className.length + (li.classList.contains("completed") ? 1 : 0);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/text-content-read-item.html"] = micro(
    "textContent read of one todo item subtree (label text lookups in framework tests/drivers)", 50000,
    setup="() => Array.from(buildList(100).children)",
    run="""
    (items, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += items[i % 100].textContent.length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["dom/append-to-new-parent.html"] = micro(
    "move existing todo items between two attached lists with appendChild (keyed list moves)", 20000,
    setup="""
    () => {
        const a = buildList(100);
        const b = document.createElement("ul");
        sandbox().appendChild(b);
        return { a, b };
    }""",
    run="""
    ({ a, b }, iters) => {
        for (let i = 0; i < iters; i++) {
            const from = i & 1 ? b : a, to = i & 1 ? a : b;
            if (from.firstChild) to.appendChild(from.firstChild);
        }
        if (a.childElementCount + b.childElementCount !== 100) throw new Error("bad result");
    }""")

# ======================================================================================
# events/ additions
# ======================================================================================

TESTS["events/checkbox-click-activation.html"] = micro(
    "click() on todo checkboxes: activation flips checked and fires click, input and change; delegated listeners on the list", 5000,
    setup="""
    () => {
        const list = buildList(100);
        const counts = { click: 0, change: 0, input: 0 };
        list.addEventListener("click", (e) => { if (e.target.classList.contains("toggle")) counts.click++; });
        list.addEventListener("input", () => { counts.input++; });
        list.addEventListener("change", (e) => { if (e.target.closest("li")) counts.change++; });
        return { toggles: Array.from(list.querySelectorAll(".toggle")), counts };
    }""",
    run="""
    ({ toggles, counts }, iters) => {
        for (let i = 0; i < iters; i++)
            toggles[i % 100].click();
        if (counts.click !== iters || counts.change !== iters) throw new Error("bad result");
    }""")

TESTS["events/keypress-enter-new-todo.html"] = micro(
    "new KeyboardEvent('keypress', {key: 'Enter', keyCode: 13, which: 13}) on .new-todo, listeners on the input and the app root read key/keyCode/target.value (the Speedometer driver's enter())", 20000,
    setup="""
    () => {
        sandbox().innerHTML = TODO_APP_HTML;
        const input = sandbox().querySelector(".new-todo");
        input.value = "Walk the dog";
        const counts = { seen: 0 };
        input.addEventListener("keypress", (e) => { if (e.keyCode === 13) counts.seen++; });
        sandbox().firstChild.addEventListener("keypress", (e) => { if (e.key === "Enter" && e.target.value.length) counts.seen++; });
        return { input, counts };
    }""",
    run="""
    ({ input, counts }, iters) => {
        for (let i = 0; i < iters; i++)
            input.dispatchEvent(new KeyboardEvent("keypress", { bubbles: true, cancelable: true, keyCode: 13, which: 13, key: "Enter" }));
        if (counts.seen !== 2 * iters) throw new Error("bad result");
    }""")

TESTS["events/wheel-event-dispatch.html"] = micro(
    "new WheelEvent('wheel', {deltaY, clientX, clientY}) dispatched on a chart; handler reads deltaY/clientX and calls preventDefault (React-Stockcharts ZoomTheChart)", 20000,
    setup="""
    () => {
        sandbox().innerHTML = "<div style='width:600px;height:300px'></div>";
        const chart = sandbox().firstChild;
        const counts = { zoom: 0 };
        chart.addEventListener("wheel", (e) => { counts.zoom += e.deltaY < 0 ? 1 : 0; e.preventDefault(); }, { passive: false });
        return { chart, counts };
    }""",
    run="""
    ({ chart, counts }, iters) => {
        for (let i = 0; i < iters; i++)
            chart.dispatchEvent(new WheelEvent("wheel", { deltaY: -10, clientX: 100 + (i & 63), clientY: 100, bubbles: true, cancelable: true }));
        if (counts.zoom !== iters) throw new Error("bad result");
    }""")

TESTS["events/mouse-drag-sequence.html"] = micro(
    "mousedown + 10 mousemove + mouseup with coordinates from getBoundingClientRect (the driver's dispatchMouseEvent; PanTheChart/SelectingRange)", 1000,
    setup="""
    () => {
        sandbox().innerHTML = "<div style='margin:20px;width:600px;height:300px'></div>";
        const target = sandbox().firstChild;
        const state = { dx: 0, down: false };
        target.addEventListener("mousedown", (e) => { state.down = true; state.x = e.clientX; });
        target.addEventListener("mousemove", (e) => { if (state.down) state.dx += e.clientX - state.x; });
        target.addEventListener("mouseup", () => { state.down = false; });
        return { target, state };
    }""",
    run="""
    ({ target, state }, iters) => {
        const fire = (type, x, y) => {
            const r = target.getBoundingClientRect();
            target.dispatchEvent(new MouseEvent(type, { clientX: r.x + x, clientY: r.y + y, bubbles: true, cancelable: true }));
        };
        for (let i = 0; i < iters; i++) {
            fire("mousedown", 100, 100);
            for (let m = 0; m < 10; m++) fire("mousemove", 100 + m * 5, 100);
            fire("mouseup", 150, 100);
        }
        if (!state.dx) throw new Error("bad result");
    }""")

TESTS["events/keydown-arrow-component.html"] = micro(
    "keydown ArrowRight dispatched at an element inside a closed shadow root; a listener on the host checks key and updates a selection index (Perf-Dashboard SelectingPoints)", 20000,
    setup="""
    () => {
        sandbox().textContent = "";
        const host = document.createElement("div");
        sandbox().appendChild(host);
        const root = host.attachShadow({ mode: "closed" });
        root.innerHTML = "<div class='pane'><canvas width=10 height=10 tabindex=0></canvas></div>";
        const canvas = root.querySelector("canvas");
        const state = { index: 0 };
        host.addEventListener("keydown", (e) => { if (e.key === "ArrowRight") state.index++; else if (e.key === "ArrowLeft") state.index--; });
        return { canvas, state };
    }""",
    run="""
    ({ canvas, state }, iters) => {
        for (let i = 0; i < iters; i++)
            canvas.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, composed: true, cancelable: true }));
        if (state.index !== iters) throw new Error("bad result");
    }""")

TESTS["events/event-construct-only.html"] = micro(
    "new Event / new CustomEvent / new KeyboardEvent construction without dispatch", 50000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const e = (i % 3 === 0) ? new Event("change", { bubbles: true }) : (i % 3 === 1) ? new CustomEvent("toggle-item", { detail: i }) : new KeyboardEvent("keyup", { key: "Enter" });
            acc += e.type.length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["events/listener-object-handle-event.html"] = micro(
    "dispatch to listeners registered as objects with handleEvent (Lit/Backbone/Ember style) plus once:true listeners re-added", 20000,
    setup="""
    () => {
        const target = document.createElement("button");
        sandbox().appendChild(target);
        const handler = { count: 0, handleEvent(e) { this.count += e.type === "click" ? 1 : 0; } };
        target.addEventListener("click", handler);
        return { target, handler };
    }""",
    run="""
    ({ target, handler }, iters) => {
        let once = 0;
        for (let i = 0; i < iters; i++) {
            if ((i & 7) === 0) target.addEventListener("click", () => { once++; }, { once: true });
            target.dispatchEvent(new Event("click"));
        }
        if (handler.count < iters || !once) throw new Error("bad result");
    }""")

# ======================================================================================
# style/ additions
# ======================================================================================

TESTS["style/computed-style-after-class.html"] = micro(
    "toggle a class on one of 300 cells then read getComputedStyle(cell).color (forced style recalc, no layout)", 1500,
    setup="""
    () => {
        injectStyleOnce("cells", ".cell { display: inline-block; width: 40px; color: rgb(10, 20, 30); } .cell.on { color: rgb(200, 0, 0); }");
        sandbox().textContent = "";
        const cells = [];
        for (let i = 0; i < 300; i++) { const d = document.createElement("div"); d.className = "cell"; d.textContent = "c" + i; sandbox().appendChild(d); cells.push(d); }
        forceLayout();
        return cells;
    }""",
    run="""
    (cells, iters) => {
        let red = 0;
        for (let i = 0; i < iters; i++) {
            const cell = cells[(i * 7) % 300];
            cell.classList.toggle("on");
            if (getComputedStyle(cell).color === "rgb(200, 0, 0)") red++;
        }
        if (!red) throw new Error("bad result");
    }""")

TESTS["style/inline-width-300.html"] = pipeline(
    "style.width writes on 300 inline-block cells, then force layout once", 10,
    setup="""
    () => {
        injectStyleOnce("cells2", ".wcell { display: inline-block; height: 12px; background: #ccc; margin: 1px; overflow: hidden; }");
        sandbox().textContent = "";
        const cells = [];
        for (let i = 0; i < 300; i++) { const d = document.createElement("div"); d.className = "wcell"; sandbox().appendChild(d); cells.push(d); }
        return cells;
    }""",
    mutate="""
    (cells, k) => {
        for (let i = 0; i < 300; i++)
            cells[i].style.width = ((i + k) % 50) + 20 + "px";
    }""")

TESTS["style/css-text-300.html"] = pipeline(
    "style.cssText with 4 declarations (width, height, background-color, transform) on 300 cells, then force layout once", 10,
    setup="""
    () => {
        sandbox().textContent = "";
        const cells = [];
        for (let i = 0; i < 300; i++) { const d = document.createElement("div"); d.style.display = "inline-block"; sandbox().appendChild(d); cells.push(d); }
        return cells;
    }""",
    mutate="""
    (cells, k) => {
        for (let i = 0; i < 300; i++) {
            const v = (i + k) % 40;
            cells[i].style.cssText = `display: inline-block; width: ${v + 20}px; height: 12px; background-color: rgb(${v * 5}, 100, 150); transform: translate(${v}px, 0px)`;
        }
    }""")

TESTS["style/nth-child-prepend.html"] = pipeline(
    "prepend one item into a 200-item list styled with :nth-child(odd)/:first-child/:last-child, then force layout", 30,
    setup="""
    () => {
        injectStyleOnce("nth", ".todo-list li:nth-child(odd) { background: #fafafa; } .todo-list li:first-child label { font-weight: bold; } .todo-list li:last-child { border-bottom: none; }");
        return buildList(200);
    }""",
    mutate="""
    (list, k) => {
        list.insertBefore(makeListItem(k, false), list.firstChild);
    }""")

TESTS["style/var-calc-transform-dropdown.html"] = pipeline(
    "NewsSite dropdown: click() a hidden checkbox; :checked ~ label .chevron transform: translate(calc(var() * var())) rotate() and :checked ~ ul display; then force layout", 50,
    setup="""
    () => {
        injectStyleOnce("dropdown", `
            :root { --dir: 1; --chevron-offset: 2px; }
            .dropdown { position: relative; font: 14px sans-serif; }
            .dropdown-toggle { position: absolute; opacity: 0; }
            .dropdown-label { display: flex; align-items: center; gap: 4px; }
            .chevron { display: inline-block; width: 8px; height: 8px; border-right: 2px solid; border-bottom: 2px solid; transform: translate(calc(var(--chevron-offset) * var(--dir)), 0) rotate(45deg); }
            .dropdown-toggle:checked ~ .dropdown-label .chevron { transform: translate(calc(-1 * var(--chevron-offset) * var(--dir)), 0) rotate(-135deg); }
            .dropdown-menu { display: none; list-style: none; margin: 0; padding: 0; }
            .dropdown-toggle:checked ~ .dropdown-menu { display: block; }
            .dropdown-menu li { padding-block: 4px; padding-inline: 8px; }
        `);
        let menu = "";
        for (let i = 0; i < 12; i++) menu += `<li><a href="#/s${i}">Section ${i}</a></li>`;
        let content = "";
        for (let i = 0; i < 40; i++) content += `<p>Article paragraph ${i} with some text to lay out in the page body.</p>`;
        sandbox().innerHTML = `<nav class="dropdown"><input id="dd" class="dropdown-toggle" type="checkbox"><label for="dd" class="dropdown-label">More<span class="chevron"></span></label><ul class="dropdown-menu">${menu}</ul></nav><main>${content}</main>`;
        return sandbox().querySelector("#dd");
    }""",
    mutate="""
    (toggle, k) => {
        toggle.click();
    }""")

TESTS["style/not-selector-invalidation.html"] = pipeline(
    "toggle 'completed' on one of 200 items under rules with :not(.completed), [data-priority] and child combinators (big-dom app.css shapes), then force layout", 30,
    setup="""
    () => {
        injectStyleOnce("not-rules", `
            .show-priority li[data-priority="3"]:not(.completed) { border-left: 4px solid orange; }
            .show-priority li[data-priority="4"]:not(.completed) > div > label { color: #b83f45; }
            .show-priority li.completed:not([data-priority="4"]) > div > label { opacity: 0.6; }
            .backlog-group li > div > :checked ~ label { color: green; }
            .timeline-group input:not([value=""]) ~ div > :last-child { color: blue; }
        `);
        const list = fillTodoList(buildList(0), 200);
        list.classList.add("show-priority");
        return list;
    }""",
    mutate="""
    (list, k) => {
        list.children[(k * 37) % 200].classList.toggle("completed");
    }""")

TESTS["style/body-class-unused.html"] = pipeline(
    "toggle a <body> class that no selector references over a 500-item list, then force layout", 50,
    setup="() => buildList(500)",
    mutate="""
    (list, k) => {
        document.body.classList.toggle("unused-state-class");
    }""")

TESTS["style/dir-attribute-switch.html"] = pipeline(
    "flip dir='rtl'/'ltr' on a container of 200 items styled with logical properties (padding-inline, margin-inline-start, inset-inline-start), then force layout (NewsSite language switch)", 10,
    setup="""
    () => {
        injectStyleOnce("logical", ".logical li { padding-inline: 12px 4px; margin-inline-start: 8px; position: relative; } .logical li::before { content: ''; position: absolute; inset-inline-start: 0; width: 4px; height: 4px; background: #333; }");
        const list = buildList(200);
        list.classList.add("logical");
        return list;
    }""",
    mutate="""
    (list, k) => {
        list.dir = k & 1 ? "ltr" : "rtl";
    }""")

TESTS["style/adopted-stylesheets-assign.html"] = micro(
    "attachShadow + adoptedStyleSheets = [global, item] for 200 new hosts (constructable stylesheets shared across components)", 10,
    setup="""
    () => {
        const global = new CSSStyleSheet();
        global.replaceSync(":host { display: block; } .x { color: red; } .y { margin: 2px; }");
        const item = new CSSStyleSheet();
        item.replaceSync("li { font-size: 24px; } li.completed label { text-decoration: line-through; }");
        sandbox().textContent = "";
        return { sheets: [global, item] };
    }""",
    run="""
    ({ sheets }, iters) => {
        let acc = 0;
        for (let k = 0; k < iters; k++) {
            sandbox().textContent = "";
            for (let i = 0; i < 200; i++) {
                const host = document.createElement("div");
                const root = host.attachShadow({ mode: "open" });
                root.adoptedStyleSheets = sheets;
                root.innerHTML = "<li><label>x</label></li>";
                sandbox().appendChild(host);
                acc += root.adoptedStyleSheets.length;
            }
            forceLayout();
        }
        if (acc !== 400 * iters) throw new Error("bad result");
    }""")

TESTS["style/insert-rule-then-layout.html"] = pipeline(
    "insertRule of a fresh class rule into a live sheet (CodeMirror StyleModule pattern) with 300 elements in the page, then force layout", 30,
    setup="""
    () => {
        let style = document.getElementById("dyn-sheet");
        if (!style) { style = document.createElement("style"); style.id = "dyn-sheet"; document.head.appendChild(style); }
        const sheet = style.sheet;
        while (sheet.cssRules.length) sheet.deleteRule(0);
        buildList(300);
        return sheet;
    }""",
    mutate="""
    (sheet, k) => {
        sheet.insertRule(`.gen${k} { color: rgb(${k & 255}, 0, 0); padding-left: ${k & 7}px; }`, sheet.cssRules.length);
    }""")

# ======================================================================================
# layout/ additions
# ======================================================================================

TESTS["layout/bounding-rect-after-move.html"] = micro(
    "move an absolutely positioned box via style.left/top, then getBoundingClientRect (forced layout) in a page with a 200-item list", 500,
    setup="""
    () => {
        buildList(200);
        let box = document.getElementById("abs-box");
        if (!box) { box = document.createElement("div"); box.id = "abs-box"; box.style.cssText = "position:absolute;width:50px;height:50px;background:#09f"; sandbox().appendChild(box); }
        forceLayout();
        return box;
    }""",
    run="""
    (box, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            box.style.left = (i % 200) + "px";
            box.style.top = ((i * 3) % 100) + "px";
            acc += box.getBoundingClientRect().left;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["layout/scroll-top-set-read.html"] = micro(
    "scrollTop = y then read scrollTop + scrollHeight of a 400-row overflow:auto scroller (NewsSite scrollTo, TipTap scrollTop = 0)", 2000,
    setup="""
    () => {
        sandbox().innerHTML = "<div style='height:300px;overflow:auto;font:14px sans-serif'></div>";
        const scroller = sandbox().firstChild;
        for (let i = 0; i < 400; i++) { const d = document.createElement("div"); d.style.height = "24px"; d.textContent = "Row " + i; scroller.appendChild(d); }
        forceLayout();
        return scroller;
    }""",
    run="""
    (scroller, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            scroller.scrollTop = (i * 97) % 5000;
            acc += scroller.scrollTop + scroller.scrollHeight;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["layout/window-scroll-to.html"] = micro(
    "window.scrollTo({top, behavior: 'instant'}) + scrollY read on a long page (NewsSite layout effect on navigation)", 2000,
    setup="""
    () => {
        sandbox().innerHTML = "<div style='height:20000px'></div>";
        forceLayout();
        return null;
    }""",
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            window.scrollTo({ top: (i * 131) % 10000, behavior: "instant" });
            acc += window.scrollY;
        }
        window.scrollTo(0, 0);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["layout/element-from-point.html"] = micro(
    "document.elementFromPoint hit testing over 300 inline-block cells with clean layout (CodeMirror/TipTap layout step)", 2000,
    setup="""
    () => {
        injectStyleOnce("hit-cells", ".hcell { display: inline-block; width: 40px; height: 20px; margin: 1px; }");
        sandbox().textContent = "";
        for (let i = 0; i < 300; i++) { const d = document.createElement("div"); d.className = "hcell"; sandbox().appendChild(d); }
        forceLayout();
        return null;
    }""",
    run="""
    (ctx, iters) => {
        let hits = 0;
        for (let i = 0; i < iters; i++) {
            const el = document.elementFromPoint(10 + (i * 37) % 600, 10 + (i * 11) % 120);
            if (el && el.className === "hcell") hits++;
        }
        if (!hits) throw new Error("bad result");
    }""")

TESTS["layout/grid-template-change.html"] = pipeline(
    "change grid-template-columns of a 120-item text grid, then force layout", 20,
    setup="""
    () => {
        sandbox().innerHTML = "<div style='display:grid;gap:4px;width:700px;font:13px sans-serif'></div>";
        const grid = sandbox().firstChild;
        for (let i = 0; i < 120; i++) { const d = document.createElement("div"); d.textContent = "Card " + i + " with a short headline"; grid.appendChild(d); }
        return grid;
    }""",
    mutate="""
    (grid, k) => {
        grid.style.gridTemplateColumns = ["repeat(3, 1fr)", "repeat(4, 1fr)", "200px 1fr 1fr", "repeat(auto-fill, minmax(150px, 1fr))"][k & 3];
    }""")

TESTS["layout/paragraph-text-replace.html"] = pipeline(
    "replace a 600px paragraph's text with a different ~400-char sentence (line breaking from scratch), then force layout", 50,
    setup="""
    () => {
        sandbox().innerHTML = "<p style='width:600px;font:16px/1.5 serif'></p>";
        const words = "the quick brown fox jumps over the lazy dog while the committee debates the merits of the new transit plan".split(" ");
        const texts = [];
        for (let t = 0; t < 16; t++) { const s = []; for (let w = 0; w < 70; w++) s.push(words[(t * 7 + w * 3) % words.length]); texts.push(s.join(" ")); }
        return { p: sandbox().firstChild, texts };
    }""",
    mutate="""
    ({ p, texts }, k) => {
        p.textContent = texts[k & 15];
    }""")

TESTS["layout/article-headings-reflow.html"] = pipeline(
    "change the width of an article with 6 headings and 30 paragraphs (~25k chars), then force layout (NewsSite article pages)", 10,
    setup="""
    () => {
        sandbox().innerHTML = "<article style='font:16px/1.5 serif'></article>";
        const article = sandbox().firstChild;
        const words = "the quick brown fox jumps over the lazy dog while the committee debates the merits of the new transit plan".split(" ");
        for (let i = 0; i < 30; i++) {
            if (i % 5 === 0) { const h = document.createElement("h2"); h.textContent = "Section heading number " + i; article.appendChild(h); }
            const s = []; for (let w = 0; w < 140; w++) s.push(words[(i * 7 + w * 3) % words.length]);
            const p = document.createElement("p"); p.textContent = s.join(" "); article.appendChild(p);
        }
        return article;
    }""",
    mutate="""
    (article, k) => {
        article.style.width = 500 + (k % 4) * 60 + "px";
    }""")

TESTS["layout/flex-item-text-change.html"] = pipeline(
    "change the text of one item in a 100-item wrapping flex row of variable-width text items, then force layout", 50,
    setup="""
    () => {
        sandbox().innerHTML = "<div style='display:flex;flex-wrap:wrap;gap:4px;width:700px;font:13px sans-serif'></div>";
        const row = sandbox().firstChild;
        for (let i = 0; i < 100; i++) { const d = document.createElement("div"); d.style.cssText = "flex:1 1 auto;padding:4px;border:1px solid #ddd"; d.textContent = "item " + i; row.appendChild(d); }
        return Array.from(row.children);
    }""",
    mutate="""
    (items, k) => {
        items[(k * 37) % 100].textContent = "item text " + "x".repeat(k % 20);
    }""")

TESTS["layout/offset-width-after-text.html"] = micro(
    "change a label's text then read its offsetWidth (measure-after-write in a 100-item list)", 300,
    setup="() => { const list = buildList(100); forceLayout(); return Array.from(list.querySelectorAll('label')); }",
    run="""
    (labels, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const label = labels[(i * 7) % 100];
            label.textContent = "Measured label " + i;
            acc += label.offsetWidth;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["layout/inline-client-rects.html"] = micro(
    "getClientRects of wrapped inline <span>s in a settled paragraph (tooltips, editors' line measurement)", 2000,
    setup="""
    () => {
        let html = "";
        for (let i = 0; i < 50; i++) html += `<span>wrapped inline span number ${i} with several words </span>`;
        sandbox().innerHTML = `<p style="width:300px;font:14px sans-serif">${html}</p>`;
        forceLayout();
        return Array.from(sandbox().querySelectorAll("span"));
    }""",
    run="""
    (spans, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += spans[i % 50].getClientRects().length;
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# svg/ additions
# ======================================================================================

TESTS["svg/plot-bars-with-titles.html"] = pipeline(
    "create 300 <rect> bars with x/y/width/height/fill attributes and a <title> child each (observable-plot barY), then force layout", 3,
    setup="() => makeSVG(0)",
    mutate="""
    (svg, k) => {
        svg.textContent = "";
        const g = document.createElementNS(SVG_NS, "g");
        g.setAttribute("fill", "steelblue");
        for (let i = 0; i < 300; i++) {
            const rect = document.createElementNS(SVG_NS, "rect");
            rect.setAttribute("x", String((i * 2) % 600));
            rect.setAttribute("y", String(300 - ((i * 13 + k) % 250)));
            rect.setAttribute("width", "1.5");
            rect.setAttribute("height", String((i * 13 + k) % 250));
            rect.setAttribute("fill", i & 1 ? "#4e79a7" : "#f28e2c");
            const title = document.createElementNS(SVG_NS, "title");
            title.textContent = "AK\\n" + i;
            rect.appendChild(title);
            g.appendChild(rect);
        }
        svg.appendChild(g);
    }""")

TESTS["svg/plot-dots-create.html"] = pipeline(
    "create 500 <circle> elements with cx/cy/r/fill-opacity attributes (observable-plot Dotted), then force layout", 3,
    setup="() => makeSVG(0)",
    mutate="""
    (svg, k) => {
        svg.textContent = "";
        const g = document.createElementNS(SVG_NS, "g");
        g.setAttribute("stroke", "currentColor");
        for (let i = 0; i < 500; i++) {
            const c = document.createElementNS(SVG_NS, "circle");
            c.setAttribute("cx", String((i * 37 + k) % 600));
            c.setAttribute("cy", String((i * 91) % 300));
            c.setAttribute("r", String(1 + (i % 7) ** 0.2 * 3));
            c.setAttribute("fill-opacity", "0.5");
            g.appendChild(c);
        }
        svg.appendChild(g);
    }""")

TESTS["svg/candlestick-rerender.html"] = pipeline(
    "React-Stockcharts pan: rewrite 150 candle bodies (rect x/y/height/class) and 150 wick paths (d), then force layout", 10,
    setup="""
    () => {
        const svg = makeSVG(0);
        const bodies = [], wicks = [];
        for (let i = 0; i < 150; i++) {
            const wick = document.createElementNS(SVG_NS, "path");
            wick.setAttribute("stroke", "#000");
            const body = document.createElementNS(SVG_NS, "rect");
            body.setAttribute("width", "2");
            svg.appendChild(wick); svg.appendChild(body);
            bodies.push(body); wicks.push(wick);
        }
        return { bodies, wicks };
    }""",
    mutate="""
    ({ bodies, wicks }, k) => {
        for (let i = 0; i < 150; i++) {
            const x = i * 4, open = 100 + ((i + k) * 37) % 80, close = 100 + ((i + k) * 53) % 80;
            bodies[i].setAttribute("x", String(x - 1));
            bodies[i].setAttribute("y", String(Math.min(open, close)));
            bodies[i].setAttribute("height", String(Math.abs(open - close) + 1));
            bodies[i].setAttribute("class", open > close ? "down" : "up");
            wicks[i].setAttribute("d", "M" + x + "," + (Math.min(open, close) - 10) + "L" + x + "," + (Math.max(open, close) + 10));
        }
    }""")

TESTS["svg/axis-ticks-create.html"] = pipeline(
    "create an axis: 40 tick <g transform> groups each with a <line> and a <text> label (Plot/d3-axis), then force layout", 10,
    setup="() => makeSVG(0)",
    mutate="""
    (svg, k) => {
        svg.textContent = "";
        const axis = document.createElementNS(SVG_NS, "g");
        axis.setAttribute("font-size", "10");
        axis.setAttribute("text-anchor", "middle");
        for (let i = 0; i < 40; i++) {
            const tick = document.createElementNS(SVG_NS, "g");
            tick.setAttribute("transform", `translate(${i * 15 + 0.5},0)`);
            const line = document.createElementNS(SVG_NS, "line");
            line.setAttribute("y2", "6");
            line.setAttribute("stroke", "currentColor");
            const text = document.createElementNS(SVG_NS, "text");
            text.setAttribute("y", "9");
            text.setAttribute("dy", "0.71em");
            text.textContent = ((i + k) * 2.5).toFixed(1);
            tick.append(line, text);
            axis.appendChild(tick);
        }
        svg.appendChild(axis);
    }""")

TESTS["svg/screen-ctm-mouse.html"] = micro(
    "convert mouse coordinates with svg.getScreenCTM().inverse() + DOMPoint.matrixTransform (chart crosshair hit testing)", 5000,
    setup="() => { const svg = makeSVG(10); forceLayout(); return svg; }",
    run="""
    (svg, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const point = new DOMPoint(100 + (i & 63), 50).matrixTransform(svg.getScreenCTM().inverse());
            acc += point.x;
        }
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# edit/ additions
# ======================================================================================

TESTS["edit/codemirror-lines-render.html"] = pipeline(
    "render 100 CodeMirror-style lines (div.cm-line with 8 token <span class>s each) into a pre-wrap contenteditable, then force layout", 5,
    setup="""
    () => {
        injectStyleOnce("cm", ".cm-content { white-space: pre-wrap; font: 13px monospace; width: 600px; } .tk-kw { color: #708; } .tk-def { color: #00f; } .tk-str { color: #a11; } .tk-num { color: #164; }");
        sandbox().innerHTML = "<div class='cm-content' contenteditable='true'></div>";
        return sandbox().firstChild;
    }""",
    mutate="""
    (content, k) => {
        content.textContent = "";
        const kinds = ["tk-kw", "tk-def", "", "tk-str", "", "tk-num", "", "tk-kw"];
        const words = ["function", "render", "(", "\\"item\\"", ",", String(k), ")", "return"];
        for (let line = 0; line < 100; line++) {
            const div = document.createElement("div");
            div.className = "cm-line";
            for (let t = 0; t < 8; t++) {
                if (kinds[t]) { const span = document.createElement("span"); span.className = kinds[t]; span.textContent = words[t] + " "; div.appendChild(span); }
                else div.appendChild(document.createTextNode(words[t] + " "));
            }
            content.appendChild(div);
        }
    }""")

TESTS["edit/tiptap-bold-all.html"] = pipeline(
    "wrap/unwrap the text of 100 paragraphs in <strong> (TipTap selectAll().setBold()), then force layout", 4,
    setup="""
    () => {
        sandbox().innerHTML = "<div contenteditable='true' style='width:600px;font:16px serif'></div>";
        const editor = sandbox().firstChild;
        for (let i = 0; i < 100; i++) { const p = document.createElement("p"); p.textContent = "Paragraph " + i + " of the long text, with enough words to wrap onto a second line in the editor."; editor.appendChild(p); }
        return editor;
    }""",
    mutate="""
    (editor, k) => {
        for (const p of editor.children) {
            if (k & 1) {
                const strong = p.firstChild;
                p.replaceChildren(...strong.childNodes);
            } else {
                const strong = document.createElement("strong");
                strong.append(...p.childNodes);
                p.appendChild(strong);
            }
        }
    }""")

TESTS["edit/contenteditable-mutation-observer.html"] = micro(
    "edit text nodes in a contenteditable observed by a characterData+childList MutationObserver; await record delivery per batch of 20 edits (ProseMirror/CodeMirror DOM observer)", 500,
    setup="""
    () => {
        sandbox().innerHTML = "<div contenteditable='true'></div>";
        const editor = sandbox().firstChild;
        for (let i = 0; i < 20; i++) { const p = document.createElement("p"); p.textContent = "line " + i; editor.appendChild(p); }
        const state = { records: 0, resolve: null };
        const observer = new MutationObserver((records) => { state.records += records.length; if (state.resolve) { const r = state.resolve; state.resolve = null; r(); } });
        observer.observe(editor, { characterData: true, childList: true, subtree: true, characterDataOldValue: true });
        return { texts: Array.from(editor.children, (p) => p.firstChild), state };
    }""",
    run="""
    async ({ texts, state }, iters) => {
        for (let k = 0; k < iters; k++) {
            const delivered = new Promise((resolve) => { state.resolve = resolve; });
            for (let i = 0; i < 20; i++) texts[i].data = "line " + i + " edit " + k;
            await delivered;
        }
        if (state.records !== 20 * iters) throw new Error("bad result " + state.records);
    }""")

TESTS["edit/selection-set-base-and-extent.html"] = micro(
    "getSelection().setBaseAndExtent across paragraphs of a focused contenteditable, reading anchorOffset/focusNode/rangeCount (ProseMirror selection sync)", 2000,
    setup="""
    () => {
        sandbox().innerHTML = "<div contenteditable='true' style='width:600px'></div>";
        const editor = sandbox().firstChild;
        for (let i = 0; i < 20; i++) { const p = document.createElement("p"); p.textContent = "Paragraph " + i + " has some editable text in it."; editor.appendChild(p); }
        editor.focus();
        return Array.from(editor.children, (p) => p.firstChild);
    }""",
    run="""
    (texts, iters) => {
        const selection = getSelection();
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const a = texts[i % 20], b = texts[(i + 3) % 20];
            selection.setBaseAndExtent(a, i % 10, b, (i % 7) + 1);
            acc += selection.anchorOffset + selection.rangeCount + (selection.focusNode === b ? 1 : 0);
        }
        if (!acc) throw new Error("bad result");
    }""")

# ======================================================================================
# parse/ additions
# ======================================================================================

TESTS["parse/domparser-tiptap-content.html"] = micro(
    "DOMParser.parseFromString of a ~6KB book chunk (section/h2/p/span lang/strong) and count elements (TipTap setContent)", 100,
    setup="""
    () => {
        let html = "";
        for (let i = 0; i < 12; i++)
            html += `<section><h2>Chapter ${i}</h2><p>${"It was the best of times, it was the worst of times, ".repeat(6)}<span lang="la">lorem ipsum ${i}</span> <strong>bold ${i}</strong></p></section>`;
        return html;
    }""",
    run="""
    (html, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += new DOMParser().parseFromString(html, "text/html").body.getElementsByTagName("*").length;
        if (acc !== 60 * iters) throw new Error("bad result " + acc);
    }""")

TESTS["parse/template-innerhtml-component.html"] = micro(
    "template.innerHTML = ~1.5KB component markup (with <style>) then content.cloneNode(true) (Perf-Dashboard ComponentBase htmlTemplate/cssTemplate)", 500,
    setup="""
    () => {
        let markup = "<style>:host{display:block} .pane{display:flex} .header{font-weight:bold}</style><div class='pane'>";
        for (let i = 0; i < 10; i++)
            markup += `<div class="row" id="row-${i}"><span class="header">Label ${i}</span><input type="text" value="v${i}"><button class="action" title="Do ${i}">Go</button><a href="#item-${i}">link</a></div>`;
        return markup + "</div>";
    }""",
    run="""
    (markup, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const t = document.createElement("template");
            t.innerHTML = markup;
            acc += t.content.cloneNode(true).childNodes.length;
        }
        if (acc !== 2 * iters) throw new Error("bad result");
    }""")

TESTS["parse/inner-html-svg-icon.html"] = micro(
    "innerHTML of a button containing an inline SVG icon with a long path 'd' (Spectrum/NewsSite icons)", 5000,
    setup="() => document.createElement(\"div\")",
    run="""
    (div, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            div.innerHTML = '<button class="spectrum-ActionButton"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" class="spectrum-Icon" focusable="false" aria-hidden="true"><path d="M9 1a8 8 0 1 0 8 8 8 8 0 0 0-8-8Zm-4.49 9.695A1.696 1.696 0 1 1 6.206 9a1.696 1.696 0 0 1-1.696 1.695Zm4.49 0A1.696 1.696 0 1 1 10.696 9V9A1.696 1.696 0 0 1 9 10.695Z"></path></svg><span>Item ' + (i & 7) + '</span></button>';
            acc += div.firstChild.childElementCount;
        }
        if (acc !== 2 * iters) throw new Error("bad result");
    }""")

# ======================================================================================
# shadow/ additions
# ======================================================================================

TESTS["shadow/closed-component-create.html"] = micro(
    "Perf-Dashboard ComponentBase: create a host, attachShadow({mode: 'closed'}), clone a cached template + <style> into it, query 3 elements by id", 2000,
    setup="""
    () => {
        const template = document.createElement("template");
        template.innerHTML = "<style>.pane{display:flex}</style><div class='pane'><h1 id='title'></h1><canvas id='chart' width=10 height=10></canvas><ul id='legend'></ul></div>";
        sandbox().textContent = "";
        return template;
    }""",
    run="""
    (template, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const host = document.createElement("div");
            const root = host.attachShadow({ mode: "closed" });
            root.appendChild(template.content.cloneNode(true));
            root.getElementById("title").textContent = "Chart " + i;
            acc += root.getElementById("chart") ? 1 : 0;
            acc += root.getElementById("legend") ? 1 : 0;
            if ((i & 63) === 0) sandbox().textContent = "";
            sandbox().appendChild(host);
        }
        if (acc !== 2 * iters) throw new Error("bad result");
    }""")

TESTS["shadow/lit-element-update.html"] = micro(
    "Lit-style reactive update: property setter queues requestUpdate on a microtask; await updateComplete; render patches a text node and class inside the shadow root", 1,
    setup="""
    () => {
        if (!window.MiniLit) {
            window.MiniLit = class extends HTMLElement {
                constructor() { super(); this._text = ""; this._done = false; this._pending = null; this.root = this.attachShadow({ mode: "open" }); this.root.innerHTML = "<li><label></label></li>"; this.li = this.root.firstChild; this.label = this.li.firstChild; }
                set text(v) { this._text = v; this.requestUpdate(); }
                set done(v) { this._done = v; this.requestUpdate(); }
                requestUpdate() { if (!this._pending) this._pending = Promise.resolve().then(() => { this._pending = null; this.update(); }); }
                get updateComplete() { return this._pending || Promise.resolve(); }
                update() { this.label.textContent = this._text; this.li.className = this._done ? "completed" : ""; }
            };
            customElements.define("mini-lit", window.MiniLit);
        }
        sandbox().textContent = "";
        const items = [];
        for (let i = 0; i < 100; i++) { const el = document.createElement("mini-lit"); sandbox().appendChild(el); items.push(el); }
        return items;
    }""",
    run="""
    async (items, iters) => {
        for (let round = 0; round < 100; round++) {
            for (let i = 0; i < 100; i++) { items[i].text = "todo " + i + " r" + round; items[i].done = (i + round) & 1; }
            await Promise.all(items.map((item) => item.updateComplete));
        }
        if (!items[5].label.textContent.endsWith("r99")) throw new Error("bad result");
    }""")

# ======================================================================================
# timers/ additions
# ======================================================================================

TESTS["timers/debounce-settimeout.html"] = micro(
    "debounce: clearTimeout + setTimeout(fn, 0) 5000 times, then wait for the one surviving callback (Backbone _.debounce(render, 0))", 1,
    run="""
    (ctx, iters) => new Promise((resolve) => {
        let timer = 0, fired = 0;
        for (let i = 0; i < 5000; i++) {
            clearTimeout(timer);
            timer = setTimeout(() => { fired++; resolve(); }, 0);
        }
    })""")

TESTS["timers/async-await-nested.html"] = micro(
    "async function awaiting another async function (2 awaits deep), 10000 calls in sequence", 1,
    run="""
    async (ctx, iters) => {
        const leaf = async (x) => { await null; return x + 1; };
        const mid = async (x) => (await leaf(x)) * 2;
        let acc = 0;
        for (let i = 0; i < 10000; i++) acc += await mid(i & 7);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["timers/promise-then-fanout.html"] = micro(
    "50000 .then callbacks attached to one pending promise, then resolve it (store subscriptions, nextTick queues)", 1,
    run="""
    async (ctx, iters) => {
        let resolve;
        const p = new Promise((r) => { resolve = r; });
        let acc = 0;
        const all = [];
        for (let i = 0; i < 50000; i++) all.push(p.then((v) => { acc += v; }));
        resolve(1);
        await Promise.all(all);
        if (acc !== 50000) throw new Error("bad result");
    }""")

# ======================================================================================
# js/ additions — idioms the Speedometer framework and chart code leans on.
# ======================================================================================

TESTS["js/property-polymorphic.html"] = micro(
    "read 'id' and 'value' from objects of 4 different shapes at one site (vnode/fiber kinds)", 200000,
    setup="""
    () => {
        const objects = [];
        for (let i = 0; i < 400; i++) {
            switch (i & 3) {
            case 0: objects.push({ id: i, value: 1 }); break;
            case 1: objects.push({ kind: "b", id: i, value: 2 }); break;
            case 2: objects.push({ x: 0, y: 0, id: i, value: 3 }); break;
            default: objects.push({ value: 4, id: i, extra: null, more: true });
            }
        }
        return objects;
    }""",
    run="""
    (objects, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) { const o = objects[i % 400]; acc += o.id + o.value; }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/property-megamorphic.html"] = micro(
    "read 'id' from objects of 32 different shapes at one site (generic framework code over many prop shapes)", 200000,
    setup="""
    () => {
        const objects = [];
        for (let i = 0; i < 640; i++) { const o = {}; o["k" + (i % 32)] = i; o.id = i; objects.push(o); }
        return objects;
    }""",
    run="""
    (objects, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += objects[i % 640].id;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/call-apply.html"] = micro(
    "fn.call(ctx, a, b), fn.apply(ctx, [a, b]) and fn.apply(ctx, arguments) forwarding (Backbone/jQuery event triggering)", 50000,
    setup="""
    () => {
        const ctx = { base: 3 };
        function add(a, b) { return this.base + a + b; }
        function forward() { return add.apply(ctx, arguments); }
        return { ctx, add, forward };
    }""",
    run="""
    ({ ctx, add, forward }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += add.call(ctx, i & 7, 1) + add.apply(ctx, [i & 3, 2]) + forward(i & 1, 3);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/bind-call.html"] = micro(
    "Function.prototype.bind (fresh every 16th call, with a bound argument) and calls through bound functions (React class handlers, _.bindAll)", 100000,
    setup="""
    () => {
        const obj = { x: 2, get(y) { return this.x + y; } };
        return { obj, bound: obj.get.bind(obj) };
    }""",
    run="""
    ({ obj, bound }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            acc += bound(i & 7);
            if ((i & 15) === 0) acc += obj.get.bind(obj, 1)();
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/arguments-object.html"] = micro(
    "functions reading arguments.length/arguments[i] and Array.prototype.slice.call(arguments) (jQuery/Underscore/Backbone)", 50000,
    setup="""
    () => {
        function variadic() { let s = arguments.length; for (let i = 0; i < arguments.length; i++) s += arguments[i]; return s; }
        function sliced() { return Array.prototype.slice.call(arguments, 1).length; }
        return { variadic, sliced };
    }""",
    run="""
    ({ variadic, sliced }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += variadic(i & 3, 1, 2) + sliced(1, 2, i & 1);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/private-fields.html"] = micro(
    "class with #private fields and a #private method used through public methods (TodoMVC-WebComponents #data/#elements)", 100000,
    setup="""
    () => class Store {
        #items = [];
        #count = 0;
        #bump() { this.#count++; }
        add(x) { this.#items.push(x); this.#bump(); if (this.#items.length > 64) this.#items.length = 0; }
        get count() { return this.#count; }
    }""",
    run="""
    (Store, iters) => {
        const store = new Store();
        for (let i = 0; i < iters; i++) store.add(i);
        if (store.count !== iters) throw new Error("bad result");
    }""")

TESTS["js/in-hasown-delete.html"] = micro(
    "'key' in obj, Object.hasOwn, hasOwnProperty.call and delete on a dictionary-like object (props diffing, caches)", 50000,
    setup="() => { const keys = []; for (let i = 0; i < 32; i++) keys.push(\"p\" + i); return keys; }",
    run="""
    (keys, iters) => {
        const dict = {};
        let hits = 0;
        for (let i = 0; i < iters; i++) {
            const k = keys[i & 31];
            if (k in dict) hits++;
            if (Object.hasOwn(dict, k)) hits++;
            if (Object.prototype.hasOwnProperty.call(dict, k)) delete dict[k]; else dict[k] = i;
        }
        if (!hits) throw new Error("bad result");
    }""")

TESTS["js/object-assign-merge.html"] = micro(
    "Object.assign({}, defaults, props) with 6 default and 3 override properties (Chart.js/Plot option merging, Lit todos.update)", 50000,
    setup="""
    () => {
        const defaults = { color: "red", width: 1, visible: true, label: "", order: 0, stack: null };
        const props = [];
        for (let i = 0; i < 16; i++) props.push({ width: i, label: "l" + i, order: i * 2 });
        return { defaults, props };
    }""",
    run="""
    ({ defaults, props }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += Object.assign({}, defaults, props[i & 15]).order;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/object-freeze-create.html"] = micro(
    "create small objects and arrays and Object.freeze them, then read through them (ProseMirror/TipTap immutable nodes and marks)", 50000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const attrs = Object.freeze({ level: i & 3, id: null });
            const marks = Object.freeze([attrs]);
            acc += marks[0].level + (Object.isFrozen(marks) ? 1 : 0);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/entries-from-entries.html"] = micro(
    "Object.fromEntries(Object.entries(obj).map(...)) remapping an 8-property object (Plot channels, Redux selectors)", 20000,
    setup="() => ({ a: 1, b: 2, c: 3, d: 4, e: 5, f: 6, g: 7, h: 8 })",
    run="""
    (obj, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, v * (i & 3)])).h;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/sort-objects-by-string.html"] = micro(
    "sort a fresh copy of 100 objects with a comparator on a number then a string key (d3/Plot sort, Perf-Dashboard series)", 500,
    setup="""
    () => {
        const rows = [];
        for (let i = 0; i < 100; i++) rows.push({ value: (i * 7919) % 50, name: "airport" + ((i * 104729) % 1000) });
        return rows;
    }""",
    run="""
    (rows, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const sorted = rows.slice().sort((a, b) => a.value - b.value || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
            acc += sorted[(i * 7) % 100].value;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/array-from-map-fn.html"] = micro(
    "Array.from(arrayLike, mapFn) and [...set] on 32-element sources (Array.from(nodeList), [...new Set()])", 20000,
    setup="""
    () => {
        const set = new Set();
        const arrayLike = { length: 32 };
        for (let i = 0; i < 32; i++) { set.add(i * 3); arrayLike[i] = i; }
        return { set, arrayLike };
    }""",
    run="""
    ({ set, arrayLike }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += [...set][i & 31] + Array.from(arrayLike, (v) => v * 2)[(i * 5) & 31];
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/slice-concat-flat.html"] = micro(
    "slice, concat and flat on small arrays (immutable list updates, Plot channel concatenation)", 50000,
    setup="() => ({ a: Array.from({ length: 24 }, (_, i) => i), b: [100, 101, 102, 103], nested: [[1, 2], [3, [4, 5]], [6]] })",
    run="""
    ({ a, b, nested }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += a.slice(i & 7, 20).length + a.concat(b).length + nested.flat().length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/find-index-splice.html"] = micro(
    "findIndex by id + splice(index, 1) + splice back in, on a 100-todo array (Lit/Angular/Svelte delete)", 10000,
    setup="() => Array.from({ length: 100 }, (_, i) => ({ id: \"t\" + i, completed: false }))",
    run="""
    (todos, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const id = "t" + ((i * 7) % 100);
            const index = todos.findIndex((t) => t.id === id);
            const [removed] = todos.splice(index, 1);
            todos.splice(index, 0, removed);
            acc += index;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/todo-derived-state.html"] = micro(
    "TodoMVC derived state over 100 todos: filter(!completed).length, every(completed), some(completed), find(id) per op", 5000,
    setup="() => Array.from({ length: 100 }, (_, i) => ({ id: i, title: todoTitle(i), completed: i % 3 === 0 }))",
    run="""
    (todos, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            todos[i % 100].completed = !todos[i % 100].completed;
            acc += todos.filter((t) => !t.completed).length + (todos.every((t) => t.completed) ? 1 : 0) + (todos.some((t) => t.completed) ? 1 : 0) + todos.find((t) => t.id === (i % 100)).id;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/intl-number-format.html"] = micro(
    "Intl.NumberFormat.format with cached formatters (unit kilometer; grouping) (Charts-chartjs ticks)", 5000,
    setup="() => ({ unit: new Intl.NumberFormat(\"en-US\", { style: \"unit\", unit: \"kilometer\", maximumFractionDigits: 1 }), plain: new Intl.NumberFormat(\"en-US\") })",
    run="""
    ({ unit, plain }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += unit.format(i * 12.5).length + plain.format(i * 1001).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/to-locale-string.html"] = micro(
    "Number.prototype.toLocaleString and Date.prototype.toLocaleDateString without cached formatters (dashboards, tooltips)", 500,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += (i * 1234.5).toLocaleString("en-US") .length + new Date(Date.UTC(2020, i % 12, 1 + (i % 28))).toLocaleDateString("en-US").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/date-parse-ymd.html"] = micro(
    "parse 'YYYY-MM-DD' with a regexp into Date.UTC, then read UTC fields (React-Stockcharts timeParse over data.tsv)", 20000,
    setup="""
    () => {
        const strings = [];
        for (let i = 0; i < 365; i++) strings.push(new Date(Date.UTC(2010, 0, 1 + i)).toISOString().slice(0, 10));
        return strings;
    }""",
    run="""
    (strings, iters) => {
        const re = /^(\\d{4})-(\\d{2})-(\\d{2})$/;
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const m = re.exec(strings[i % 365]);
            const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
            acc += d.getUTCFullYear() + d.getUTCMonth() + d.getUTCDate();
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/date-string-parse.html"] = micro(
    "new Date(string) parsing of ISO and RFC-ish date strings + getTime (Perf-Dashboard data, chart CSVs)", 20000,
    setup="() => [\"2021-03-04T05:06:07Z\", \"2021-03-04\", \"Thu, 04 Mar 2021 05:06:07 GMT\", \"2021-03-04T05:06:07.123+02:00\"]",
    run="""
    (strings, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += new Date(strings[i & 3]).getTime() % 1000;
        if (Number.isNaN(acc)) throw new Error("bad result");
    }""")

TESTS["js/typed-array-subarray-set.html"] = micro(
    "Float64Array element writes plus subarray() + set() block copies (Plot/d3 channel arrays)", 50000,
    setup="() => ({ src: new Float64Array(256).map((_, i) => i * 0.5), dst: new Float64Array(512) })",
    run="""
    ({ src, dst }, iters) => {
        let acc = 0;
        for (let k = 0; k < iters; k++) {
            src[k & 255] = k & 1023;
            dst.set(src.subarray(k & 127, (k & 127) + 64), k & 255);
            acc += dst[(k * 3) & 511];
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/recursive-vnode-walk.html"] = micro(
    "recursive walk of a 4-ary, 5-level object tree (341 nodes) summing values (virtual DOM render/diff recursion)", 2000,
    setup="""
    () => {
        const make = (depth) => { const node = { tag: "div", children: [], value: depth }; if (depth > 0) for (let i = 0; i < 4; i++) node.children.push(make(depth - 1)); return node; };
        return make(4);
    }""",
    run="""
    (tree, iters) => {
        const walk = (node) => { let s = node.value; const c = node.children; for (let i = 0; i < c.length; i++) s += walk(c[i]); return s; };
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += walk(tree);
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/for-of-entries-destructure.html"] = micro(
    "for (const [i, v] of array.entries()) and for (const [k, v] of map) with destructuring (Lit repeat, Vue renderList)", 10000,
    setup="""
    () => {
        const array = Array.from({ length: 32 }, (_, i) => i);
        const map = new Map(array.map((i) => ["k" + i, i]));
        return { array, map };
    }""",
    run="""
    ({ array, map }, iters) => {
        let acc = 0;
        for (let k = 0; k < iters; k++) {
            for (const [i, v] of array.entries()) if (i === (k & 31)) acc += v;
            for (const [key, v] of map) if (v === 3) acc += key.length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/instanceof-checks.html"] = micro(
    "instanceof against a 3-level class hierarchy and built-ins (ProseMirror Node/Mark checks, Plot mark dispatch)", 200000,
    setup="""
    () => {
        class Base {} class Mid extends Base {} class Leaf extends Mid {}
        const values = [new Leaf(), new Mid(), new Base(), [], {}, new Map(), "s", 1];
        return { values, Base, Mid, Leaf };
    }""",
    run="""
    ({ values, Base, Mid, Leaf }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const v = values[i & 7];
            if (v instanceof Leaf) acc += 3; else if (v instanceof Mid) acc += 2; else if (v instanceof Base) acc += 1; else if (v instanceof Array) acc += 4; else if (v instanceof Map) acc += 5;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/optional-chaining-nullish.html"] = micro(
    "optional chaining a?.b?.c, optional calls fn?.() and ?? defaults over sparse option objects (modern framework/build output)", 200000,
    setup="""
    () => [{ a: { b: { c: 1 } }, fn: () => 2 }, { a: null }, { a: { b: null }, fn: null }, {}, { a: { b: { c: 0 } }, d: 5 }]
    """,
    run="""
    (objects, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const o = objects[i % 5];
            acc += (o.a?.b?.c ?? 7) + (o.fn?.() ?? 1) + (o.d ?? 0);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/reducer-switch.html"] = micro(
    "Redux-style reducer: switch on action.type strings returning new state objects (React-Redux TodoMVC)", 200000,
    setup="""
    () => {
        const types = ["ADD_TODO", "TOGGLE_TODO", "DELETE_TODO", "EDIT_TODO", "SET_FILTER", "CLEAR_COMPLETED", "UNKNOWN"];
        return types.map((type, i) => ({ type, id: i, text: "t" + i, filter: "all" }));
    }""",
    run="""
    (actions, iters) => {
        let state = { count: 0, filter: "all", last: null };
        for (let i = 0; i < iters; i++) {
            const action = actions[i % 7];
            switch (action.type) {
            case "ADD_TODO": state = { ...state, count: state.count + 1, last: action.text }; break;
            case "TOGGLE_TODO": state = { ...state, last: action.id }; break;
            case "DELETE_TODO": state = { ...state, count: state.count - 1 }; break;
            case "EDIT_TODO": state = { ...state, last: action.text }; break;
            case "SET_FILTER": state = { ...state, filter: action.filter }; break;
            case "CLEAR_COMPLETED": state = { ...state, count: state.count }; break;
            default: break;
            }
        }
        if (state.count !== 0 && !state.last) throw new Error("bad result");
    }""")

TESTS["js/symbol-keyed-props.html"] = micro(
    "get/set of Symbol-keyed properties on objects (Lit/Vue internal markers, React $$typeof checks)", 200000,
    setup="""
    () => {
        const marker = Symbol("marker"), raw = Symbol.for("__v_raw");
        const objects = Array.from({ length: 64 }, (_, i) => ({ id: i, [marker]: i & 1, [raw]: null }));
        return { objects, marker, raw };
    }""",
    run="""
    ({ objects, marker, raw }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const o = objects[i & 63];
            acc += o[marker];
            o[raw] = i & 1 ? o : null;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/hooks-state-cells.html"] = micro(
    "React hooks emulation: per-render cursor into a state-cell array, useState returning [value, setter] tuples, useMemo dependency comparison", 20000,
    setup="""
    () => {
        const cells = [];
        let cursor = 0;
        const useState = (init) => { const i = cursor++; if (cells.length <= i) cells.push(init); return [cells[i], (v) => { cells[i] = v; }]; };
        const useMemo = (fn, deps) => { const i = cursor++; const prev = cells[i]; if (prev && prev.deps.length === deps.length && prev.deps.every((d, k) => d === deps[k])) return prev.value; const value = fn(); cells[i] = { deps, value }; return value; };
        const render = (props) => {
            cursor = 0;
            const [count, setCount] = useState(0);
            const [text] = useState("todo");
            const label = useMemo(() => text + " " + props.id, [text, props.id]);
            setCount(count + 1);
            return label.length + count;
        };
        return render;
    }""",
    run="""
    (render, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) acc += render({ id: i & 7 });
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/linear-scale-ticks.html"] = micro(
    "d3-scale linear ticks: tickIncrement via Math.log10/pow/floor, then generate and map ticks through the scale (Plot/Stockcharts axes)", 20000,
    run="""
    (ctx, iters) => {
        const tickIncrement = (start, stop, count) => {
            const step = (stop - start) / Math.max(0, count), power = Math.floor(Math.log10(step)), error = step / Math.pow(10, power);
            const f = error >= 7.07 ? 10 : error >= 3.16 ? 5 : error >= 1.41 ? 2 : 1;
            return power >= 0 ? f * Math.pow(10, power) : -Math.pow(10, -power) / f;
        };
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const lo = i % 50, hi = 1000 + (i % 997);
            const inc = tickIncrement(lo, hi, 10);
            const r0 = Math.ceil(lo / inc), r1 = Math.floor(hi / inc);
            for (let r = r0; r <= r1; r++) acc += ((r * inc - lo) / (hi - lo)) * 600;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/binary-search.html"] = micro(
    "bisect (binary search) into a sorted 2000-element Float64 time array (Perf-Dashboard TimeSeries, Stockcharts xAccessor)", 100000,
    setup="() => Float64Array.from({ length: 2000 }, (_, i) => 1e12 + i * 86400000)",
    run="""
    (times, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const x = 1e12 + ((i * 7919) % 2000) * 86400000 + 1;
            let lo = 0, hi = times.length;
            while (lo < hi) { const mid = (lo + hi) >>> 1; if (times[mid] < x) lo = mid + 1; else hi = mid; }
            acc += lo;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/csv-parse-rows.html"] = micro(
    "d3-dsv csvParse + autoType: split a 200-row CSV into lines and fields, build row objects keyed by header, convert numeric fields (observable-plot/chartjs #prepare)", 60,
    setup="""
    () => {
        let csv = "iata,name,city,state,country,latitude,longitude\\n";
        for (let i = 0; i < 200; i++) csv += `A${i},Airport ${i},City ${i % 37},S${i % 50},USA,${(30 + i / 10).toFixed(4)},${(-80 - i / 10).toFixed(4)}\\n`;
        return csv;
    }""",
    run="""
    (csv, iters) => {
        let acc = 0;
        for (let k = 0; k < iters; k++) {
            const lines = csv.split("\\n");
            const header = lines[0].split(",");
            const rows = [];
            for (let i = 1; i < lines.length; i++) {
                if (!lines[i]) continue;
                const fields = lines[i].split(",");
                const row = {};
                for (let c = 0; c < header.length; c++) { const v = fields[c]; const n = +v; row[header[c]] = v !== "" && !Number.isNaN(n) ? n : v; }
                rows.push(row);
            }
            acc += rows.length + rows[5].latitude;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/number-format-si.html"] = micro(
    "d3-format '.2s'/',': toExponential/toPrecision + SI prefix selection + thousands grouping by string slicing (Plot/Stockcharts axis labels)", 20000,
    run="""
    (ctx, iters) => {
        const prefixes = ["y", "z", "a", "f", "p", "n", "µ", "m", "", "k", "M", "G", "T", "P", "E", "Z", "Y"];
        const si = (x) => { const e = Math.max(-8, Math.min(8, Math.floor(Math.log10(Math.abs(x)) / 3))); return (x / Math.pow(10, e * 3)).toPrecision(2) + prefixes[8 + e]; };
        const group = (x) => { const s = String(Math.round(x)); let out = ""; for (let i = 0; i < s.length; i++) { if (i && (s.length - i) % 3 === 0) out += ","; out += s[i]; } return out; };
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const v = (i * 7919.13) % 1e7 + 1;
            acc += si(v).length + group(v).length;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/string-starts-includes.html"] = micro(
    "indexOf/slice/startsWith/endsWith/includes on hash-route strings (NewsSite routing, jQuery selector fast paths)", 50000,
    setup="() => Array.from({ length: 64 }, (_, i) => `#/section/${[\"us\", \"world\", \"politics\", \"business\"][i & 3]}/article-${i}?ref=nav`)",
    run="""
    (urls, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const u = urls[i & 63];
            const path = u.slice(2, u.indexOf("?"));
            acc += path.length + (u.startsWith("#/section/w") ? 1 : 0) + (path.endsWith("-7") ? 1 : 0) + (u.includes("politics") ? 1 : 0);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/char-code-scan.html"] = micro(
    "hand-written tokenizer loop classifying characters with charCodeAt over 64-char source lines (Lezer/CodeMirror, d3-dsv)", 10000,
    setup="() => Array.from({ length: 64 }, (_, i) => `function f${i}(a, b) { return a + b * ${i} - Math.max(a, ${i * 3}); } // note`)",
    run="""
    (lines, iters) => {
        let idents = 0;
        for (let k = 0; k < iters; k++) {
            const s = lines[k & 63];
            let inIdent = false;
            for (let i = 0; i < s.length; i++) {
                const c = s.charCodeAt(i);
                const isIdent = (c >= 97 && c <= 122) || (c >= 65 && c <= 90) || c === 95 || (inIdent && c >= 48 && c <= 57);
                if (isIdent && !inIdent) idents++;
                inIdent = isIdent;
            }
        }
        if (!idents) throw new Error("bad result");
    }""")

TESTS["js/string-key-compare.html"] = micro(
    "=== and < on equal-length strings differing late, plus comparison against freshly concatenated keys (keyed diffing, sort comparators)", 100000,
    setup="""
    () => {
        const a = [], b = [];
        for (let i = 0; i < 64; i++) { a.push("todo-item-key-" + (1000 + i)); b.push("todo-item-key-" + (1000 + ((i * 7) & 63))); }
        return { a, b };
    }""",
    run="""
    ({ a, b }, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const x = a[i & 63], y = b[i & 63];
            if (x === y) acc++;
            if (x < y) acc += 2;
            if ("todo-item-key-" + (1000 + (i & 63)) === x) acc += 3;
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/trim-case-unicode.html"] = micro(
    "trim + toLowerCase + toUpperCase of short strings mixing ASCII, Japanese and Cyrillic (todo input handling)", 50000,
    setup="() => Array.from({ length: 64 }, (_, i) => \"  \" + todoTitle(i) + \" Item  \")",
    run="""
    (inputs, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const s = inputs[i & 63];
            acc += s.trim().length + s.toLowerCase().length + ((i & 7) ? 0 : s.toUpperCase().length);
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/escape-html-chain.html"] = micro(
    "HTML-escape with 6 chained .replace(/x/g, entity) calls, mostly on strings with nothing to escape (TodoMVC escapeForHTML, _.escape)", 20000,
    setup="() => Array.from({ length: 64 }, (_, i) => i % 8 === 0 ? `Buy <milk> & \\\"eggs\\\" #${i}` : todoTitle(i))",
    run="""
    (inputs, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += inputs[i & 63].replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;").replace(/`/g, "&#x60;").length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/pad-repeat.html"] = micro(
    "padStart/padEnd/repeat building fixed-width labels and dates (date formatting, ascii tables)", 100000,
    run="""
    (ctx, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++)
            acc += String(i % 12 + 1).padStart(2, "0").length + String(i & 1023).padEnd(6, ".").length + "-".repeat(i & 7).length;
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/regex-exec-global-tokenize.html"] = micro(
    "tokenize JS lines with a global alternation regexp in an exec() loop (template compilers, legacy highlighters)", 2000,
    setup="() => Array.from({ length: 32 }, (_, i) => `const value${i} = compute(${i}, \\\"str${i}\\\") + other.prop[${i & 3}]; // note`)",
    run="""
    (lines, iters) => {
        const re = /([A-Za-z_$][\\w$]*)|(\\d+(?:\\.\\d+)?)|("(?:[^"\\\\]|\\\\.)*")|(\\/\\/.*$)|([^\\s\\w])/g;
        let tokens = 0;
        for (let k = 0; k < iters; k++) {
            const s = lines[k & 31];
            re.lastIndex = 0;
            let m;
            while ((m = re.exec(s)) !== null) tokens += m[1] ? 2 : 1;
        }
        if (!tokens) throw new Error("bad result");
    }""")

TESTS["js/regex-sticky-lexer.html"] = micro(
    "lexer trying 5 sticky /y regexps at each position (Lezer external tokenizers, marked, template compilers)", 2000,
    setup="() => Array.from({ length: 32 }, (_, i) => `let x${i} = foo(bar, ${i * 17}) + \\\"s\\\" + baz.qux;`)",
    run="""
    (lines, iters) => {
        const rules = [/\\s+/y, /[A-Za-z_$][\\w$]*/y, /\\d+/y, /"[^"]*"/y, /[=+(),.;]/y];
        let tokens = 0;
        for (let k = 0; k < iters; k++) {
            const s = lines[k & 31];
            let pos = 0;
            while (pos < s.length) {
                let matched = false;
                for (const re of rules) { re.lastIndex = pos; const m = re.exec(s); if (m) { pos += m[0].length; tokens++; matched = true; break; } }
                if (!matched) pos++;
            }
        }
        if (!tokens) throw new Error("bad result");
    }""")

TESTS["js/regex-replace-callback.html"] = micro(
    "replace(/\\{\\{(\\w+)\\}\\}/g, (_, key) => values[key]) template interpolation of a todo item template", 10000,
    setup="""
    () => ({
        template: '<li data-id="{{id}}" class="{{completed}}"><div class="view"><input class="toggle" type="checkbox" {{checked}}><label>{{title}}</label><button class="destroy"></button></div></li>',
        values: Array.from({ length: 32 }, (_, i) => ({ id: i, completed: i & 1 ? "completed" : "", checked: i & 1 ? "checked" : "", title: todoTitle(i) })),
    })""",
    run="""
    ({ template, values }, iters) => {
        const re = /\\{\\{(\\w+)\\}\\}/g;
        let acc = 0;
        for (let i = 0; i < iters; i++) { const v = values[i & 31]; acc += template.replace(re, (_, key) => v[key]).length; }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/regex-match-groups.html"] = micro(
    "str.match with capture groups and named groups (?<y>...) on rgb() colors and dates (d3-color parsing, timeParse)", 20000,
    setup="() => Array.from({ length: 64 }, (_, i) => i & 1 ? `rgb(${i}, ${(i * 2) & 255}, ${(i * 3) & 255})` : `2010-${String((i % 12) + 1).padStart(2, \"0\")}-${String((i % 28) + 1).padStart(2, \"0\")}`)",
    run="""
    (inputs, iters) => {
        const reColor = /^rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)$/;
        const reDate = /^(?<y>\\d{4})-(?<m>\\d{2})-(?<d>\\d{2})$/;
        let acc = 0;
        for (let i = 0; i < iters; i++) {
            const s = inputs[i & 63];
            const c = s.match(reColor);
            if (c) acc += +c[1] + +c[3]; else { const d = s.match(reDate); acc += +d.groups.m + +d.groups.d; }
        }
        if (!acc) throw new Error("bad result");
    }""")

TESTS["js/json-roundtrip-small.html"] = micro(
    "JSON.parse(JSON.stringify(state)) deep clone of a small nested state object (ES5 TodoMVC store, toJSON snapshots)", 10000,
    setup="() => ({ filter: \"all\", editing: null, todos: [{ id: 1, title: \"a\", completed: false }, { id: 2, title: \"b\", completed: true }], meta: { version: 3, tags: [\"x\", \"y\"] } })",
    run="""
    (state, iters) => {
        let acc = 0;
        for (let i = 0; i < iters; i++) { state.meta.version = i & 15; acc += JSON.parse(JSON.stringify(state)).todos.length; }
        if (acc !== 2 * iters) throw new Error("bad result");
    }""")

TESTS["js/json-store-update.html"] = micro(
    "ES5 TodoMVC store.update: JSON.parse the whole 100-todo store string, find + modify one todo, JSON.stringify it back", 200,
    setup="() => JSON.stringify({ todos: Array.from({ length: 100 }, (_, i) => ({ id: i, title: todoTitle(i), completed: false })) })",
    run="""
    (initial, iters) => {
        let stored = initial;
        for (let i = 0; i < iters; i++) {
            const data = JSON.parse(stored);
            const todo = data.todos.find((t) => t.id === (i * 7) % 100);
            todo.completed = !todo.completed;
            stored = JSON.stringify(data);
        }
        if (stored.length < initial.length) throw new Error("bad result");
    }""")


# ======================================================================================
# StyleBench-derived: reduced from the StyleBench steps and suite setup where Chromium was
# faster. Each isolates one workload.
# ======================================================================================

TESTS["style/remove-wide-hidden-container.html"] = micro(
    "remove a display:none container of 4000 child divs, then force style (cost grows with the square of the child count)", 1,
    setup="""
    () => {
        sandbox().style.display = "none";
        sandbox().textContent = "";
        const container = document.createElement("div");
        for (let i = 0; i < 4000; i++)
            container.appendChild(document.createElement("div"));
        sandbox().appendChild(container);
        forceLayout();
        return container;
    }""",
    run="""
    (container) => {
        container.remove();
        forceLayout();
        if (sandbox().firstChild) throw new Error("bad result");
    }""")

TESTS["style/insert-under-display-none.html"] = micro(
    "insert a container of 5000 child divs into a display:none parent, then force style + layout (nothing renders)", 1,
    setup="""
    () => {
        sandbox().style.display = "none";
        sandbox().textContent = "";
        forceLayout();
        const container = document.createElement("div");
        for (let i = 0; i < 5000; i++)
            container.appendChild(document.createElement("div"));
        return container;
    }""",
    run="""
    (container) => {
        sandbox().appendChild(container);
        forceLayout();
        if (sandbox().firstChild !== container) throw new Error("bad result");
    }""")

TESTS["style/initial-style-5000-elements.html"] = micro(
    "insert a StyleBench-shaped 5000-element tree whose elements are all display:contents, then force style (style only: no boxes, no author rules)", 1,
    setup="""
    () => {
        injectStyleOnce("contents", "#sandbox * { display: contents; }");
        sandbox().textContent = "";
        forceLayout();
        return makeInlineBlockTree(5000);
    }""",
    run="""
    (tree) => {
        sandbox().appendChild(tree);
        forceLayout();
        if (sandbox().firstChild !== tree) throw new Error("bad result");
    }""")

TESTS["style/insert-5000-rule-sheet-then-layout.html"] = micro(
    "insert a 5000-rule sheet of StyleBench-style descendant/child selectors over a 100-item list, force layout, remove it, force layout", 2,
    setup="() => { buildList(100); return makeRuleSheetText(5000); }",
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

TESTS["render/initial-layout-5000-blocks.html"] = micro(
    "insert a container of 5000 empty fixed-height block divs and force the first style + layout", 1,
    setup="""
    () => {
        injectStyleOnce("blocks", "#sandbox div div { height: 10px; }");
        sandbox().textContent = "";
        forceLayout();
        const container = document.createElement("div");
        for (let i = 0; i < 5000; i++)
            container.appendChild(document.createElement("div"));
        return container;
    }""",
    run="""
    (container) => {
        sandbox().appendChild(container);
        if (forceLayout() < 50000) throw new Error("bad result");
    }""")

TESTS["render/insert-scattered-leaves.html"] = pipeline(
    "insert 100 new leaves under 100 random parents of a StyleBench-shaped 5000-element inline-block tree with a 5000-rule sheet, then force layout", 1,
    setup="""
    () => {
        injectInlineBlockStyle();
        injectStyleOnce("rules", makeRuleSheetText(5000));
        sandbox().textContent = "";
        sandbox().appendChild(makeInlineBlockTree(5000));
        forceLayout();
        return { parents: [...sandbox().querySelectorAll("*")].filter((e) => e.firstChild), random: seededRandom(4) };
    }""",
    mutate="""
    ({ parents, random }) => {
        for (let i = 0; i < 100; i++) {
            const parent = parents[random(parents.length)];
            const element = document.createElement("elem" + random(10));
            element.className = "class" + random(200);
            parent.insertBefore(element, parent.childNodes[random(parent.childNodes.length + 1)] || null);
        }
    }""")

TESTS["render/remove-scattered-leaves.html"] = pipeline(
    "remove 100 random leaves of a StyleBench-shaped 5000-element inline-block tree with a 5000-rule sheet, then force layout", 1,
    setup="""
    () => {
        injectInlineBlockStyle();
        injectStyleOnce("rules", makeRuleSheetText(5000));
        sandbox().textContent = "";
        sandbox().appendChild(makeInlineBlockTree(5000));
        forceLayout();
        return { leaves: [...sandbox().querySelectorAll("*")].filter((e) => !e.firstChild), random: seededRandom(5) };
    }""",
    mutate="""
    ({ leaves, random }) => {
        for (let i = 0; i < 100; i++) {
            const index = random(leaves.length);
            leaves[index].remove();
            leaves[index] = leaves[leaves.length - 1];
            leaves.pop();
        }
    }""")

TESTS["js/lehmer-random-modulo.html"] = micro(
    "Lehmer RNG step seed = seed * 16807 % 2147483647, whose product leaves the int32 range (StyleBench's random source)", 1000000,
    run="""
    (_, iters) => {
        let seed = 1, acc = 0;
        for (let i = 0; i < iters; i++) {
            seed = seed * 16807 % 2147483647;
            acc += seed % 1048576;
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
