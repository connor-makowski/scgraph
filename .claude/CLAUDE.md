# scgraph: Claude Instructions

## Project Purpose

`scgraph` is a high-performance Python library for shortest path routing on geographic and supply chain networks. Core capabilities:

- **Shortest path algorithms** — Dijkstra, Bellman-Ford, A\*, BMSSP, Contraction Hierarchies (CH), Transit Node Routing (TNR)
- **Geographic routing** — lat/lon node coordinates, automatic origin/destination snapping to network, haversine/cheap-ruler distances
- **Built-in networks** — maritime, rail, highway, and combined world networks (downloaded on demand)
- **C++ acceleration** — optional compiled extension (nanobind) providing ~10x speedup; pure Python fallback always present
- **Grid pathfinding** — 2D grid routing with obstacles and configurable connectivity

Winner of the 2025 MIT Prize for Open Data. Zero external runtime dependencies beyond `geokdtree`, `bmsspy`, and `requests`.

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
  NN_module_feature_test.py      # 28 numbered test files (00–28); named *_test.py
utils/
  test.sh                        # Run all test/*.py files with python
  prettify.sh                    # autoflake (unused imports) + black (line-length=88)
  docs.sh                        # Generate pdoc HTML docs — do NOT run unless releasing
pyproject.toml                   # Package metadata, scikit-build-core config, black config
CMakeLists.txt                   # C++ build configuration (nanobind, C++20, -O3 -march=native)
run.sh                           # Docker wrapper for all dev commands
Dockerfile                       # Python 3.14 by default; edit to test other versions
requirements.txt                 # Dev dependencies (black, autoflake, pdoc, twine, jupyter)
```

---

## Development Commands

All commands use Docker via `./run.sh`:

| Command | What it does |
|---|---|
| `./run.sh test` | Run all tests inside Docker |
| `./run.sh test test/NN_*.py` | Run a specific test file in Docker |
| `./run.sh prettify` | Format with autoflake + black |
| `./run.sh docs` | Regenerate pdoc documentation |
| `./run.sh` | Drop into a Docker shell |

> **Note:** `./run.sh` requires a TTY. In non-interactive contexts (CI, background tasks) it will fail with "the input device is not a TTY". Ask the user to run it themselves.

**Test runner** (`utils/test.sh`): Runs every `*_test.py` file in `test/` with `python`. Each file prints its own pass/fail result.

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

Tests are in `test/`. Each file is standalone: imports what it needs, runs assertions using `scgraph.utils.validate()`, and prints its own result.

**Naming convention:** `NN_module_feature_test.py` (zero-padded number prefix ensures ordered execution)

**Rough groupings:**
- `00`: C++ extension availability check
- `01–03`: Core `Graph` algorithms and scale
- `04–11`: `GeoGraph` with various built-in networks + I/O
- `12–14`: `GridGraph`
- `15–22`: Specialized (negative cycles, helpers, merge, distance matrix, BMSSP, etc.)
- `23–24`: Contraction Hierarchies save/load
- `25–28`: TNR, import, and integration tests

**Test pattern:**
```python
from scgraph import Graph
from scgraph.utils import validate

graph = Graph([{1: 5, 2: 1}, ...])
result = graph.dijkstra(origin_id=0, destination_id=5)
validate(
    name="Dijkstra basic",
    realized=result,
    expected={"path": [0, 2, 1, 3, 5], "length": 10},
)
```

When adding a new feature, add a corresponding `NN_*_test.py` file. Tests are picked up automatically by `utils/test.sh`.

---

## Coding Conventions

- **Python version**: 3.10+ (use `X | Y` union syntax, `match`, etc.)
- **Formatting**: Always run `./run.sh prettify` before committing
- **C++ fallback**: Every algorithm implemented in C++ must have a pure Python equivalent; C++ is opt-in at build time
- **No new runtime dependencies**: Runtime code must only import stdlib + `geokdtree`, `bmsspy`, `requests`
- **No unnecessary abstractions**: Don't create shared helpers unless the same logic appears 3+ times
- **DO NOT generate docs**: Only the maintainer generates docs at release time
