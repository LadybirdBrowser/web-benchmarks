# MicroWeb

A suite of fine-grained, time-based microbenchmarks for the primitives that Speedometer3
exercises. Each test is one small standalone HTML page measuring one operation family:
one DOM API, one render-pipeline pattern, one JS idiom, one canvas call, and so on.

The purpose is comparative: run the suite against Ladybird and against Chromium with its
JIT disabled, rank every test by the Ladybird/Chromium multiplier, and grind the worst
multiplier down. Each test is independent, so many people (or agents) can work on
different tests in parallel without stepping on each other.

## Running

```bash
# Ladybird, fresh browser per category (honest per-test numbers)
./run.py --executable "$LADYBIRD/Build/release/bin/Ladybird" \
    --benchmarks MicroWeb --split-suites --iterations 5 -o lb.json

# Chromium, JIT disabled (the interesting engine-vs-engine comparison)
./run.py --executable /snap/bin/chromium --browser chromium --jitless \
    --benchmarks MicroWeb --split-suites --iterations 5 -o cr.json

# Ranked multiplier table, worst first
./ratios.py --subject lb.json --reference cr.json
```

Use `--iterations 5` for reference numbers and the default single iteration for quick
checks; a 5-iteration Ladybird run keeps the CPU pinned for several minutes, which is
the benchmark working, not a hang.

**Session aging.** Running all ~230 tests in one browser session makes late-running
tests dramatically slower in Ladybird (up to hundreds of times slower than the same
test in a fresh browser); Chromium shows no such drift. `--split-suites` launches a
fresh browser per category so per-test multipliers stay honest. A run *without* it
doubles as the aging probe:

```bash
./run.py --executable .../Ladybird --benchmarks MicroWeb --iterations 5 -o aged.json
./aging.py --aged aged.json --fresh lb.json
```

Real sessions (and Speedometer3 itself) are long-lived, so the aging tax is a real
performance bug, not benchmark noise; it just should not be smeared across unrelated
per-test numbers.

`compare.py` still compares two runs of the same browser (before/after a change).

For the grind loop there is a one-command tool that runs a single test in both
browsers, each in a fresh session, and prints the ratio — the fastest way to check a
fix:

```bash
$ ./mw.py fill-style-set
canvas/fill-style-set.html  (iterations: 5, chromium jitless)
  ladybird  median    70.80 ms   [72.10, 70.70, 71.00, 70.80, 70.30]
  chromium  median     1.20 ms   [1.20, 1.20, 1.30, 1.10, 1.10]
  ratio     Ladybird is 59.0x slower
```

Any unique substring of a test path works; several tests can be named at once, and
`--jit` re-enables Chromium's JIT. Individual tests are also plain pages: open
`dom/create-element.html?iterationCount=5` directly in any browser and read
`window.__webKitPerfTestState.values` from the console.

## Categories

| Directory | What it covers | Speedometer3 connection |
|---|---|---|
| `dom/` | DOM API primitives with no rendering involvement | every suite's Sync time |
| `render/` | a mutation followed by a forced style+layout flush | every suite's Async settle + in-handler forced layouts |
| `layout/` | the same, per layout mode: flex, grid, table, abspos, floats, deep nesting | complex-DOM suites, Perf-Dashboard |
| `style/` | stylesheet parsing, selector invalidation breadth, CSS variables, CSSOM | class-toggle-heavy suites |
| `text/` | text shaping (cache hit vs miss), font switches, bidi, innerText | everything with text |
| `js/` | pure JavaScript idioms, Proxy reactivity, no DOM | framework internals, Vue, editors |
| `canvas/` | 2D canvas calls | Charts-chartjs |
| `svg/` | SVG DOM and layout | React-Stockcharts-SVG, observable-plot, Perf-Dashboard |
| `parse/` | HTML/XML parsing and serialization | TodoMVC-jQuery re-render, NewsSite hydration |
| `shadow/` | custom elements and shadow DOM | TodoMVC-WebComponents, Lit |
| `events/` | dispatch shapes: deep bubbling, delegation, synthetic keyboard input | the test driver itself + framework delegation |
| `edit/` | contenteditable, Selection, Range | Editor-TipTap, Editor-CodeMirror |
| `frameworks/` | reconciler patterns: keyed reorder, fragment batching, template fill | all framework suites |
| `observers/` | MutationObserver and friends | frameworks' batching machinery |
| `timers/` | task and microtask scheduling | async settle plumbing |
| `urlstate/` | URL parsing, history API, text encoding | NewsSite SPA navigation |
| `storage/` | synchronous storage | app state persistence |

A test that fails or measures an unimplemented feature reports an error instead of a
number; the run continues, and the test simply has no row in the results (so ratios.py
skips it). `single.html?test=dom/create-element.html&iterationCount=5` runs one test in
isolation for debugging.

## Methodology

- **Time-based, fixed workloads.** A test's value is the elapsed ms for a fixed batch of
  operations, so faster code produces a smaller number and total suite time shrinks as
  the engine improves. There is no score.
- One untimed warm-up iteration runs before the measured iterations.
- Workloads are sized to take at least a few ms per iteration in a fast browser, because
  Ladybird quantizes `performance.now()` to 0.1ms.
- `render/` tests time `mutate; offsetHeight` cycles: the synchronous style+layout flush.
  Paint happens between iterations, outside the timed region, because timing paint from
  JS mostly measures vsync waits. A paint-cost category needs different machinery and is
  deliberately out of scope here.
- Tests accumulate results and throw on nonsense values, so an engine cannot win by
  optimizing away the workload.

## Adding a test

Edit the spec in `resources/generate.py` and re-run it:

```bash
./resources/generate.py
```

It rewrites the test pages and `index.html`. Keep one test to one operation family: a
test that mixes two behaviors produces a multiplier nobody can act on. When a test's
multiplier reaches ~1x, split it or replace it with a finer-grained probe of whatever
is still slow.

## Provenance

Workload shapes are modeled on what Speedometer3's suites and test driver actually do:
todo-list DOM shapes, `li:nth-child(i) .toggle` queries, whole-list innerHTML
replacement (jQuery TodoMVC), path `d`-attribute rewriting (React-Stockcharts zoom),
per-point canvas fillStyle changes (chartjs), and so on.
