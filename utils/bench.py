#!/usr/bin/env python3
"""
Lightweight benchmark suite for scgraph.
Runs algorithm benchmarks across built-in geographs (marnet, us_freeway, world_highways_and_marnet)
in original, reduced, and fully reduced states, prints results to the terminal, and updates benchmark.md.

Usage:
    uv run utils/bench.py
"""

import os
import platform
import sys
import time
from pathlib import Path
from scgraph import GeoGraph
from scgraph.utils import has_cpp

BENCHMARK_MD_PATH = Path(__file__).resolve().parent.parent / "benchmark.md"

TEST_GEOGRAPHS = [
    {
        "name": "marnet",
        "description": "Global Maritime Network",
        "warmup": (0, 5),
        "combinations": [
            (100, 7999),
            (4022, 8342),
            (512, 6340),
            (1205, 9543),
            (342, 8100),
            (2530, 7120),
            (154, 4580),
            (3560, 10200),
            (870, 5520),
            (2100, 9150),
        ],
    },
    {
        "name": "us_freeway",
        "description": "US Freeway Network",
        "warmup": (0, 5),
        "combinations": [
            (1000, 9770),
            (250, 8500),
            (5100, 12300),
            (350, 14100),
            (1520, 7580),
            (4050, 11200),
            (620, 9100),
            (2530, 13400),
            (3100, 8200),
            (520, 10600),
        ],
    },
    {
        "name": "world_highways_and_marnet",
        "description": "World Highways and Maritime Network",
        "warmup": (100, 500),
        "combinations": [
            (1050, 52000),
            (21000, 153000),
            (76000, 305000),
            (121000, 452000),
            (51000, 254000),
            (182000, 403000),
            (91000, 521000),
            (31000, 352000),
            (223000, 481000),
            (102000, 501000),
        ],
    },
]

ALGORITHMS = [
    ("dijkstra", "Dijkstra"),
    ("bidirectional_dijkstra", "Bidirectional Dijkstra"),
    ("a_star", "A* (Haversine)"),
    ("dijkstra_buckets", "Dijkstra Buckets"),
]

NUM_RUNS = 10


def run_benchmark():
    print("=" * 80)
    print("scgraph Benchmark Suite")
    print(
        f"Python: {platform.python_version()} | Platform: {platform.system()} {platform.machine()} | C++ Extension: {has_cpp()}"
    )
    print("=" * 80)

    all_results = {}

    for geo_info in TEST_GEOGRAPHS:
        name = geo_info["name"]
        combinations = geo_info["combinations"]
        warmup_pair = geo_info.get("warmup", combinations[0])

        all_results[name] = {}

        for mode, red_iters in [
            ("Original", 0),
            ("Reduced", 1),
            ("Fully Reduced", -1),
        ]:
            mode_key = mode.lower().replace(" ", "_")
            print(f"\n--> Loading {name} ({mode})...")
            geo = GeoGraph.load_geograph(name, reduce_iterations=red_iters)
            g_obj = geo.graph_object
            num_nodes = len(geo.graph)
            chains = (
                sum(
                    1
                    for c in getattr(g_obj, "reduced_node_chain_ids", [])
                    if c
                )
                if mode_key != "original"
                else 0
            )

            all_results[name][mode_key] = {
                "nodes": num_nodes,
                "reduced_chains": chains,
                "timings": {},
            }

            for alg_key, alg_label in ALGORITHMS:
                kwargs = {"algorithm_fn": alg_key}
                if alg_key == "a_star":
                    kwargs["algorithm_kwargs"] = {
                        "heuristic_fn": geo.haversine
                    }

                # Warmup
                try:
                    w_orig = {
                        "latitude": geo.nodes[warmup_pair[0]][0],
                        "longitude": geo.nodes[warmup_pair[0]][1],
                    }
                    w_dest = {
                        "latitude": geo.nodes[warmup_pair[1]][0],
                        "longitude": geo.nodes[warmup_pair[1]][1],
                    }
                    geo.get_shortest_path(w_orig, w_dest, **kwargs)
                except Exception as e:
                    print(f"    {alg_label:<24} Warmup FAILED: {e}")

                # Timed iterations across random node combinations
                times = []
                for orig_id, dest_id in combinations:
                    orig = {
                        "latitude": geo.nodes[orig_id][0],
                        "longitude": geo.nodes[orig_id][1],
                    }
                    dest = {
                        "latitude": geo.nodes[dest_id][0],
                        "longitude": geo.nodes[dest_id][1],
                    }
                    try:
                        t0 = time.perf_counter()
                        res = geo.get_shortest_path(orig, dest, **kwargs)
                        dt = (time.perf_counter() - t0) * 1000
                        times.append(dt)
                    except Exception as e:
                        print(
                            f"    {alg_label:<24} query ({orig_id} -> {dest_id}) FAILED: {e}"
                        )

                if times:
                    avg_ms = sum(times) / len(times)
                    min_ms = min(times)
                    all_results[name][mode_key]["timings"][alg_key] = avg_ms
                    print(
                        f"    {alg_label:<24} : {avg_ms:8.4f} ms  (min: {min_ms:8.4f} ms, successful: {len(times)}/{len(combinations)})"
                    )
                else:
                    all_results[name][mode_key]["timings"][alg_key] = float(
                        "nan"
                    )
                    print(f"    {alg_label:<24} ALL QUERIES FAILED")

    # Print Summary Table in Terminal
    print("\n" + "=" * 90)
    print(f"{'BENCHMARK SUMMARY (Average ms over 10 random node queries)':^90}")
    print("=" * 90)

    header = (
        f"{'Graph':<28} {'State':<15} {'Nodes':<10} {'Dijkstra':>10} {'BiDijkstra':>11} {'A*':>9} {'Buckets':>10}"
    )
    print(header)
    print("-" * len(header))

    for geo_info in TEST_GEOGRAPHS:
        name = geo_info["name"]
        for mode_key, mode_lbl in [
            ("original", "Original"),
            ("reduced", "Reduced"),
            ("fully_reduced", "Fully Reduced"),
        ]:
            data = all_results[name][mode_key]
            node_str = f"{data['nodes']:,}"
            dijk = data["timings"].get("dijkstra", float("nan"))
            bidir = data["timings"].get("bidirectional_dijkstra", float("nan"))
            astar = data["timings"].get("a_star", float("nan"))
            buckets = data["timings"].get("dijkstra_buckets", float("nan"))

            row = (
                f"{name:<28} {mode_lbl:<15} {node_str:<10} "
                f"{dijk:10.4f} {bidir:11.4f} {astar:9.4f} {buckets:10.4f}"
            )
            print(row)

    print("=" * 90)

    # Generate Markdown Table for benchmark.md
    md_content = generate_markdown(all_results)
    with open(BENCHMARK_MD_PATH, "w") as f:
        f.write(md_content)

    print(f"\nBenchmark results saved to: {BENCHMARK_MD_PATH}")


def generate_markdown(results: dict) -> str:
    cpp_status = (
        "Enabled (`nanobind` C++20)" if has_cpp() else "Disabled (Pure Python)"
    )
    py_ver = platform.python_version()
    os_info = f"{platform.system()} {platform.machine()}"

    lines = [
        "# scgraph Benchmark Results",
        "",
        f"- **Environment**: Python {py_ver} ({os_info})",
        f"- **C++ Acceleration**: {cpp_status}",
        f"- **Iterations per query**: {NUM_RUNS}",
        "",
        "## Algorithm Query Performance",
        "",
        "| Graph | State | Nodes | Dijkstra (ms) | Bidirectional Dijkstra (ms) | A* (ms) | Dijkstra Buckets (ms) |",
        "|---|---|---|---|---|---|---|",
    ]

    for geo_info in TEST_GEOGRAPHS:
        name = geo_info["name"]
        for mode_key, mode_lbl in [
            ("original", "Original"),
            ("reduced", "Reduced"),
            ("fully_reduced", "Fully Reduced"),
        ]:
            data = results[name][mode_key]
            node_count = data["nodes"]
            dijk = data["timings"].get("dijkstra", 0.0)
            bidir = data["timings"].get("bidirectional_dijkstra", 0.0)
            astar = data["timings"].get("a_star", 0.0)
            buckets = data["timings"].get("dijkstra_buckets", 0.0)

            lines.append(
                f"| `{name}` | {mode_lbl} | {node_count:,} | {dijk:.4f} | {bidir:.4f} | {astar:.4f} | {buckets:.4f} |"
            )

    lines.extend(
        [
            "",
            "## Graph Reduction Impact",
            "",
            "| Graph | State | Total Nodes | Simplified Chain Nodes | Reduction Ratio |",
            "|---|---|---|---|---|",
        ]
    )

    for geo_info in TEST_GEOGRAPHS:
        name = geo_info["name"]
        orig_n = results[name]["original"]["nodes"]
        for mode_key, mode_lbl in [
            ("reduced", "Reduced (1 pass)"),
            ("fully_reduced", "Fully Reduced"),
        ]:
            chains = results[name][mode_key]["reduced_chains"]
            pct = (chains / orig_n) * 100
            lines.append(
                f"| `{name}` | {mode_lbl} | {orig_n:,} | {chains:,} | **{pct:.1f}% simplified** |"
            )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    run_benchmark()
