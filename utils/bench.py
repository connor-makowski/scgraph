#!/usr/bin/env python3
"""
Unified benchmark suite for scgraph.

Two uses of one script:

1. Snapshot: with no argument, runs every section once (<30s with C++) and writes
   benchmark.md at the repository root.

       uv run utils/bench.py

2. Before/after deltas (a PR, or dev against the release): utils/compare_versions.py
   builds the environment of each version, runs this script several times alternating
   the versions, then compares and writes a report.

       python3 utils/compare_versions.py origin/dev my-branch --only reduce

   By hand, each environment holds one version installed from its checkout with the
   lockfile's versions (`uv sync --no-editable`; C++ build: SCGRAPH_REQUIRE_CPP=1,
   pure-Python build: SCGRAPH_NO_BUILD=1) and its own SCGRAPH_CACHE_DIR; run once per
   environment untimed, with a scratch --json (without it a full run overwrites
   benchmark.md), then --json runs alternating the versions, then
   `python utils/bench.py --compare "base-*.json" "head-*.json"`.

   --compare first reports the rows whose best time and median time over the runs
   of each side both move beyond x1.15 in the same direction; it also lists any
   difference in route lengths, node counts or failures. Memory rows (Linux) use the
   median of the runs and are reported beyond x1.05 and 5 MiB. It then prints the
   tables of benchmark.md with both versions side by side (without reduce's Added
   memory, mostly noise, and the CH/TNR speed-up columns, which are ratios already).
   A surprising row is simply re-run.

Subsets (--only) and the changes that need them:
    load       load_geograph as each version does it (snap index included), first query
               (loaders, file formats, graph construction, snapping index)
    reduce     reduce(1) and reduce(-1) times and results (graph_reducer)
    query      get_shortest_path per algorithm, unreduced and reduced
               (graph.py, geograph.py queries, cpp/src/graph*)
    grid       GridGraph (grid.py, bucket algorithms)
    hierarchy  contraction hierarchies and TNR
    misc       distance matrix, cached shortest path, Visvalingam

Every time is in ms from one perf_counter reading, or a mean over the pairs of a row
(the cached tree hit: over 100 calls); one untimed call per algorithm warms up each row.
Load times read the file from the OS cache (warm). 3.6.0 (a GeoKDTree) and later
versions (since #157) build the snapping index while loading; "Index in Load" estimates
that part of Load by a second build, timed alone after the first query. Memory (Linux
only): "Peak" is the peak RSS of the process during load and first query, "Added" the
peak during reduce() minus the RSS before it (the peak is reset through
/proc/self/clear_refs). Rows run in sequence in one process, so a row's time and memory
depend on the rows before it: compare runs of the same --only and --networks. Reduction
states are explicit (Original, Reduced = 1 pass, Fully Reduced = until no change): no
row depends on the version's reduction default.
"""

import argparse
import gc
import glob
import json
import os
import platform
import subprocess
import statistics
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

BENCHMARK_MD_PATH = Path(__file__).resolve().parent.parent / "benchmark.md"
SECTIONS = ["load", "reduce", "query", "grid", "hierarchy", "misc"]
# Passed explicitly: 3.6.0 reads only its cache_dir argument, not the variable
CACHE_DIR = os.environ.get("SCGRAPH_CACHE_DIR")
NETWORKS = [
    "oak_ridge_maritime",
    "north_america_rail",
    "marnet",
    "us_freeway",
    "world_highways_and_marnet",
]
# Fixed (latitude, longitude) pairs, nodes of the built-in networks: the same nodes
# in any numbering. QUERY_PAIRS: query section (its first pair also times the first
# query); FIRST_PAIRS: first query of the other networks; HIERARCHY_PAIRS: section 5.
QUERY_PAIRS = {
    "marnet": [
        ((43.5148, 37.2408), (39.5276, 49.6551)),
        ((22.2383, 113.6934), (-17.5438, -2.5937)),
        ((30.0, -20.0), (50.5587, -176.9962)),
        ((-14.5165, 174.8274), (52.2284, -10.4723)),
        ((-23.0, 13.0), (46.2179, -72.8064)),
    ],
    "us_freeway": [
        ((47.823, -122.274), (25.979, -80.23)),
        ((34.074, -117.999), (41.182, -73.143)),
        ((39.464, -77.991), (44.806, -123.029)),
        ((32.774, -115.505), (25.964, -80.166)),
        ((43.408, -71.597), (40.702, -73.993)),
    ],
    "world_highways_and_marnet": [
        ((14.648, 108.409), (26.252, 83.477)),
        ((37.686, 37.874), (35.108, 128.839)),
        ((38.01, 23.844), (33.933, 133.21)),
        ((44.496, 26.079), (31.965, 120.966)),
        ((9.264, -9.025), (34.139, -97.157)),
    ],
}
FIRST_PAIRS = {
    "oak_ridge_maritime": ((51.3, 179.5), (43.7258, -69.7537)),
    "north_america_rail": ((42.652, -112.191), (29.715, -95.333)),
}
HIERARCHY_PAIRS = {
    "marnet": [
        ((37.9027, 12.3641), (52.8569, 1.7064)),
        ((-53.0907, -73.4436), (29.385, -89.5885)),
        ((7.5167, -117.4664), (-6.3133, -146.2597)),
        ((63.3996, 7.3788), (44.1888, -7.2684)),
        ((10.0, 103.7407), (-19.0009, 41.8471)),
        ((42.1021, 19.0579), (57.7286, -39.3167)),
        ((-2.512, -92.4763), (-35.1023, -15.3071)),
        ((63.0298, -1.7065), (36.7, 31.0)),
        ((-12.5384, -137.5827), (2.5118, -42.4761)),
        ((-12.7045, 114.9835), (-5.0572, -115.0001)),
    ],
    "us_freeway": [
        ((35.276, -107.984), (43.129, -77.635)),
        ((21.364, -157.781), (48.75, -111.862)),
        ((39.477, -91.3), (38.619, -90.264)),
        ((33.602, -101.845), (30.217, -82.707)),
        ((40.751, -111.911), (44.776, -91.527)),
        ((38.579, -112.331), (37.039, -113.598)),
        ((35.625, -80.861), (42.861, -71.334)),
        ((32.092, -81.131), (42.605, -83.174)),
        ((34.156, -118.243), (34.266, -118.472)),
        ((42.153, -87.874), (44.041, -106.638)),
    ],
}
ALGORITHMS = [
    ("dijkstra", "Dijkstra"),
    ("bidirectional_dijkstra", "BiDijkstra"),
    ("a_star", "A* Haversine"),
    ("dijkstra_buckets", "Buckets"),
    ("bidirectional_buckets", "BiBuckets"),
    ("bmssp", "BMSSP"),
]
STATES = [("Original", 0), ("Reduced", 1), ("Fully Reduced", -1)]
THRESHOLD = 1.15
HITS = 100
# Memory varies little between runs: report beyond x1.05 and at least 5 MiB
MEMORY_THRESHOLD = 1.05
MEMORY_FLOOR = 5


class Results:
    """Measurements of one run: timed rows, displayed counts, and check values."""

    def __init__(self, sections):
        self.sections = sections
        # One cell per (section, row, column): {"value", "unit", "failed"}
        self.cells = {}
        # Values that must not change between versions (lengths, node counts)
        self.checks = {}

    def cell(self, section, row, column, value, unit="ms", failed=0):
        if unit == "MiB" and value is None:
            return  # memory is measured on Linux only
        if section in self.sections:
            self.cells[(section, tuple(row), column)] = {
                "value": value,
                "unit": unit,
                "failed": failed,
            }

    def check(self, section, key, value):
        if section in self.sections:
            self.checks[f"{section}|{key}"] = value


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000, out


def memory_mark():
    """Reset the process's peak RSS to its current RSS; current RSS in MiB (Linux)."""
    try:
        with open("/proc/self/clear_refs", "w") as f:
            f.write("5")
    except OSError:
        return None
    return memory_read("VmRSS")


def memory_read(field="VmHWM"):
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(field + ":"):
                return int(line.split()[1]) / 1024
    return None


def mean_time(results, section, row, column, calls, key):
    """Warm up with the first call, then time every call; failures are counted."""
    try:
        calls[0]()
    except Exception:
        pass
    times, failed = [], 0
    for i, call in enumerate(calls):
        try:
            ms, out = timed(call)
        except Exception as error:
            failed += 1
            results.check(
                section, f"{key}|{i}", f"error: {type(error).__name__}"
            )
            continue
        times.append(ms)
        length = out.get("length") if isinstance(out, dict) else None
        results.check(section, f"{key}|{i}", round_length(length))
    value = sum(times) / len(times) if times else None
    results.cell(section, row, column, value, failed=failed)


def round_length(length):
    # Lengths are compared between versions: 9 significant digits absorb summation
    # order, not a different route
    return None if length is None else float(f"{length:.9g}")


def point(coordinates):
    return {"latitude": coordinates[0], "longitude": coordinates[1]}


def reduced_counts(graph_object):
    is_red = graph_object.is_reduced
    rg = graph_object.reduced_graph
    nodes = sum(1 for r in is_red if not r)
    edges = sum(len(rg[i]) for i, r in enumerate(is_red) if not r)
    return nodes, edges


def query_calls(geo, pairs, algorithm):
    kwargs = {"algorithm_fn": algorithm}
    if algorithm == "a_star":
        kwargs["algorithm_kwargs"] = {"heuristic_fn": geo.haversine}
    return [
        lambda u=u, v=v: geo.get_shortest_path(point(u), point(v), **kwargs)
        for u, v in pairs
    ]


def bench_networks(results, networks):
    """Sections load, reduce and query, one network at a time (one copy in memory)."""
    from scgraph import GeoGraph

    sections = results.sections
    for net in networks:
        print(f"  - {net}")
        marked = memory_mark()
        load_ms, geo = timed(
            GeoGraph.load_geograph,
            net,
            cache_dir=CACHE_DIR,
            reduce_iterations=0,
        )
        n = len(geo.nodes)

        # Time to the first answer: anything built at first use
        u, v = QUERY_PAIRS[net][0] if net in QUERY_PAIRS else FIRST_PAIRS[net]
        first_ms, first_failed = None, 1
        try:
            first_ms, out = timed(
                geo.get_shortest_path,
                point(u),
                point(v),
                algorithm_fn="dijkstra",
            )
            first_failed = 0
            results.check("load", f"{net}|first", round_length(out["length"]))
        except Exception as error:
            results.check(
                "load", f"{net}|first", f"error: {type(error).__name__}"
            )
        # Peak of the process during load and first query (includes the interpreter)
        peak = memory_read() if marked is not None else None
        # Snap index, built while loading (in Load): built again here, alone
        index_ms = None
        if "load" in sections:
            if hasattr(type(geo), "snap_index"):
                geo.snap_index = None
                index_ms = timed(getattr, geo, "snap_index")[0]
            else:  # 3.6.0: a GeoKDTree
                from geokdtree import GeoKDTree

                index_ms = timed(GeoKDTree, points=geo.nodes)[0]
        # Counted after the peak: reading geo.graph may build a Python copy
        edges = sum(len(e) for e in geo.graph)
        results.cell("load", [net], "Nodes", n, unit="count")
        results.cell("load", [net], "Edges", edges, unit="count")
        results.cell("load", [net], "Load", load_ms)
        results.cell("load", [net], "Index in Load", index_ms)
        results.cell(
            "load", [net], "First query", first_ms, failed=first_failed
        )
        results.cell("load", [net], "Peak", peak, unit="MiB")

        if "reduce" in sections or ("query" in sections and net in QUERY_PAIRS):
            for state, iterations in STATES:
                if iterations:
                    before = memory_mark()
                    ms, _ = timed(
                        geo.graph_object.reduce, iterations=iterations
                    )
                    added = (
                        memory_read() - before if before is not None else None
                    )
                    nodes, red_edges = reduced_counts(geo.graph_object)
                    row = [net, state]
                    results.cell("reduce", row, "Reduce", ms)
                    results.cell("reduce", row, "Added", added, unit="MiB")
                    results.cell(
                        "reduce", row, "Effective nodes", nodes, "count"
                    )
                    results.cell(
                        "reduce", row, "Effective edges", red_edges, "count"
                    )
                    results.cell(
                        "reduce",
                        row,
                        "Node reduction %",
                        100 * (n - nodes) / n,
                        "%",
                    )
                else:
                    nodes = n
                if net not in QUERY_PAIRS or "query" not in sections:
                    continue
                row = [net, state]
                results.cell(
                    "query", row, "Effective nodes", nodes, unit="count"
                )
                for algorithm, label in ALGORITHMS:
                    # About 1 s per query on the world network: it would double the run
                    if (
                        algorithm == "bmssp"
                        and net == "world_highways_and_marnet"
                    ):
                        continue
                    mean_time(
                        results,
                        "query",
                        row,
                        label,
                        query_calls(geo, QUERY_PAIRS[net], algorithm),
                        f"{net}|{state}|{algorithm}",
                    )
        del geo
        gc.collect()


def bench_gridgraphs(results):
    from scgraph import GridGraph

    configs = [
        ("50x50 Open Grid", 50, [], None),
        ("100x100 Open Grid", 100, [], None),
        ("200x200 Open Grid", 200, [], None),
        (
            "100x100 L-Barrier & Shape",
            100,
            [(50, i) for i in range(10, 100)],
            [(0, 0), (0, 1), (1, 0), (1, 1)],
        ),
    ]
    algorithms = [
        ("Dijkstra", {"algorithm_fn": "dijkstra"}),
        (
            "A* Manhattan",
            {"algorithm_fn": "a_star", "heuristic_fn": "manhattan"},
        ),
        ("Buckets", {"algorithm_fn": "dijkstra_buckets"}),
        ("BiBuckets", {"algorithm_fn": "bidirectional_buckets"}),
    ]
    for name, size, blocks, shape in configs:
        print(f"  - {name}")
        ms, grid = timed(
            GridGraph,
            x_size=size,
            y_size=size,
            blocks=blocks,
            shape=shape,
            add_exterior_walls=True,
        )
        results.cell("grid", [name], "Nodes", len(grid.graph), unit="count")
        results.cell("grid", [name], "Creation", ms)
        orig, dest = {"x": 1, "y": 1}, {"x": size - 2, "y": size - 2}
        for label, kwargs in algorithms:
            call = lambda kw=kwargs: grid.get_shortest_path(
                orig, dest, cache=False, **kw
            )
            mean_time(results, "grid", [name], label, [call], f"{name}|{label}")


def bench_hierarchy(results):
    from scgraph import GeoGraph, Graph

    for net in ["marnet", "us_freeway"]:
        geo = GeoGraph.load_geograph(
            net, cache_dir=CACHE_DIR, reduce_iterations=0
        )
        adj = geo.graph
        node_id = {(p[0], p[1]): i for i, p in enumerate(geo.nodes)}
        pairs = [(node_id[u], node_id[v]) for u, v in HIERARCHY_PAIRS[net]]
        del geo
        dijkstra_original = None
        for state, iterations in STATES[:2]:
            print(f"  - {net} ({state})")
            g = Graph(adj)
            if iterations:
                g.reduce(iterations=iterations)
            row = [net, state]
            key = f"{net}|{state}"
            mean_time(
                results,
                "hierarchy",
                row,
                "Dijkstra",
                [lambda u=u, v=v: g.dijkstra(u, v) for u, v in pairs],
                f"{key}|dijkstra",
            )
            ms, _ = timed(g.create_contraction_hierarchy)
            results.cell("hierarchy", row, "CH Prep", ms)
            mean_time(
                results,
                "hierarchy",
                row,
                "CH Query",
                [
                    lambda u=u, v=v: g.contraction_hierarchy(u, v)
                    for u, v in pairs
                ],
                f"{key}|ch",
            )
            ms, _ = timed(g.create_tnr_hierarchy, num_transit_nodes=50)
            results.cell("hierarchy", row, "TNR Prep", ms)
            mean_time(
                results,
                "hierarchy",
                row,
                "TNR Query",
                [lambda u=u, v=v: g.tnr(u, v) for u, v in pairs],
                f"{key}|tnr",
            )
            cells = results.cells
            dijkstra = cells.get(("hierarchy", tuple(row), "Dijkstra"), {})
            if dijkstra_original is None:
                dijkstra_original = dijkstra.get("value")
            for query in ["CH", "TNR"]:
                q = cells.get(("hierarchy", tuple(row), f"{query} Query"), {})
                speedup = (
                    dijkstra_original / q["value"]
                    if dijkstra_original and q.get("value")
                    else None
                )
                # Relative to the unreduced Dijkstra of the same network
                results.cell("hierarchy", row, f"{query} Speedup", speedup, "x")


def bench_misc(results):
    from scgraph import GeoGraph
    from scgraph.helpers.visvalingam import visvalingam

    uf_geo = GeoGraph.load_geograph(
        "us_freeway", cache_dir=CACHE_DIR, reduce_iterations=0
    )
    # Builds anything made at first use, so that it is not timed below
    uf_geo.get_shortest_path(*map(point, QUERY_PAIRS["us_freeway"][0]))

    n = 10
    lats = [34.0 + i * 8.0 / n for i in range(n)]
    lons = [-118.0 + i * 33.0 / n for i in range(n)]
    dm_nodes = [{"latitude": a, "longitude": o} for a in lats for o in lons]
    ms, _ = timed(
        uf_geo.distance_matrix,
        dm_nodes,
        off_graph_circuity=1,
        output_units="km",
    )
    results.cell(
        "misc",
        ["Distance Matrix (10x10 = 100 points)", "us_freeway"],
        "Time",
        ms,
    )

    orig = {"latitude": 34.0522, "longitude": -118.2437}
    dest = {"latitude": 40.7128, "longitude": -74.0060}
    uf_geo.graph_object.reset_cache()

    def cached():
        return uf_geo.get_shortest_path(
            orig, dest, algorithm_fn="cached_shortest_path"
        )

    def hits():
        # A hit takes about 0.1 ms: one garbage collection would decide one call
        for _ in range(HITS):
            out = cached()
        return out

    for label, call, calls in [
        ("Tree Build", cached, 1),
        ("Tree Hit", hits, HITS),
    ]:
        ms, out = timed(call)
        results.cell(
            "misc",
            [f"Cached Shortest Path ({label})", "us_freeway"],
            "Time",
            ms / calls,
        )
        results.check("misc", f"cached|{label}", round_length(out["length"]))

    vis_data = [[i, i % 2 + (i / 10000)] for i in range(10000)]
    visvalingam(vis_data, pct_to_keep=0.1)
    ms, _ = timed(visvalingam, vis_data, pct_to_keep=0.1)
    results.cell(
        "misc",
        ["Visvalingam Line Simplification", "10,000 coordinates"],
        "Time",
        ms,
    )


def cpu_model():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    if platform.system() == "Darwin":
        try:
            return subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return platform.processor() or platform.machine()


def ram_gib():
    try:
        return round(
            os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**30, 1
        )
    except (AttributeError, OSError, ValueError):
        return None


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def environment(commit):
    from scgraph.utils import has_cpp

    return {
        "commit": commit,
        "backend": "C++" if has_cpp() else "Python",
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.machine()}",
        "cpu": cpu_model(),
        "ram_gib": ram_gib(),
        "packages": {
            name: package_version(name)
            for name in ["scgraph", "bmsspy", "geokdtree"]
        },
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fmt(value, unit):
    if value is None:
        return "failed" if unit == "ms" else "n/a"
    if unit == "count":
        return f"{value:,}"
    if unit == "MiB":
        return f"{value:,.0f}" if abs(value) >= 0.5 else "0"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "x":
        return f"{value:.1f}x"
    if value >= 100:
        return f"{value:,.0f}"
    if value >= 10:
        return f"{value:.1f}"
    if value >= 1:
        return f"{value:.2f}"
    return f"{value:.3g}"


TABLES = {
    "load": ("Built-in GeoGraph Loading", ["Network"]),
    "reduce": ("Graph Reduction", ["Network", "State"]),
    "query": ("Shortest Path Queries on GeoGraphs", ["Graph", "State"]),
    "grid": ("GridGraph Pathfinding & Obstacles", ["Configuration"]),
    "hierarchy": (
        "Hierarchical Preprocessing & Routing (CH & TNR)",
        ["Graph", "State"],
    ),
    "misc": (
        "Specialized Features & Operations",
        ["Feature / Operation", "Input"],
    ),
}


def markdown_tables(cells):
    lines = []
    for number, section in enumerate(SECTIONS, 1):
        rows, columns = {}, {}
        for (sec, row, column), c in cells.items():
            if sec == section:
                rows.setdefault(row, {})[column] = c
                columns.setdefault(column, c["unit"])
        if not rows:
            continue
        title, row_headers = TABLES[section]
        headers = row_headers + [
            (
                f"{col} (ms)"
                if unit == "ms"
                else f"{col} (MiB)" if unit == "MiB" else col
            )
            for col, unit in columns.items()
        ]
        lines += [f"## {number}. {title}", ""]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "---|" * len(headers))
        for row, values in rows.items():
            labels = [f"`{row[0]}`" if row[0] in NETWORKS else row[0]]
            labels += list(row[1:])
            out = []
            for col in columns:
                c = values.get(col)
                text = "" if c is None else fmt(c["value"], c["unit"])
                if c and c["failed"] and c["value"] is not None:
                    text += f" ({c['failed']} failed)"
                out.append(text)
            lines.append("| " + " | ".join(labels + out) + " |")
        lines.append("")
    return lines


def run(sections, networks, json_path, commit):
    env = environment(commit)
    print("=" * 80)
    print("scgraph benchmark suite")
    print(
        f"Python {env['python']} | {env['os']} | {env['cpu']}"
        f" | backend: {env['backend']}"
    )
    print("=" * 80)
    results = Results(sections)
    t0 = time.perf_counter()
    if {"load", "reduce", "query"} & set(sections):
        print("\nNetworks (load, reduce, query)...")
        bench_networks(results, networks)
    if "grid" in sections:
        print("\nGridGraph...")
        bench_gridgraphs(results)
    if "hierarchy" in sections:
        print("\nCH & TNR...")
        bench_hierarchy(results)
    if "misc" in sections:
        print("\nSpecialized features...")
        bench_misc(results)
    total = time.perf_counter() - t0

    tables = markdown_tables(results.cells)
    print("\n" + "\n".join(tables))
    print(f"Finished in {total:.2f} s")
    if json_path:
        record = {
            "environment": env,
            "sections": sections,
            "networks": networks,
            "total_s": total,
            "cells": [
                {"section": s, "row": list(r), "column": c, **v}
                for (s, r, c), v in results.cells.items()
            ],
            "checks": results.checks,
        }
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(record, indent=1))
        print(f"Results written to {json_path}")
    elif sections == SECTIONS and networks == NETWORKS:
        lines = [
            "# scgraph Benchmark Results",
            "",
            f"- **Environment**: Python {env['python']} ({env['os']}), {env['cpu']}",
            f"- **Backend**: {env['backend']}",
            f"- **scgraph**: {env['packages']['scgraph']}"
            + (f" (commit {env['commit']})" if env["commit"] else ""),
            f"- **Date**: {env['date'][:10]}",
            f"- **Total Suite Execution Time**: {total:.2f}s",
            "- **Protocol**: one run; each value is one reading, or the mean over the"
            f" pairs of the row (the cached tree hit: over {HITS} calls), after one"
            " untimed call. Compare only with runs on the same machine.",
            "",
        ] + tables
        BENCHMARK_MD_PATH.write_text("\n".join(lines))
        print(f"Markdown written to {BENCHMARK_MD_PATH}")


def load_runs(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f"No file matches {pattern}")
    return [json.loads(Path(f).read_text()) for f in files]


def run_times(runs):
    """Per time row: the values of the runs, and the largest failure count."""
    values, failed = {}, {}
    for run_ in runs:
        for c in run_["cells"]:
            key = (c["section"], tuple(c["row"]), c["column"])
            if c["unit"] != "ms":
                continue
            failed[key] = max(failed.get(key, 0), c["failed"])
            values.setdefault(key, [])
            if c["value"] is not None:
                values[key].append(c["value"])
    return values, failed


def median_memory(runs):
    values = {}
    for run_ in runs:
        for c in run_["cells"]:
            if c["unit"] == "MiB" and c["value"] is not None:
                key = (c["section"], tuple(c["row"]), c["column"])
                values.setdefault(key, []).append(c["value"])
    return {k: statistics.median(v) for k, v in values.items()}


def checks_of(runs):
    merged = {}
    for run_ in runs:
        for key, value in run_["checks"].items():
            merged.setdefault(key, set()).add(json.dumps(value))
    for run_ in runs:
        for c in run_["cells"]:
            if c["unit"] == "count":
                key = f"{c['section']}|{'|'.join(c['row'])}|{c['column']}"
                merged.setdefault(key, set()).add(json.dumps(c["value"]))
    return merged


def moves(before, after):
    """The rule of --compare: best and median times both beyond THRESHOLD, same way."""
    best = min(before) / min(after)
    median = statistics.median(before) / statistics.median(after)
    return min(best, median) >= THRESHOLD or max(best, median) <= 1 / THRESHOLD


def memory_moves(before, after):
    return abs(after - before) >= MEMORY_FLOOR and (
        after >= before * MEMORY_THRESHOLD or before >= after * MEMORY_THRESHOLD
    )


def side_by_side(base, head, labels):
    """The tables of benchmark.md for both versions: best time (memory: median)."""
    times_b, _ = run_times(base)
    times_h, _ = run_times(head)
    mem_b, mem_h = median_memory(base), median_memory(head)
    rows, info = {}, {}
    for run_ in (head[0], base[0]):
        for c in run_["cells"]:
            key = (c["section"], tuple(c["row"]))
            if c["unit"] in ("count", "%"):
                info.setdefault(key, {}).setdefault(
                    c["column"], (c["value"], c["unit"])
                )
            elif c["unit"] in ("ms", "MiB") and (c["section"], c["column"]) != (
                "reduce",
                "Added",  # mostly noise below 5 MiB, about 0 after Reduced
            ):
                columns = rows.setdefault(key, [])
                if (c["column"], c["unit"]) not in columns:
                    columns.append((c["column"], c["unit"]))
    lines = []
    for number, section in enumerate(SECTIONS, 1):
        keys = [k for k in rows if k[0] == section]
        if not keys:
            continue
        title, row_headers = TABLES[section]
        info_columns = list(info.get(keys[0], {}))
        measures = {m for k in keys for m in rows[k]}
        single = next(iter(measures)) if len(measures) == 1 else None
        values = (
            [f"{labels[0]} ({single[1]})", f"{labels[1]} ({single[1]})"]
            if single
            else ["Measure", *labels]
        )
        headers = row_headers + info_columns + values + ["Change"]
        lines += [f"## {number}. {title}", ""]
        lines += [
            "| " + " | ".join(headers) + " |",
            "|" + "---|" * len(headers),
        ]
        for key in keys:
            row = key[1]
            lead = [f"`{row[0]}`" if row[0] in NETWORKS else row[0], *row[1:]]
            lead += [
                fmt(*info.get(key, {}).get(c, (None, "n/a")))
                for c in info_columns
            ]
            for column, unit in rows[key]:
                cell = (section, row, column)
                if unit == "ms":
                    vb, vh = times_b.get(cell) or [], times_h.get(cell) or []
                    b, h = min(vb, default=None), min(vh, default=None)
                    if b and h:
                        text = (
                            f"×{b / h:.2f} faster"
                            if b >= h
                            else f"×{h / b:.2f} slower"
                        )
                        text = f"**{text}**" if moves(vb, vh) else text
                    else:
                        text = "not in both"
                else:
                    b, h = mem_b.get(cell), mem_h.get(cell)
                    text = (
                        "–"
                        if b is None or h is None or b < 0.5
                        else f"{(h - b) / b:+.0%}"
                    )
                    if b is not None and h is not None and memory_moves(b, h):
                        text = f"**{text}**"
                measure = [] if single else [f"{column} ({unit})"]
                lines.append(
                    "| "
                    + " | ".join(
                        lead + measure + [fmt(b, unit), fmt(h, unit), text]
                    )
                    + " |"
                )
                lead = [""] * len(lead)
        lines.append("")
    totals = [
        statistics.median(r["total_s"] for r in runs) for runs in (base, head)
    ]
    lines.append(
        f"Whole run (median): {labels[0]} {totals[0]:.1f} s,"
        f" {labels[1]} {totals[1]:.1f} s."
    )
    return lines


def compare(base_pattern, head_pattern, labels=None):
    base, head = load_runs(base_pattern), load_runs(head_pattern)
    env_b, env_h = base[0]["environment"], head[0]["environment"]
    for name in ["backend", "cpu", "python"]:
        if env_b[name] != env_h[name]:
            print(f"Warning: {name} differs: {env_b[name]} vs {env_h[name]}")
    for name in ["sections", "networks"]:
        if base[0][name] != head[0][name]:
            print(f"Warning: {name} differ: {base[0][name]} vs {head[0][name]}")
    times_b, failed_b = run_times(base)
    times_h, failed_h = run_times(head)

    # A row moves only if its best time and its median time both move beyond the
    # threshold in the same direction: one lucky or unlucky run does not count
    changed, unchanged, missing = [], 0, []
    for key in sorted(set(times_b) | set(times_h), key=str):
        vb, vh = times_b.get(key) or [], times_h.get(key) or []
        section, row, column = key
        case = f"{section}: {', '.join(row)}, {column}"
        if not vb or not vh:
            b, h = min(vb, default=None), min(vh, default=None)
            missing.append(
                f"{case} (before {fmt(b, 'n/a')}, after {fmt(h, 'n/a')})"
            )
            continue
        if moves(vb, vh):
            best = min(vb) / min(vh)
            median = statistics.median(vb) / statistics.median(vh)
            changed.append((case, min(vb), min(vh), best, median))
        else:
            unchanged += 1

    commit = lambda e: e["commit"] or "?"
    print(
        f"Speed ({len(base)} and {len(head)} interleaved runs, "
        f"{env_h['backend']}, {env_h['cpu']}, {commit(env_b)} → {commit(env_h)}; "
        f"rows whose best and median times both move beyond "
        f"±{(THRESHOLD - 1) * 100:.0f} %; before and after: best times):\n"
    )
    if changed:
        print("| Case | Before (ms) | After (ms) | Speedup | Median speedup |")
        print("|---|---|---|---|---|")
        for case, b, h, best, median in changed:
            print(
                f"| {case} | {fmt(b, 'ms')} | {fmt(h, 'ms')} | ×{best:.2f}"
                f" | ×{median:.2f} |"
            )
        print()
    print(f"{unchanged} other rows: no clear change.")

    mem_b, mem_h = median_memory(base), median_memory(head)
    moved, steady = [], 0
    for key in sorted(set(mem_b) & set(mem_h), key=str):
        b, h = mem_b[key], mem_h[key]
        if memory_moves(b, h):
            moved.append((key, b, h, h / b if b else float("inf")))
        else:
            steady += 1
    if moved:
        print("\nMemory (median of the runs; peak RSS of the step, Linux):\n")
        print("| Case | Before (MiB) | After (MiB) | After / before |")
        print("|---|---|---|---|")
        for (section, row, column), b, h, ratio in moved:
            case = f"{section}: {', '.join(row)}, {column}"
            print(f"| {case} | {b:,.0f} | {h:,.0f} | ×{ratio:.2f} |")
        print()
    if mem_b or mem_h:
        print(f"{steady} memory rows: no clear change.")
    for line in missing:
        print(f"Not comparable: {line}")
    for key in sorted(set(failed_b) | set(failed_h), key=str):
        if failed_b.get(key, 0) != failed_h.get(key, 0):
            section, row, column = key
            print(
                f"Failures differ: {section}: {', '.join(row)}, {column}: "
                f"{failed_b.get(key, 0)} → {failed_h.get(key, 0)}"
            )

    checks_b, checks_h = checks_of(base), checks_of(head)
    common = set(checks_b) & set(checks_h)
    unstable = [
        k for k in common if len(checks_b[k]) > 1 or len(checks_h[k]) > 1
    ]
    differ = sorted(
        k for k in common if checks_b[k] != checks_h[k] and k not in unstable
    )
    lengths = [
        k
        for k in common
        if not k.endswith(("nodes", "edges", "Nodes", "Edges"))
    ]
    if not differ:
        print(
            f"Results identical on all {len(common)} checks ({len(lengths)} routes)."
        )
    else:
        print(f"Results differ on {len(differ)} of {len(common)} checks:")
        for k in differ:
            b, h = sorted(checks_b[k])[0], sorted(checks_h[k])[0]
            print(f"  {k}: {b} → {h}")
    for k in sorted(unstable):
        print(f"Varies between runs of one side: {k}")

    labels = labels or [commit(env_b), commit(env_h)]
    print("\n" + "\n".join(side_by_side(base, head, labels)))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--only", help="comma-separated sections: " + ",".join(SECTIONS)
    )
    parser.add_argument(
        "--networks",
        help="comma-separated networks for load, reduce and query (hierarchy and"
        " misc use marnet and us_freeway): " + ",".join(NETWORKS),
    )
    parser.add_argument("--json", help="write the measurements to this file")
    parser.add_argument(
        "--commit", help="commit of the installed scgraph, recorded"
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASE_GLOB", "HEAD_GLOB"),
        help="compare two sets of --json files: rows that move, then both versions"
        " side by side in the tables of benchmark.md",
    )
    parser.add_argument(
        "--labels",
        nargs=2,
        metavar=("BASE", "HEAD"),
        help="names of the two versions in the --compare tables (default: commits)",
    )
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare, labels=args.labels)
        return

    def pick(text, allowed):
        if not text:
            return list(allowed)
        chosen = [x.strip() for x in text.split(",")]
        unknown = [x for x in chosen if x not in allowed]
        if unknown:
            parser.error(f"unknown: {', '.join(unknown)}")
        return [x for x in allowed if x in chosen]

    run(
        pick(args.only, SECTIONS),
        pick(args.networks, NETWORKS),
        args.json,
        args.commit,
    )


if __name__ == "__main__":
    main()
