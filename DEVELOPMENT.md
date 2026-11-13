# scgraph — Developer Guide

<!-- Budget: 200 lines. `.claude/CLAUDE.md` and `AGENTS.md` link to this file. Detail lives in ARCHITECTURE.md, README.md and pyproject.toml. -->

This guide is for people and for coding agents who change scgraph. *Getting Started* takes a new contributor to a first passing test run. The sections after it are reference: where the code is, how it is built and tested, and the rules of a contribution.

## Project Purpose

`scgraph` is a high-performance Python library for shortest path routing on geographic and supply chain networks. Core capabilities:

- **Shortest path algorithms** — Dijkstra, Bidirectional Dijkstra, Bellman-Ford, A\*, BMSSP, Contraction Hierarchies (CH), Transit Node Routing (TNR)
- **Graph reduction** — iterative degree-2 pass-through chain contraction with O(1) same-chain detection, boundary resolution, and transparent algorithm wrapping
- **Geographic routing & lazy loading** — lat/lon node coordinates, automatic origin/destination snapping, lazy GeoGraph proxies, haversine/cheap-ruler distances
- **Built-in networks** — maritime, rail, highway, and combined world networks (downloaded on demand); networks built from their online sources
- **C++ acceleration** — optional compiled extension (nanobind) providing ~10x speedup; pure Python fallback always present
- **Grid pathfinding** — 2D grid routing with obstacles and configurable connectivity

Winner of the 2025 MIT Prize for Open Data. Zero external runtime dependencies beyond `geokdtree`, `bmsspy`, and `requests`.

> **IMPORTANT — DO NOT RUN A RELEASE CYCLE.** Do not bump versions, generate docs, build distributions, or publish to PyPI. Release steps are owner-only. If you think a release is needed, flag it and stop.

## Getting Started

1. Install Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).
2. Get the code and switch to the `dev` branch: `git clone https://github.com/connor-makowski/scgraph.git`, `cd scgraph`, `git checkout dev`.
3. Install the package and its dev dependencies: `uv sync --extra dev`. This also compiles the C++ extension if a compiler is present. If the root-owned `build/` directory causes a permission error, run `sudo rm -rf build/cp314-cp314-linux_x86_64`, then install again.
4. Run the tests: `uv run pytest`. The tests download the built-in networks, so they need Internet. Expect about 1,000 tests in 1 to 2 minutes, all passed or skipped.
5. Check that the C++ extension was built: `uv run python -c "from scgraph.utils import has_cpp; print(has_cpp())"` prints `True`. If it prints `False`, see *C++ Extension* below.
6. Before each commit, run `uv run utils/prettify.py`, then `uv run nox -s lint`. On a clean checkout, the formatter changes no file. Read *Contribution Workflow* before your first PR.

## Directory Layout (relevant files only)

```
scgraph/
  __init__.py                    # Exports: Graph, CHGraph, TNRGraph, GeoGraph, GridGraph, PathNotFoundError, NegativeCycleError
  graph.py                       # Core Graph class — Dijkstra, Bidirectional Dijkstra, Bellman-Ford, A*, BMSSP, tree ops
  graph_reducer.py               # GraphReducer + @algorithm decorator (chain contraction, path expansion)
  geograph.py                    # GeoGraph + LazyGeoGraph — snapping, caching, built-in nets, loaders, build_geograph
  contraction_hierarchies.py     # CHGraph — CH preprocessing + bidirectional queries
  transit_node_routing.py        # TNRGraph — Transit Node Routing (extends CHGraph)
  grid.py                        # GridGraph — 2D grid pathfinding
  network_file.py                # Reading and writing .scgraph network files (stdlib)
  graph_utils.py                 # GraphUtils (validation, path reconstruction) + GraphModifiers
  utils.py                       # Distance math, coordinate helpers, caching, console output
  pipelines/                     # One module per buildable network; the contract is the docstring of __init__.py
    build.py                     # The runner: build_file (download, build, cache) and python -m scgraph.pipelines.build
    steps/                       # stage1_extract, stage2_intermodal, stage3_assembly, stage4_validation (ARCHITECTURE.md §1)
  helpers/
    geojson.py                   # GeoJSON parsing and simplification
    visvalingam.py               # Visvalingam-Whyatt line simplification
    douglas_peucker.py           # Douglas-Peucker line simplification
    polylines.py                 # Polylines to a graph: nodes where they end or meet, arcs with their shape
    hilbert.py                   # Hilbert-curve order of nodes
    snap_index.py                # Snapping index, pure-Python version of cpp/src/snap_index.cpp
  cpp/
    src/                         # C++ source: csr_graph, graph, graph_utils, graph_reducer, contraction_hierarchies,
    │                            #   transit_node_routing, snap_index, bmssp (template header); pipelines/ (assembly, landmask)
    bindings/                    # nanobind Python/C++ interface: graph_bindings.cpp, pipelines_bindings.cpp
test/                            # 50+ numbered files NN_module_feature_test.py; conftest.py (session fixtures), helpers.py
utils/
  bench.py                       # Fast benchmark runner (<30s); outputs benchmark.md
  compare_versions.py            # Before/after of two git refs with bench.py
  prettify.py                    # ruff (unused imports) + black (line-length=80)
  docs.py                        # Generate pdoc HTML docs — DO NOT RUN (release only)
noxfile.py                       # nox sessions: pytest across Python 3.11–3.14, and lint (ruff, pyrefly)
pyproject.toml                   # Package metadata, scikit-build-core config, black + ruff + pytest config
CMakeLists.txt                   # C++ build configuration (nanobind, C++20, -O3)
publish.sh                       # PyPI publishing script — DO NOT RUN
```

## Development Commands

| Command | What it does |
|---|---|
| `uv run pytest` / `uv run pytest test/NN_*.py` | Run all tests in the local venv or a specific test file |
| `uv run nox` | Run tests (C++ then no-C++) across Python 3.11–3.14, and the lint session |
| `uv run nox -s tests-3.14` | Run both build variants on a single Python version |
| `uv run utils/bench.py` | Run benchmarks (<30s), output `benchmark.md` |
| `python3 utils/compare_versions.py BASE HEAD` | Benchmark two git refs side by side; options in `--help` |
| `uv run utils/prettify.py` | Remove unused imports (ruff), format (black) |
| `uv run nox -s lint` | Check the code with ruff and the types with pyrefly |

**Benchmarks** (`utils/bench.py`): Runs timing benchmarks across GeoGraphs, GridGraphs, hierarchical routing, and specialized features, and outputs `benchmark.md`. Its docstring lists the sections (`load`, `reduce`, `query`, `grid`, `hierarchy`, `misc`).

## Core Architecture

[ARCHITECTURE.md](ARCHITECTURE.md) explains how scgraph works inside: the data model and the hierarchies (§2), the steps of a geographic query (§3), graph reduction (§4), plugging in an algorithm (§5), caches (§6), the `.scgraph` file (§7). The [README](README.md) gives every algorithm with its use (*Algorithm Reference*) and the parameters of the loaders.

### Key Classes

**`Graph`** (`graph.py`) — base graph class:
- Algorithms: `dijkstra`, `bidirectional_dijkstra`, `bellman_ford`, `a_star`, `bmssp`, `dijkstra_buckets`, `bidirectional_buckets`, `dijkstra_negative`, `cached_shortest_path`, `contraction_hierarchy`, `tnr`
- Graph reduction: `reduce()` to contract pass-through chains
- Decorator: `@Graph.algorithm` wraps custom single- or bidirectional algorithms with automatic reduced-graph support
- Tree operations for multi-destination queries (`get_shortest_path_tree`, `get_tree_path`)
- Delegates to C++ extension when available, falls back to pure Python

**`GraphReducer`** (`graph_reducer.py` / C++ `graph_reducer.cpp`) — detail in ARCHITECTURE.md §4:
- Contracts degree-2 / pass-through nodes into composite weighted edges while preserving exact path lengths
- Iterative reduction passes (`iterations=-1` for convergence, the default; `iterations=1` for one pass)
- Transparent path reconstruction expanding compressed chains back to original node sequences

**`GeoGraph` / `LazyGeoGraph`** (`geograph.py`) — geographic routing:
- Combines `Graph` (attribute `graph_object`) with lat/lon node coordinates
- Snaps arbitrary coordinates to the network with its snapping index (`snap_index`) or `geokdtree` (ARCHITECTURE.md §3)
- Manages caching of shortest path trees and downloaded built-in networks (ARCHITECTURE.md §6)
- Lazy loading via `LazyGeoGraph` proxy (`lazy=True`) to defer downloads/instantiation until first use
- Configurable reduction upon loading (`reduce_iterations=0` by default, `1` or `-1` for reduction)
- Handles I/O: load from GeoJSON, OSMNx, OpenStreetMap files, graphjson or `.scgraph` network files; save in multiple formats
- Builds networks from their online sources into the local cache (`build_geograph`, one pipeline per network)

**`CHGraph`** (`contraction_hierarchies.py`) / **`TNRGraph`** (`transit_node_routing.py`) — hierarchies built once for fast queries:
- `CHGraph` contracts nodes in order of importance; `TNRGraph` extends it with transit nodes and a distance table
- Serialize to `.chjson` / `.tnrjson`; how they are built and queried: ARCHITECTURE.md §2, *Trees and Hierarchies*

**`GridGraph`** (`grid.py`) — 2D grid pathfinding: supports obstacles, configurable connectivity (4/8-directional), shape collisions

**`GraphUtils` / `GraphModifiers`** (`graph_utils.py`): input validation, path reconstruction, negative cycle detection; add/remove nodes and edges dynamically

### C++ Extension

Located in `scgraph/cpp/`, compiled via scikit-build-core + nanobind:
- Provides ~10x speedup on core algorithms; pure Python implementations in the `.py` files serve as the fallback
- Skip C++ build: `SCGRAPH_NO_BUILD=1`. Fail if it cannot be compiled: `SCGRAPH_REQUIRE_CPP=1`. Check the installed build: `scgraph.utils.has_cpp()`
- C++20 standard, compiled with `-O3 -DNDEBUG -fno-math-errno -fomit-frame-pointer` (`/O2 /DNDEBUG` with MSVC)
- The C++ build is installed as a copy: after a change, run `uv sync --extra dev --reinstall-package scgraph` before a test run

**Debugging a C++ build:** `pyproject.toml` contains a build fallback (`[[tool.scikit-build.overrides]]`, `if.failed = true`, `wheel.cmake = false`). When C++ compilation fails, `scikit-build-core` silently falls back to building a pure Python wheel, so `uv sync` may appear to succeed while `has_cpp()` returns `False`. To surface the compiler error: `uv sync --extra dev --reinstall-package scgraph -v --config-setting=build.verbose=true`.

## Test Structure

Tests use pytest (`uv run pytest`). Files are in `test/`, named `NN_module_feature_test.py` (zero-padded for ordered display). When adding a new feature, add a corresponding `NN_*_test.py` file. pytest discovers all `*_test.py` files in `test/` automatically.

**Shared infrastructure:**
- `test/conftest.py` — session-scoped fixtures: `marnet`, `us_freeway`, `oak_ridge_maritime`, `north_america_rail`, `world_highways_and_marnet`, `published`. The tests download these networks into a temporary cache per session, never the user's. Set `SCGRAPH_CACHE_DIR` to keep the downloads between runs.
- `test/helpers.py` — `assert_result(realized, expected)` rounds `length` to 3dp before comparing
- `scgraph/pipelines/steps/stage4_validation/` — `validate_network` checks a built network against the cases of `cases/*.csv`: `python -m scgraph.pipelines.build NAME --validate` (`--validate-only` for a network in the cache)

**Rough groupings:** `00` C++ extension check · `01–02` core `Graph` algorithms · `04–11` `GeoGraph` with built-in networks + I/O · `12–14` `GridGraph` · `15–22` specialized (negative cycles, helpers, merge, distance matrix, BMSSP) · `23–31` CH and TNR, save/load, modifiers, caches · `32–33`, `40–43` graph reduction · `35–39` CH/TNR edge cases, lazy loading, reduce defaults, bidirectional Dijkstra · `44–47` buckets, origin dicts, static shortest path, dict weights · `48–50` OSMNx, OSM and GeoJSON loaders · `51–56` network builds, `.scgraph` files, snapping index, assembly, land mask, validation

**Test pattern:**
```python
from helpers import assert_result

def test_dijkstra(marnet):  # marnet is a session fixture from conftest.py
    assert_result(
        marnet.get_shortest_path(
            origin_node={"latitude": 30, "longitude": 160},
            destination_node={"latitude": 30, "longitude": -160},
        ),
        {"coordinate_path": [...], "length": 4477.148},
    )
```

**Rules for a new or changed test:**
- **One requirement:** A test states one requirement that a user relies on, through the public API, and runs in both builds (with the C++ extension, and pure Python).
- **Readable alone:** A test names its data, makes one call and checks one result. It has no `if`, and no table of options that change what the test checks. Several short tests are better than one such table.
- **Can fail:** A fix comes with a test that fails without the fix. If a test of the feature exists, add the case to it. `test_reduced_graph_matches_unreduced_graph` in `test/33` is the general test of reduced graphs. Add a new case of reduction there as data.
- **No clock:** A test does not compare durations. `utils/bench.py` measures speed.
- **Fakes:** A test may replace the download (`requests.get`, or a source URL pointed at a local server). It does not replace a function or a constant of scgraph.
- **Tests of release 3.6.0:** They stay as their author wrote them. Change one only for a clear gain in simplicity, speed or coverage, and state the gain in the PR.

## Coding Conventions

- **Line length**: 80 characters (black config in `pyproject.toml`). **Python version**: 3.11+ (use `X | Y` union syntax, `match`, etc.)
- **Formatting and checks**: Always run `uv run utils/prettify.py` then `uv run nox -s lint` before committing. A finding of `ruff` or `pyrefly` blocks a PR. The rules and their reasons are in `pyproject.toml`.
- **Names**: A function name starts with a verb (`build_`, `find_`, `select_`, `read_`, `get_`). A function that returns a boolean starts with `is_`, `has_`, `can_` or `should_`. A parameter says what it holds, with its unit (`max_km_between_nodes`), and keeps that name in every function and in the C++ binding. Internal names: `_name` in Python, `name_` for C++ members.
- **Types**: Public functions annotate their parameters and their return, with built-in types and `X | Y`. Each kind of value has one form. A number parameter is `float`. A returned length, or a weight inside a graph, is `int | float`. A `[latitude, longitude]` pair is `Sequence[float]`. A path is `str | os.PathLike`. A buffer of a C++ kernel is `array | memoryview`. A function is `Callable` (from `collections.abc`). A default of `None` adds `| None`. A value of any type is `object`. A type of an optional dependency is written as a string.
- **Docstrings and comments**: A docstring gives a summary, the parameters and the return. It adds the unit and the constraints, not the type. A comment gives a reason, in full sentences. It does not tell the history of a change or name an issue.
- **Sentences**: Every text (docstring, comment, commit message, issue, PR) uses plain sentences. A sentence has a concrete subject, a verb and an object. It holds one idea in about 20 words. Define a term where it first appears, and keep one word for one thing.
- **Exceptions**: Raise a specific type (`ValueError`, `PathNotFoundError`…), never a bare `Exception`. A condition that raises in C++ raises the same type in pure Python.
- **Numbers**: Coordinates stored as integers (1e-7 degree) are widened to 64 bits before any difference or product; distances are computed in `float64`.
- **C++ fallback**: Every algorithm implemented in C++ must have a pure Python equivalent; C++ is opt-in at build time. Code that has a C++ kernel calls it when the extension is built.
- **Messages**: Use `logging.getLogger(__name__)` for information, `warnings.warn` for what the caller can avoid, and exceptions for errors. New code has no `print` and no `silent=` parameter (older functions still have `silent=`; see #115).
- **No new runtime dependencies**: Runtime code must only import stdlib + `geokdtree`, `bmsspy`, `requests`; an optional reader may need an optional extra (`osm`: osmium), imported only when it is called
- **No unnecessary abstractions**: Don't create shared helpers unless the same logic appears 3+ times. Remove code that nothing calls.
- **Don't mutate caller-provided arguments**: Copy small inputs (option dicts, lists of blocks, etc.) before modifying them; large graph data may be kept without copying for performance, so say so in the docstring

## Contribution Workflow

- Open an issue first, then one branch and one PR per issue. A PR title states the outcome and ends with its issue number: `Fix … (#N)`. The body says what changes for the user and gives the proof.
- Branches live in this repository (`fix/...`, `perf/...`, `docs/...`, `test/...`) and start from `dev`; PRs target `dev`, never `main`. A contributor without write access works from a fork.
- Never commit directly to `dev` or `main`. Merge PRs with a merge commit (no squash or rebase), so that stacked PRs keep their commits, then delete the branch.
- A PR that depends on another open PR targets that PR's branch until it is merged.
- A change to the public API edits `README.md` and the docstring of `scgraph/__init__.py` identically, in the same PR.
- `dev` has no users. A file or a name that exists only on `dev` gets no migration code. What release 3.6.0 wrote or exposed must keep working.
- A PR that changes runtime code (`scgraph/`) includes a before → after from `utils/compare_versions.py` on the sections it touches, against its target branch (`--backends cpp,python` if pure-Python code changed).
- `Closes #N` only links and closes issues for PRs into `main`. For a PR into `dev`, also link the issue by hand (the PR's *Development* sidebar, or `gh api graphql` with the `addCloseIssueReferences` mutation): the issue then shows the PR but stays open.
- After merging into `dev`, add the `merged in dev` label and the "Next release" milestone to the issue; it is closed when `dev` is merged into `main` (list it with `Closes #N` in that PR). Only the owner merges `dev` into `main` and releases.

## Release Checklist (owner only — do not execute)

1. Set `version` in `pyproject.toml` (and `uv.lock`) to the release number, dropping the `.devN` suffix
2. Run `uv run utils/prettify.py`
3. Run `uv run nox` — all sessions must pass
4. Run `uv run python utils/docs.py` to regenerate docs
5. Build and publish via `publish.sh`
6. Right after the release, set the next development version on `dev` with a `.dev0` suffix (PEP 440), e.g. `4.1.0.dev0`
