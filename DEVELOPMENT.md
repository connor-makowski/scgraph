# scgraph — Developer Guide

## Project Purpose

`scgraph` is a high-performance Python library for shortest path routing on geographic and supply chain networks. Core capabilities:

- **Shortest path algorithms** — Dijkstra, Bellman-Ford, A\*, BMSSP, Contraction Hierarchies (CH), Transit Node Routing (TNR)
- **Geographic routing** — lat/lon node coordinates, automatic origin/destination snapping to network, haversine/cheap-ruler distances
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
  __init__.py                    # Exports: Graph, CHGraph, TNRGraph, GeoGraph, GridGraph
  graph.py                       # Core Graph class — Dijkstra, Bellman-Ford, A*, BMSSP, tree ops
  geograph.py                    # GeoGraph — geographic routing, snapping, caching, built-in nets
  contraction_hierarchies.py     # CHGraph — CH preprocessing + bidirectional queries
  transit_node_routing.py        # TNRGraph — Transit Node Routing (extends CHGraph)
  grid.py                        # GridGraph — 2D grid pathfinding
  graph_utils.py                 # GraphUtils (validation, path reconstruction) + GraphModifiers
  utils.py                       # Distance math, coordinate helpers, caching, console output
  helpers/
    geojson.py                   # GeoJSON parsing and simplification
    visvalingam.py               # Visvalingam-Whyatt line simplification
  cpp/
    src/                         # C++ source: graph, graph_utils, contraction_hierarchies,
    │                            #   transit_node_routing, bmssp (template header)
    bindings/
      graph_bindings.cpp         # nanobind Python/C++ interface
test/
  NN_module_feature_test.py      # 30+ numbered test files; named *_test.py
  conftest.py                    # pytest session fixtures for shared geographs
  helpers.py                     # assert_result() helper used by test files
utils/
  benchmark.py                   # Standalone benchmark runner; outputs benchmark_results.json
  prettify.py                    # autoflake (unused imports) + black (line-length=88)
  docs.py                        # Generate pdoc HTML docs — DO NOT RUN (release only)
noxfile.py                       # nox sessions: runs pytest across Python 3.11–3.14
pyproject.toml                   # Package metadata, scikit-build-core config, black + pytest config
CMakeLists.txt                   # C++ build configuration (nanobind, C++20, -O3 -march=native)
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
| `uv run utils/benchmark.py` | Run all benchmarks, output `benchmark_results.json` |
| `uv run utils/benchmark.py --output path/to/file.json` | Custom benchmark output path |
| `uv run utils/prettify.py` | Format with autoflake + black |

Dev dependencies are declared in `[project.optional-dependencies] dev` in `pyproject.toml`. Install them with `uv sync --extra dev`.

> **Note:** If the root-owned `build/` directory causes a permission error on a fresh install, run `sudo rm -rf build/cp314-cp314-linux_x86_64` then `uv sync --extra dev` to rebuild.

**Benchmarks** (`utils/benchmark.py`): Runs all timing benchmarks and writes a nested JSON file. Commit `benchmark_results.json` to track performance changes via `git diff`. TNR benchmarks are slow (~30s Python, ~4s C++).

**Docs**: **DO NOT generate docs**. Docs are regenerated and versioned at release time by the user only.

---

## Core Architecture

### Key Classes

**`Graph`** (`graph.py`) — base graph class:
- Algorithms: `dijkstra`, `bellman_ford`, `a_star`, `bmssp`, `dijkstra_buckets`, `cached_shortest_path`
- Tree operations for multi-destination queries
- Delegates to C++ extension when available, falls back to pure Python

**`GeoGraph`** (`geograph.py`) — geographic routing:
- Combines `Graph` with lat/lon node coordinates
- Snaps arbitrary coordinates to the network via KD-tree (`geokdtree`)
- Manages caching of shortest path trees and downloaded built-in networks
- Handles I/O: load from GeoJSON, OSMNx, or custom format; save in multiple formats

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
- C++20 standard, compiled with `-O3 -march=native`

---

## Test Structure

Tests use pytest (`uv run pytest`). Files are in `test/`, named `NN_module_feature_test.py`.

**Shared infrastructure:**
- `test/conftest.py` — session-scoped fixtures: `marnet`, `us_freeway`, `oak_ridge_maritime`, `north_america_rail`, `world_highways_and_marnet`
- `test/helpers.py` — `assert_result(realized, expected)` rounds `length` to 3dp before comparing

**Naming convention:** `NN_module_feature_test.py` (zero-padded for ordered display)

**Rough groupings:**
- `00`: C++ extension availability check
- `01–02`: Core `Graph` algorithms (marnet)
- `04–11`: `GeoGraph` with various built-in networks + I/O
- `12–14`: `GridGraph`
- `15–22`: Specialized (negative cycles, helpers, merge, distance matrix, BMSSP, etc.)
- `23–24`: Contraction Hierarchies save/load
- `25–30`: TNR, world highways, modifiers, load/cache tests

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

- **Line length**: 88 characters (black config in `pyproject.toml`)
- **Python version**: 3.11+ (use `X | Y` union syntax, `match`, etc.)
- **Formatting**: Always run `uv run python utils/prettify.py` before committing
- **C++ fallback**: Every algorithm implemented in C++ must have a pure Python equivalent; C++ is opt-in at build time
- **No new runtime dependencies**: Runtime code must only import stdlib + `geokdtree`, `bmsspy`, `requests`
- **No unnecessary abstractions**: Don't create shared helpers unless the same logic appears 3+ times
- **DO NOT generate docs**: Only the maintainer generates docs at release time

---

## Release Checklist (owner only — do not execute)

1. Bump `version` in `pyproject.toml`
2. Run `uv run python utils/prettify.py`
3. Run `uv run nox` — all sessions must pass
4. Run `uv run python utils/docs.py` to regenerate docs
5. Build and publish via `publish.sh`

---

Python: **≥ 3.11** | Runtime dependencies: `geokdtree`, `bmsspy`, `requests`
