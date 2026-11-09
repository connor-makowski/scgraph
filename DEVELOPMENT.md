# scgraph — Developer Guide

## Project Purpose

`scgraph` is a high-performance Python library for shortest path routing on geographic and supply chain networks. Core capabilities:

- **Shortest path algorithms** — Dijkstra, Bidirectional Dijkstra, Bellman-Ford, A\*, BMSSP, Contraction Hierarchies (CH), Transit Node Routing (TNR)
- **Graph reduction** — iterative degree-2 pass-through chain contraction with O(1) same-chain detection, boundary resolution, and transparent algorithm wrapping
- **Geographic routing & lazy loading** — lat/lon node coordinates, automatic origin/destination snapping, lazy GeoGraph proxies, haversine/cheap-ruler distances
- **Built-in networks** — maritime, rail, highway, and combined world networks (downloaded on demand)
- **C++ acceleration** — optional compiled extension (nanobind) providing ~10x speedup; pure Python fallback always present
- **Grid pathfinding** — 2D grid routing with obstacles and configurable connectivity

Winner of the 2025 MIT Prize for Open Data. Zero external runtime dependencies beyond `geokdtree`, `bmsspy`, and `requests`.

---

> **IMPORTANT — DO NOT RUN A RELEASE CYCLE.** Do not bump versions, generate docs, build distributions, or publish to PyPI. Release steps are owner-only. If you think a release is needed, flag it and stop.

---

## Directory Layout (relevant files only)

```
scgraph/
  __init__.py                    # Exports: Graph, CHGraph, TNRGraph, GeoGraph, LazyGeoGraph, GridGraph
  graph.py                       # Core Graph class — Dijkstra, Bidirectional Dijkstra, Bellman-Ford, A*, BMSSP, tree ops
  graph_reducer.py               # GraphReducer + @algorithm decorator (chain contraction, path expansion)
  geograph.py                    # GeoGraph + LazyGeoGraph — snapping, caching, built-in nets, loaders
  contraction_hierarchies.py     # CHGraph — CH preprocessing + bidirectional queries
  transit_node_routing.py        # TNRGraph — Transit Node Routing (extends CHGraph)
  grid.py                        # GridGraph — 2D grid pathfinding
  network_file.py                # Reading and writing .scgraph network files (stdlib)
  graph_utils.py                 # GraphUtils (validation, path reconstruction) + GraphModifiers
  utils.py                       # Distance math, coordinate helpers, caching, console output
  pipelines/                     # Pipelines of build_geograph, one per network (contract and steps in __init__.py)
    build.py                     # The runner: build_file (download, build, cache) and python -m scgraph.pipelines.build
    steps/                       # Sequential execution stages:
      stage1_extract/            # Ingestion & raw extraction (osm, arcgis, pbf_range_streamer)
      stage2_intermodal/         # Intermodal connectors & domain logic (landmask, ports)
      stage3_assembly/           # Topology, CSR assembly, chain contraction (assembly)
  helpers/
    geojson.py                   # GeoJSON parsing and simplification
    hilbert.py                   # Hilbert-curve order of nodes (network files, loaders that number nodes)
    polylines.py                 # Polylines to a graph: nodes where they end or meet, arcs with their shape (GeoJSON, OSM)
    snap_index.py                # Snapping index, pure-Python version of cpp/src/snap_index.cpp
    visvalingam.py               # Visvalingam-Whyatt line simplification
  cpp/
    src/                         # C++ source: adjacency, graph, graph_utils, graph_reducer, contraction_hierarchies,
    │                            #   transit_node_routing, snap_index, bmssp (template header); pipelines/assembly.hpp, landmask.hpp
    bindings/
      graph_bindings.cpp         # nanobind Python/C++ interface
      pipelines_bindings.cpp     # Bindings of the pipelines' kernels (no fused multiply-add, as their Python twins)
      array_types.hpp            # Array types shared by the binding units
test/
  NN_module_feature_test.py      # 40+ numbered test files; named *_test.py
  conftest.py                    # pytest session fixtures for shared geographs
  helpers.py                     # assert_result() helper used by test files
utils/
  bench.py                       # Fast benchmark runner (<30s); outputs benchmark.md
  compare_versions.py            # Before/after of two git refs with bench.py (report.md)
  prettify.py                    # autoflake (unused imports) + black (line-length=80)
  docs.py                        # Generate pdoc HTML docs — DO NOT RUN (release only)
noxfile.py                       # nox sessions: runs pytest across Python 3.11–3.14
pyproject.toml                   # Package metadata, scikit-build-core config, black + pytest config
CMakeLists.txt                   # C++ build configuration (nanobind, C++20, -O3)
publish.sh                       # PyPI publishing script — DO NOT RUN
```

---

## Development Commands

| Command | What it does |
|---|---|
| `uv run pytest` | Run all tests in the local venv |
| `uv run pytest test/NN_*.py` | Run a specific test file |
| `uv run nox` | Run tests (C++ then no-C++) across Python 3.11–3.14 |
| `uv run nox -s tests-3.14` | Run both build variants on a single Python version |
| `uv run utils/bench.py` | Run benchmarks (<30s), output `benchmark.md` |
| `python3 utils/compare_versions.py 3.6.0 origin/dev` | Compare two versions on this machine, output `bench-results/…/report.md` |
| `uv run utils/prettify.py` | Format with autoflake + black |

Dev dependencies are declared in `[project.optional-dependencies] dev` in `pyproject.toml`. Install them with `uv sync --extra dev`.

> **Note:** If the root-owned `build/` directory causes a permission error on a fresh install, run `sudo rm -rf build/cp314-cp314-linux_x86_64` then `uv sync --extra dev` to rebuild.

**Benchmarks** (`utils/bench.py`): Runs timing benchmarks across GeoGraphs, GridGraphs, hierarchical routing, and specialized features, and outputs `benchmark.md`.

- **Before/after numbers** (a PR, or `dev` against the release): `python3 utils/compare_versions.py BASE HEAD` builds an environment per version, runs `utils/bench.py` alternating the two, and writes a report: a summary for the PR description, then the tables of `benchmark.md` with both versions side by side. For a PR: `python3 utils/compare_versions.py origin/dev <branch> --only <sections it touches>` (`--backends cpp,python` if the pure-Python code changed too); `--post <N>` writes the report into the description of PR or issue N. Options and duration: `--help`.

**Docs**: **DO NOT generate docs**. Docs are regenerated and versioned at release time by the user only.

---

## Core Architecture

For how scgraph works inside (query, graph reduction, plugging in an algorithm, caches), see [ARCHITECTURE.md](ARCHITECTURE.md).

### Key Classes

**`Graph`** (`graph.py`) — base graph class:
- Algorithms: `dijkstra`, `bidirectional_dijkstra`, `bellman_ford`, `a_star`, `bmssp`, `dijkstra_buckets`, `cached_shortest_path`
- Graph reduction: `reduce()` to contract pass-through chains
- Decorator: `@Graph.algorithm` wraps custom single- or bidirectional algorithms with automatic reduced-graph support
- Tree operations for multi-destination queries
- Delegates to C++ extension when available, falls back to pure Python

**`GraphReducer`** (`graph_reducer.py` / C++ `graph_reducer.cpp`):
- Contracts degree-2 / pass-through nodes into composite weighted edges while preserving exact path lengths
- `reduced_node_chain_ids`: O(1) same-chain origin/destination detection
- Dual-sided boundary connections for interior chain nodes
- Iterative reduction passes (`iterations=-1` for convergence, the default; `iterations=1` for one pass)
- Transparent path reconstruction expanding compressed chains back to original node sequences

**`GeoGraph` / `LazyGeoGraph`** (`geograph.py`) — geographic routing:
- Combines `Graph` with lat/lon node coordinates
- Snaps arbitrary coordinates to the network with its own snapping index (`snap_index`; C++ `cpp/src/snap_index.cpp`, Python `helpers/snap_index.py`); `geokdtree` only backs the deprecated `geokdtree` attribute
- Manages caching of shortest path trees and downloaded built-in networks
- Lazy loading via `LazyGeoGraph` proxy (`lazy=True`) to defer downloads/instantiation until first use
- Configurable reduction upon loading (`reduce_iterations=0` by default, `1` or `-1` for reduction)
- Handles I/O: load from GeoJSON, OSMNx, OpenStreetMap files, graphjson or `.scgraph` network files; save in multiple formats
- Builds reference networks from their online sources into the local cache (`build_geograph`, one pipeline per network in `pipelines/`)

**`CHGraph`** (`contraction_hierarchies.py`) — Contraction Hierarchies:
- Preprocessing step that contracts nodes in order of importance
- Bidirectional Dijkstra queries on the contracted graph
- Serializes/deserializes to `.chjson`

**`TNRGraph`** (`transit_node_routing.py`) — Transit Node Routing:
- Extends `CHGraph` with a transit node set and precomputed distance table
- Global O(1)-style queries for long-distance routing
- Serializes to `.tnrjson`

**`GridGraph`** (`grid.py`) — 2D grid pathfinding:
- Supports obstacles, configurable connectivity (4/8-directional), shape collisions

**`GraphUtils` / `GraphModifiers`** (`graph_utils.py`):
- Input validation, path reconstruction, negative cycle detection
- Add/remove nodes and edges dynamically

### C++ Extension

Located in `scgraph/cpp/`, compiled via scikit-build-core + nanobind:
- Provides ~10x speedup on core algorithms
- Pure Python implementations in the `.py` files serve as the fallback
- Skip C++ build: `SKBUILD_CMAKE_ARGS="-DSKIP_CPP_BUILD=ON"`
- C++20 standard, compiled with `-O3 -DNDEBUG -fno-math-errno -fomit-frame-pointer` (`/O2 /DNDEBUG` with MSVC)

#### Debugging C++ Builds & Compiler Errors

By default, `pyproject.toml` contains a build fallback:
```toml
[[tool.scikit-build.overrides]]
if.failed = true
wheel.cmake = false
```
When C++ compilation fails, `scikit-build-core` silently falls back to building a pure Python wheel, so `uv sync` may appear to succeed while `has_cpp()` returns `False`.

To surface compiler errors and debug the C++ build:

1. **Verbose build command (recommended)**:
   ```bash
   uv sync --extra dev --reinstall-package scgraph -v --config-setting=build.verbose=true
   ```
   Or set debug logging:
   ```bash
   uv sync --extra dev --reinstall-package scgraph --config-setting=logging.level=DEBUG
   ```

2. **Disable fallback override in `pyproject.toml`**:
   Temporarily comment out the `[[tool.scikit-build.overrides]]` section and set `build.verbose = true` under `[tool.scikit-build]`. Running `uv sync --extra dev --reinstall-package scgraph` will then immediately fail with the exact C++ compiler error and line number.

---

## Test Structure

Tests use pytest (`uv run pytest`). Files are in `test/`, named `NN_module_feature_test.py`.

**Shared infrastructure:**
- `test/conftest.py` — session-scoped fixtures: `marnet`, `us_freeway`, `oak_ridge_maritime`, `north_america_rail`, `world_highways_and_marnet`, and `published` (a built-in network in the node numbering of its `.graphjson`)
  - The tests download these networks into their own cache, a temporary directory per session, never the user's. Set `SCGRAPH_CACHE_DIR` to a directory to keep the downloads between runs (or to run the tests offline from a filled cache).
- `test/helpers.py` — `assert_result(realized, expected)` rounds `length` to 3dp before comparing
- `acceptance/` — the acceptance suite of a built network file (`test_<kind>.py`, with its own `pytest.ini`), not collected by `uv run pytest`: run `uv run pytest acceptance --network FILE`

**Naming convention:** `NN_module_feature_test.py` (zero-padded for ordered display)

**Rough groupings:**
- `00`: C++ extension availability check
- `01–02`: Core `Graph` algorithms (marnet, bidirectional Dijkstra)
- `04–11`: `GeoGraph` with various built-in networks + I/O
- `12–14`: `GridGraph`
- `15–22`: Specialized (negative cycles, helpers, merge, distance matrix, BMSSP, etc.)
- `23–24`: Contraction Hierarchies save/load
- `25–31`: TNR, world highways, modifiers, load/cache, CH caching tests
- `32–33`: Graph reduction and consistency checks
- `34–35`: GridGraph performance, CH/TNR edge cases
- `36–37`: Lazy loading and reduce defaults
- `38–43`: CH/TNR on reduced graphs, bidirectional Dijkstra, chain IDs, dual-sided reduction, algorithm decorator, iterative reduction

**Reduction exactness:** `test_reduced_graph_matches_unreduced_graph` in `test/33` compares every search on reduced graphs with Dijkstra on the unreduced graph and checks the paths `reduce()` stores; the comment above `CHECKED_GRAPHS` explains how the graphs are chosen.

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

When adding a new feature, add a corresponding `NN_*_test.py` file. pytest discovers all `*_test.py` files in `test/` automatically.

---

## Coding Conventions

- **Line length**: 80 characters (black config in `pyproject.toml`)
- **Python version**: 3.11+ (use `X | Y` union syntax, `match`, etc.)
- **Formatting**: Always run `uv run python utils/prettify.py` before committing
- **C++ fallback**: Every algorithm implemented in C++ must have a pure Python equivalent; C++ is opt-in at build time
- **Messages**: through `logging.getLogger(__name__)` (a `NullHandler` on `scgraph`), `warnings.warn` for what the caller can avoid, exceptions for errors; no `print` and no `silent=` in new code (older functions still have `silent=`; see #115)
- **No new runtime dependencies**: Runtime code must only import stdlib + `geokdtree`, `bmsspy`, `requests`; an optional reader may need an optional extra (`osm`: osmium), imported only when it is called
- **No unnecessary abstractions**: Don't create shared helpers unless the same logic appears 3+ times
- **Don't mutate caller-provided arguments**: Copy small inputs (option dicts, lists of blocks, etc.) before modifying them; large graph data may be kept without copying for performance, so say so in the docstring
- **DO NOT generate docs**: Only the maintainer generates docs at release time

---

## Contribution Workflow

- Open an issue first, then one branch and one PR per issue.
- Branches live in this repository (`fix/...`, `perf/...`, `docs/...`, `test/...`) and start from `dev`; PRs target `dev`, never `main`.
- Never commit directly to `dev` or `main`. Merge PRs with a merge commit (no squash or rebase), so that stacked PRs keep their commits, then delete the branch.
- A PR that depends on another open PR targets that PR's branch until it is merged.
- A PR that changes runtime code (`scgraph/`) includes a before → after from `utils/bench.py` on the sections it touches, against its target branch (see *Benchmarks* above).
- `Closes #N` only links and closes issues for PRs into `main`. For a PR into `dev`, also link the issue by hand (the PR's *Development* sidebar, or `gh api graphql` with the `addCloseIssueReferences` mutation): the issue then shows the PR but stays open.
- After merging into `dev`, add the `merged in dev` label and the "Next release" milestone to the issue; it is closed when `dev` is merged into `main` (list it with `Closes #N` in that PR).
- Only the owner merges `dev` into `main` and releases.

---

## Release Checklist (owner only — do not execute)

1. Bump `version` in `pyproject.toml`
2. Run `uv run python utils/prettify.py`
3. Run `uv run nox` — all sessions must pass
4. Run `uv run python utils/docs.py` to regenerate docs
5. Build and publish via `publish.sh`

---

Python: **≥ 3.11** | Runtime dependencies: `geokdtree`, `bmsspy`, `requests`
