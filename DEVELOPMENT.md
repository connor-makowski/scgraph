# scgraph — Developer Guide

<!-- This file is read at the start of every coding session (`.claude/CLAUDE.md` and
`AGENTS.md` are links to it). Budget: 200 lines. A rule is one or two sentences;
detail lives where it is used: ARCHITECTURE.md (how the code works), pyproject.toml
(tool settings), `--help` of a script (its options). -->

`scgraph` is a Python library for shortest paths on geographic and supply chain networks: Dijkstra and its variants, A\*, BMSSP, Contraction Hierarchies (CH), Transit Node Routing (TNR), graph reduction, geographic snapping, built-in and buildable networks, 2D grids. An optional C++ extension (nanobind) speeds it up about tenfold; a pure-Python version of every algorithm is always present. Runtime dependencies: `geokdtree`, `bmsspy`, `requests`. Python 3.11 or later.

> **DO NOT RUN A RELEASE CYCLE.** No version bump, no docs generation (`utils/docs.py`, `docs/`), no build of distributions, no publication. Release steps are the owner's. If a release seems needed, say so and stop.

## Where to look

| Need | Place |
|---|---|
| Public API, parameters and their defaults | `README.md` (the docstring of `scgraph/__init__.py` repeats it) |
| Steps of a query, snapping, circuity | `ARCHITECTURE.md` §3 |
| Graph reduction | `ARCHITECTURE.md` §4 |
| Adding an algorithm | `ARCHITECTURE.md` §5; `test/42_graph_algorithm_decorator_test.py` |
| Caches and their invalidation | `ARCHITECTURE.md` §6 |
| `.scgraph` network file format | `ARCHITECTURE.md` §7; `scgraph/network_file.py` |
| Contract of a pipeline | docstring of `scgraph/pipelines/__init__.py` |
| Exceptions (`PathNotFoundError`, `NegativeCycleError`) | top of `scgraph/graph.py`; exported by `scgraph` |
| Saving hierarchies (`.chjson`, `.tnrjson`) | `save_as_…` / `load_from_…` in `contraction_hierarchies.py`, `transit_node_routing.py` |
| Benchmark sections, and which change needs which | docstring of `utils/bench.py` |
| Lint rules and their reasons | `pyproject.toml`, `[tool.ruff.lint]` |
| Build variants | `noxfile.py`; `[[tool.scikit-build.overrides]]` in `pyproject.toml` |

Two defaults to know: `Graph.reduce(iterations=-1)` reduces until nothing changes; the loaders take `reduce_iterations=0`, no reduction.

---

## Where things are

```
scgraph/
  __init__.py                  # Exports Graph, CHGraph, TNRGraph, GeoGraph, GridGraph and the two exceptions; its docstring repeats README.md
  graph.py                     # Graph: the search algorithms, trees, reduce()
  graph_reducer.py             # GraphReducer and the @algorithm decorator
  graph_utils.py               # GraphUtils (validation, path reconstruction), GraphModifiers
  geograph.py                  # GeoGraph, LazyGeoGraph: snapping, loaders, savers, cache, build_geograph
  contraction_hierarchies.py   # CHGraph
  transit_node_routing.py      # TNRGraph (extends CHGraph)
  grid.py                      # GridGraph
  network_file.py              # Reading and writing .scgraph network files
  utils.py                     # Distances, coordinate helpers, console output
  helpers/                     # geojson, polylines, hilbert, snap_index (Python twin of the C++ one), line simplification
  pipelines/                   # One module per buildable network; the contract is in __init__.py
    build.py                   # The runner: build_file, and python -m scgraph.pipelines.build
    steps/stage1_extract/      # osm, arcgis, pbf_range_streamer
    steps/stage2_intermodal/   # landmask, ports
    steps/stage3_assembly/     # assembly: CSR arrays, components, chain contraction
    steps/stage4_validation/   # validate_network, cases in cases/*.csv
  cpp/src/                     # C++ of the algorithms above; pipelines/ holds the kernels of the steps
  cpp/bindings/                # nanobind bindings (graph_bindings.cpp, pipelines_bindings.cpp)
test/                          # NN_module_feature_test.py, conftest.py (session fixtures), helpers.py
utils/                         # bench.py, compare_versions.py, prettify.py, docs.py (release only)
```

---

## Commands

| Command | What it does |
|---|---|
| `uv sync --extra dev` | Install the development dependencies and build the package |
| `uv run pytest` / `uv run pytest test/NN_*.py` | Run all tests, or one file |
| `uv run nox` | Tests with the C++ extension then without, on Python 3.11 to 3.14, and the lint session |
| `uv run nox -s tests-3.14` | Both builds on one Python version |
| `uv run utils/prettify.py` | Remove unused imports (ruff), format (black, 80 columns) |
| `uv run nox -s lint` | Check the code with ruff and the types with pyrefly |
| `uv run utils/bench.py` | Benchmark (under 30 s), writes `benchmark.md` |
| `python3 utils/compare_versions.py BASE HEAD` | Before → after of two git refs with `bench.py`; `--only`, `--backends`, `--post N` and the rest in `--help` |

If the root-owned `build/` directory causes a permission error on a fresh install, run `sudo rm -rf build/cp314-cp314-linux_x86_64`, then `uv sync --extra dev`.

---

## The C++ extension

- In `scgraph/cpp/`, built by scikit-build-core and nanobind: C++20, `-O3 -DNDEBUG -fno-math-errno -fomit-frame-pointer` (`/O2 /DNDEBUG` with MSVC).
- `SCGRAPH_REQUIRE_CPP=1` makes the build fail if the extension cannot be compiled; `SCGRAPH_NO_BUILD=1` builds the pure-Python package. Check which one is installed with `scgraph.utils.has_cpp()`.
- Without `SCGRAPH_REQUIRE_CPP=1`, a failed compilation falls back to the pure-Python package without a word (the `[[tool.scikit-build.overrides]]` of `pyproject.toml`): `uv sync` succeeds and `has_cpp()` is `False`. To see the compiler error: `uv sync --extra dev --reinstall-package scgraph -v --config-setting=build.verbose=true`.
- The C++ build is installed as a copy: reinstall (`--reinstall-package scgraph`) after changing sources, before trusting a test run.

---

## Tests

- pytest, files `test/NN_module_feature_test.py`. A new feature gets its file; a change extends the existing file of its feature.
- `test/conftest.py` gives the built-in networks as session fixtures (`marnet`, `us_freeway`, `oak_ridge_maritime`, `north_america_rail`, `world_highways_and_marnet`, `published`). They are downloaded into a temporary cache per session, never the user's; set `SCGRAPH_CACHE_DIR` to keep them between runs or to run offline.
- `test/helpers.py`: `assert_result(realized, expected)` compares results with `length` rounded to 3 decimals.
- A test states one requirement that a user relies on, through the public API, and runs in both builds. `test_reduced_graph_matches_unreduced_graph` in `test/33` is the general test of reduced graphs: a case of reduction is added there as data.
- **Fakes:** a test may replace the download (`requests.get`, or a source URL pointed at a local server); it does not replace a function or a constant of scgraph.
- A built network is checked by `validate_network` (`scgraph/pipelines/steps/stage4_validation/`): `python -m scgraph.pipelines.build NAME --validate`, or `--validate-only` for a network already in the cache.

---

## Coding Conventions

- **Checks**: Run `uv run python utils/prettify.py` then `uv run nox -s lint` before committing. A finding of `ruff` or `pyrefly` blocks a PR; a `noqa` gives its reason. The rules are in `pyproject.toml`.
- **Names**: A function starts with a verb (`build_`, `find_`, `select_`, `read_`, `get_`), a boolean function with `is_`, `has_`, `can_` or `should_`. A parameter says what it holds, with its unit (`max_km_between_nodes`), and keeps that name in every function and in the C++ binding. Internal names: `_name` in Python, `name_` for C++ members; double underscores are for Python's own methods. A renaming changes the definition and every caller in one commit.
- **Types**: Public functions annotate parameters and return, with built-in types and `X | Y`; names that start with `_` may. One kind of value has one form: a number parameter `float`; a returned length, and the weights inside a graph, `int | float`; a `[latitude, longitude]` pair `Sequence[float]`; a buffer of a kernel `array | memoryview`; a path `str | os.PathLike`; a function `Callable` (from `collections.abc`), with its signature where it is known; a default of `None` adds `| None`; a value of any type is `object`, not `Any`. A type of an optional dependency is a string.
- **Docstrings and comments**: A docstring gives summary, parameters and return; it adds the unit, the constraints and the content of a result, not the type. A comment gives a reason, in full sentences; no history, no issue number.
- **Exceptions**: A specific type (`ValueError`, `PathNotFoundError`…), the same in C++ and in pure Python.
- **Numbers**: Integer coordinates (1e-7 degree) are widened to 64 bits before a difference or a product; distances are `float64`.
- **C++ fallback**: Every algorithm implemented in C++ must have a pure Python equivalent; C++ is opt-in at build time
- **Messages**: through `logging.getLogger(__name__)` (a `NullHandler` on `scgraph`), `warnings.warn` for what the caller can avoid, exceptions for errors; no `print` and no `silent=` in new code (older functions still have `silent=`; see #115)
- **No new runtime dependencies**: Runtime code must only import stdlib + `geokdtree`, `bmsspy`, `requests`; an optional reader may need an optional extra (`osm`: osmium), imported only when it is called
- **No unnecessary abstractions**: Don't create shared helpers unless the same logic appears 3+ times
- **Don't mutate caller-provided arguments**: Copy small inputs (option dicts, lists of blocks, etc.) before modifying them; large graph data may be kept without copying for performance, so say so in the docstring

---

## Contribution Workflow

- A change to the public API edits `README.md` and the docstring of `scgraph/__init__.py` identically, in the same PR.
- `dev` has no users: a file or a name that only an unreleased state of `dev` produced owes no compatibility and gets no migration code. What release 3.6.0 wrote or exposed must keep working.
- Open an issue first, then one branch and one PR per issue. A PR title states the outcome and ends with its issue number: `Fix … (#N)`.
- Branches live in this repository (`fix/...`, `perf/...`, `docs/...`, `test/...`) and start from `dev`; PRs target `dev`, never `main`.
- Never commit directly to `dev` or `main`. Merge PRs with a merge commit (no squash or rebase), so that stacked PRs keep their commits, then delete the branch.
- A PR that depends on another open PR targets that PR's branch until it is merged.
- A PR that changes runtime code (`scgraph/`) includes a before → after from `utils/bench.py` on the sections it touches, against its target branch (see *Commands*; sections `load`, `reduce`, `query`, `grid`, `hierarchy`, `misc`; `--backends cpp,python` if pure-Python code changed).
- `Closes #N` only links and closes issues for PRs into `main`. For a PR into `dev`, also link the issue by hand (the PR's *Development* sidebar, or `gh api graphql` with the `addCloseIssueReferences` mutation): the issue then shows the PR but stays open.
- After merging into `dev`, add the `merged in dev` label and the "Next release" milestone to the issue; it is closed when `dev` is merged into `main` (list it with `Closes #N` in that PR).
- Only the owner merges `dev` into `main` and releases.

---

## Release Checklist (owner only — do not execute)

1. Set `version` in `pyproject.toml` (and `uv.lock`) to the release number, dropping the `.devN` suffix
2. Run `uv run python utils/prettify.py`
3. Run `uv run nox` — all sessions must pass
4. Run `uv run python utils/docs.py` to regenerate docs
5. Build and publish via `publish.sh`
6. Right after the release, set the next development version on `dev` with a `.dev0` suffix (PEP 440), e.g. `4.1.0.dev0`
