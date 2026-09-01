#!/usr/bin/env python3
"""
Unified benchmark suite for scgraph.
Runs fast (<30s) comprehensive benchmarks across GeoGraphs, GridGraphs,
hierarchical routing (CH/TNR), and specialized operations.
Outputs summary tables to terminal and writes benchmark.md.

Usage:
    uv run utils/bench.py
"""

import platform
import random
import time
from pathlib import Path
from scgraph import GeoGraph, GridGraph, Graph
from scgraph.utils import has_cpp
from scgraph.helpers.visvalingam import visvalingam

BENCHMARK_MD_PATH = Path(__file__).resolve().parent.parent / "benchmark.md"


def bench_geograph_loading():
    """Benchmark 1 & 2: Built-in GeoGraph Load Times (Unreduced & Reduced)."""
    networks = [
        ("oak_ridge_maritime", "Oak Ridge Maritime"),
        ("north_america_rail", "North America Rail"),
        ("marnet", "Global Maritime (marnet)"),
        ("us_freeway", "US Freeway Network"),
        ("world_highways_and_marnet", "World Highways & Maritime"),
    ]

    loaded_geos = {}
    t1_data = []
    t2_data = []

    print("\n[1/6] Benchmarking Built-in GeoGraph Loading (Unreduced)...")
    for net_key, net_label in networks:
        t0 = time.perf_counter()
        geo = GeoGraph.load_geograph(net_key, reduce_iterations=0)
        dt_load_ms = (time.perf_counter() - t0) * 1000

        num_nodes = len(geo.graph)
        num_edges = sum(len(edges) for edges in geo.graph)

        loaded_geos[net_key] = {"original": geo}
        t1_data.append(
            {
                "key": net_key,
                "label": net_label,
                "nodes": num_nodes,
                "edges": num_edges,
                "load_ms": dt_load_ms,
            }
        )
        print(
            f"  - {net_label:<30} {num_nodes:>7,} nodes | "
            f"{num_edges:>9,} edges | "
            f"Load: {dt_load_ms:7.2f} ms"
        )

    print(
        "\n[2/6] Benchmarking Built-in GeoGraph Loading & Reduction (Reduced)..."
    )
    for idx, (net_key, net_label) in enumerate(networks):
        num_nodes = t1_data[idx]["nodes"]
        num_edges = t1_data[idx]["edges"]

        t_red = time.perf_counter()
        geo_red = GeoGraph.load_geograph(net_key, reduce_iterations=1)
        dt_red_ms = (time.perf_counter() - t_red) * 1000

        loaded_geos[net_key]["reduced"] = geo_red

        g_red_obj = geo_red.graph_object
        is_red = g_red_obj.is_reduced
        rg = g_red_obj.reduced_graph

        eff_nodes = sum(1 for r in is_red if not r)
        eff_edges = sum(len(rg[i]) for i, r in enumerate(is_red) if not r)

        node_red_pct = (
            ((num_nodes - eff_nodes) / num_nodes) * 100
            if num_nodes > 0
            else 0.0
        )
        edge_red_pct = (
            ((num_edges - eff_edges) / num_edges) * 100
            if num_edges > 0
            else 0.0
        )

        t2_data.append(
            {
                "key": net_key,
                "label": net_label,
                "effective_nodes": eff_nodes,
                "effective_edges": eff_edges,
                "load_ms": dt_red_ms,
                "node_reduction_pct": node_red_pct,
                "edge_reduction_pct": edge_red_pct,
            }
        )
        print(
            f"  - {net_label:<30} {eff_nodes:>7,} eff nodes | "
            f"{eff_edges:>9,} eff edges | "
            f"Load: {dt_red_ms:7.2f} ms | "
            f"Node Red: {node_red_pct:5.1f}% | "
            f"Edge Red: {edge_red_pct:5.1f}%"
        )

    return loaded_geos, t1_data, t2_data


def bench_geograph_queries(loaded_geos):
    """Benchmark 3: Shortest Path Algorithm Performance on GeoGraphs."""
    print("\n[3/6] Benchmarking Shortest Path Query Algorithms on GeoGraphs...")
    query_configs = [
        (
            "marnet",
            "marnet",
            [
                (100, 7999),
                (4022, 8342),
                (512, 6340),
                (1205, 9543),
                (342, 8100),
            ],
        ),
        (
            "us_freeway",
            "us_freeway",
            [
                (1000, 9770),
                (250, 8500),
                (5100, 12300),
                (350, 14100),
                (1520, 7580),
            ],
        ),
        (
            "world_highways_and_marnet",
            "world_highways_and_marnet",
            [
                (1050, 52000),
                (21000, 153000),
                (76000, 305000),
                (121000, 452000),
                (51000, 254000),
            ],
        ),
    ]

    algorithms = [
        ("dijkstra", "Dijkstra", {}),
        ("bidirectional_dijkstra", "BiDijkstra", {}),
        ("a_star", "A*", "haversine"),
        ("dijkstra_buckets", "Buckets", {}),
    ]

    table_data = []

    for net_key, display_name, pairs in query_configs:
        for state_key, state_label in [
            ("original", "Original"),
            ("reduced", "Reduced"),
        ]:
            geo = loaded_geos[net_key][state_key]
            num_nodes = len(geo.graph)
            row = {
                "graph": display_name,
                "state": state_label,
                "nodes": num_nodes,
                "timings": {},
            }

            # Warmup
            warm_orig = {
                "latitude": geo.nodes[pairs[0][0]][0],
                "longitude": geo.nodes[pairs[0][0]][1],
            }
            warm_dest = {
                "latitude": geo.nodes[pairs[0][1]][0],
                "longitude": geo.nodes[pairs[0][1]][1],
            }
            try:
                geo.get_shortest_path(
                    warm_orig, warm_dest, algorithm_fn="dijkstra"
                )
            except Exception:
                pass

            for alg_key, alg_name, alg_opts in algorithms:
                kw = {"algorithm_fn": alg_key}
                if alg_opts == "haversine":
                    kw["algorithm_kwargs"] = {"heuristic_fn": geo.haversine}

                times = []
                for u, v in pairs:
                    orig = {
                        "latitude": geo.nodes[u][0],
                        "longitude": geo.nodes[u][1],
                    }
                    dest = {
                        "latitude": geo.nodes[v][0],
                        "longitude": geo.nodes[v][1],
                    }
                    t0 = time.perf_counter()
                    geo.get_shortest_path(orig, dest, **kw)
                    times.append((time.perf_counter() - t0) * 1000)

                avg_ms = sum(times) / len(times) if times else float("nan")
                row["timings"][alg_key] = avg_ms

            table_data.append(row)
            dijk = row["timings"]["dijkstra"]
            bidir = row["timings"]["bidirectional_dijkstra"]
            astar = row["timings"]["a_star"]
            buck = row["timings"]["dijkstra_buckets"]
            print(
                f"  - {display_name:<26} ({state_label:<8}) | "
                f"Dijkstra: {dijk:7.3f} ms | "
                f"BiDijkstra: {bidir:7.3f} ms | "
                f"A*: {astar:7.3f} ms | "
                f"Buckets: {buck:7.3f} ms"
            )

    return table_data


def bench_gridgraphs():
    """Benchmark 4: GridGraph Pathfinding & Obstacle Performance."""
    print("\n[4/6] Benchmarking GridGraph Generation & Pathfinding...")
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

    table_data = []

    for name, size, blocks, shape in configs:
        t0 = time.perf_counter()
        grid = GridGraph(
            x_size=size,
            y_size=size,
            blocks=blocks,
            shape=shape,
            add_exterior_walls=True,
        )
        dt_create_ms = (time.perf_counter() - t0) * 1000

        orig = {"x": 1, "y": 1}
        dest = {"x": size - 2, "y": size - 2}

        # Warmup
        grid.get_shortest_path(
            orig, dest, algorithm_fn="dijkstra", cache=False
        )

        t_dijk = time.perf_counter()
        grid.get_shortest_path(
            orig, dest, algorithm_fn="dijkstra", cache=False
        )
        dt_dijk_ms = (time.perf_counter() - t_dijk) * 1000

        t_astar = time.perf_counter()
        grid.get_shortest_path(
            orig,
            dest,
            algorithm_fn="a_star",
            heuristic_fn="manhattan",
            cache=False,
        )
        dt_astar_ms = (time.perf_counter() - t_astar) * 1000

        t_buck = time.perf_counter()
        grid.get_shortest_path(
            orig, dest, algorithm_fn="dijkstra_buckets", cache=False
        )
        dt_buck_ms = (time.perf_counter() - t_buck) * 1000

        row = {
            "config": name,
            "nodes": len(grid.graph),
            "creation_ms": dt_create_ms,
            "dijkstra_ms": dt_dijk_ms,
            "a_star_ms": dt_astar_ms,
            "buckets_ms": dt_buck_ms,
        }
        table_data.append(row)
        print(
            f"  - {name:<26} ({len(grid.graph):>6,} nodes) | "
            f"Create: {dt_create_ms:6.2f} ms | "
            f"Dijkstra: {dt_dijk_ms:6.3f} ms | "
            f"A* Manhattan: {dt_astar_ms:6.3f} ms | "
            f"Buckets: {dt_buck_ms:6.3f} ms"
        )

    return table_data


def bench_hierarchical_routing(loaded_geos):
    """Benchmark 5: Hierarchical Preprocessing & Routing (CH & TNR)."""
    print("\n[5/6] Benchmarking Hierarchical Routing (CH & TNR)...")
    targets = [
        (
            "marnet",
            "Original",
            loaded_geos["marnet"]["original"].graph,
            False,
            50,
        ),
        (
            "marnet",
            "Reduced",
            loaded_geos["marnet"]["original"].graph,
            True,
            50,
        ),
        (
            "us_freeway",
            "Original",
            loaded_geos["us_freeway"]["original"].graph,
            False,
            50,
        ),
        (
            "us_freeway",
            "Reduced",
            loaded_geos["us_freeway"]["original"].graph,
            True,
            50,
        ),
    ]

    table_data = []

    for (
        net_name,
        state_label,
        adj,
        should_reduce,
        transit_node_count,
    ) in targets:
        g = Graph(adj)
        if should_reduce:
            g.reduce()

        num_nodes = len(adj)
        random.seed(42)
        pairs = [
            (random.randint(0, num_nodes - 1), random.randint(0, num_nodes - 1))
            for _ in range(10)
        ]

        # 1. Baseline Dijkstra
        dijk_times = []
        for u, v in pairs:
            t0 = time.perf_counter()
            try:
                g.dijkstra(u, v)
                dijk_times.append((time.perf_counter() - t0) * 1000)
            except Exception:
                pass
        avg_dijk_ms = (
            sum(dijk_times) / len(dijk_times) if dijk_times else float("nan")
        )

        # 2. Contraction Hierarchies (CH)
        t_ch_prep = time.perf_counter()
        g.create_contraction_hierarchy()
        dt_ch_prep_ms = (time.perf_counter() - t_ch_prep) * 1000

        ch_times = []
        for u, v in pairs:
            t0 = time.perf_counter()
            try:
                g.contraction_hierarchy(u, v)
                ch_times.append((time.perf_counter() - t0) * 1000)
            except Exception:
                pass
        avg_ch_ms = sum(ch_times) / len(ch_times) if ch_times else float("nan")

        # 3. Transit Node Routing (TNR)
        t_tnr_prep = time.perf_counter()
        g.create_tnr_hierarchy(num_transit_nodes=transit_node_count)
        dt_tnr_prep_ms = (time.perf_counter() - t_tnr_prep) * 1000

        tnr_times = []
        for u, v in pairs:
            t0 = time.perf_counter()
            try:
                g.tnr(u, v)
                tnr_times.append((time.perf_counter() - t0) * 1000)
            except Exception:
                pass
        avg_tnr_ms = (
            sum(tnr_times) / len(tnr_times) if tnr_times else float("nan")
        )

        ch_speedup = (
            f"{avg_dijk_ms / avg_ch_ms:5.1f}x"
            if avg_ch_ms and avg_ch_ms > 0
            else "N/A"
        )
        tnr_speedup = (
            f"{avg_dijk_ms / avg_tnr_ms:5.1f}x"
            if avg_tnr_ms and avg_tnr_ms > 0
            else "N/A"
        )

        row = {
            "graph": net_name,
            "state": state_label,
            "nodes": num_nodes,
            "dijkstra_ms": avg_dijk_ms,
            "ch_prep_ms": dt_ch_prep_ms,
            "ch_query_ms": avg_ch_ms,
            "ch_speedup": ch_speedup,
            "tnr_prep_ms": dt_tnr_prep_ms,
            "tnr_query_ms": avg_tnr_ms,
            "tnr_speedup": tnr_speedup,
        }
        table_data.append(row)
        print(
            f"  - {net_name:<12} ({state_label:<8}) | "
            f"Dijkstra: {avg_dijk_ms:6.3f} ms | "
            f"CH Prep: {dt_ch_prep_ms:7.1f} ms -> Query: {avg_ch_ms:6.3f} ms ({ch_speedup}) | "
            f"TNR Prep: {dt_tnr_prep_ms:7.1f} ms -> Query: {avg_tnr_ms:6.3f} ms ({tnr_speedup})"
        )

    return table_data


def bench_specialized_features(loaded_geos):
    """Benchmark 6: Specialized Features (Distance Matrix, Trees, BMSSP, Visvalingam)."""
    print("\n[6/6] Benchmarking Specialized Features & Tree Operations...")
    table_data = []

    # 1. Distance Matrix (100 points = 10,000 pairs on us_freeway)
    uf_geo = loaded_geos["us_freeway"]["original"]
    box = {
        "min_latitude": 34.0,
        "max_latitude": 42.0,
        "min_longitude": -118.0,
        "max_longitude": -85.0,
    }
    n = 10
    lats = [
        box["min_latitude"]
        + i * (box["max_latitude"] - box["min_latitude"]) / n
        for i in range(n)
    ]
    lons = [
        box["min_longitude"]
        + i * (box["max_longitude"] - box["min_longitude"]) / n
        for i in range(n)
    ]
    dm_nodes = [{"latitude": lat, "longitude": lon} for lat in lats for lon in lons]

    t0 = time.perf_counter()
    uf_geo.distance_matrix(dm_nodes, off_graph_circuity=1, output_units="km")
    dt_dm_ms = (time.perf_counter() - t0) * 1000
    table_data.append(
        {
            "feature": "Distance Matrix (10x10 = 100 points)",
            "target": "us_freeway",
            "time_ms": dt_dm_ms,
            "notes": "10,000 OD pairs computed",
        }
    )

    # 2. Cached Shortest Path (Tree Build vs Hit)
    orig = {"latitude": 34.0522, "longitude": -118.2437}
    dest = {"latitude": 40.7128, "longitude": -74.0060}
    uf_geo.graph_object.reset_cache()

    t0 = time.perf_counter()
    uf_geo.get_shortest_path(orig, dest, algorithm_fn="cached_shortest_path")
    dt_tree_build_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    uf_geo.get_shortest_path(orig, dest, algorithm_fn="cached_shortest_path")
    dt_tree_hit_ms = (time.perf_counter() - t0) * 1000

    speedup_str = (
        f"{dt_tree_build_ms / dt_tree_hit_ms:,.0f}x faster tree lookup"
        if dt_tree_hit_ms > 0
        else "N/A"
    )
    table_data.append(
        {
            "feature": "Cached Shortest Path (Tree Build)",
            "target": "us_freeway",
            "time_ms": dt_tree_build_ms,
            "notes": "Full SPT construction",
        }
    )
    table_data.append(
        {
            "feature": "Cached Shortest Path (Tree Hit)",
            "target": "us_freeway",
            "time_ms": dt_tree_hit_ms,
            "notes": speedup_str,
        }
    )

    # 3. Visvalingam-Whyatt Simplification (10,000 coordinates)
    vis_data = [[i, i % 2 + (i / 10000)] for i in range(10000)]
    t0 = time.perf_counter()
    visvalingam(vis_data, pct_to_keep=0.1)
    dt_vis_ms = (time.perf_counter() - t0) * 1000
    table_data.append(
        {
            "feature": "Visvalingam Line Simplification",
            "target": "10,000 coordinates",
            "time_ms": dt_vis_ms,
            "notes": "90% point reduction",
        }
    )

    # 4. BMSSP Shortest Path
    mg_geo = loaded_geos["marnet"]["original"]
    t0 = time.perf_counter()
    mg_geo.graph_object.bmssp(0, 7999)
    dt_bmssp_ms = (time.perf_counter() - t0) * 1000
    table_data.append(
        {
            "feature": "BMSSP Shortest Path",
            "target": "marnet (node 0 -> 7999)",
            "time_ms": dt_bmssp_ms,
            "notes": "Bounded Multi-Source SP",
        }
    )

    for item in table_data:
        print(
            f"  - {item['feature']:<38} | "
            f"{item['target']:<24} | "
            f"{item['time_ms']:7.3f} ms | "
            f"{item['notes']}"
        )

    return table_data


def generate_markdown(
    t1_data, t2_data, t3_data, t4_data, t5_data, t6_data, total_sec
):
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
        f"- **Total Suite Execution Time**: {total_sec:.2f}s",
        "",
        "## 1. Built-in GeoGraph Load Times (Unreduced)",
        "",
        "| Network | Nodes | Edges | Load Time (ms) |",
        "|---|---|---|---|",
    ]
    for r in t1_data:
        lines.append(
            f"| `{r['key']}` | {r['nodes']:,} | {r['edges']:,} | {r['load_ms']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 2. Built-in GeoGraph Load Times & Reduction Specs (Reduced)",
            "",
            "| Reduced Network | Effective Nodes | Effective Edges | Load Time (ms) | Node Reduction % | Edge Reduction % |",
            "|---|---|---|---|---|---|",
        ]
    )
    for r in t2_data:
        lines.append(
            f"| `{r['key']}` | {r['effective_nodes']:,} | {r['effective_edges']:,} | {r['load_ms']:.2f} | **{r['node_reduction_pct']:.1f}%** | **{r['edge_reduction_pct']:.1f}%** |"
        )

    lines.extend(
        [
            "",
            "## 3. Shortest Path Query Performance on GeoGraphs",
            "",
            "| Graph | State | Nodes | Dijkstra (ms) | BiDijkstra (ms) | A* Haversine (ms) | Buckets (ms) |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for r in t3_data:
        dijk = r["timings"]["dijkstra"]
        bidir = r["timings"]["bidirectional_dijkstra"]
        astar = r["timings"]["a_star"]
        buck = r["timings"]["dijkstra_buckets"]
        lines.append(
            f"| `{r['graph']}` | {r['state']} | {r['nodes']:,} | {dijk:.4f} | {bidir:.4f} | {astar:.4f} | {buck:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 4. GridGraph Pathfinding & Obstacle Performance",
            "",
            "| Configuration | Nodes | Creation (ms) | Dijkstra (ms) | A* Manhattan (ms) | Buckets (ms) |",
            "|---|---|---|---|---|---|",
        ]
    )
    for r in t4_data:
        lines.append(
            f"| {r['config']} | {r['nodes']:,} | {r['creation_ms']:.2f} | {r['dijkstra_ms']:.4f} | {r['a_star_ms']:.4f} | {r['buckets_ms']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 5. Hierarchical Preprocessing & Routing (CH & TNR)",
            "",
            "| Graph | State | Baseline Dijkstra (ms) | CH Prep (ms) | CH Query (ms) | CH Speedup | TNR Prep (ms) | TNR Query (ms) | TNR Speedup |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for r in t5_data:
        lines.append(
            f"| `{r['graph']}` | {r['state']} | {r['dijkstra_ms']:.4f} | {r['ch_prep_ms']:.2f} | {r['ch_query_ms']:.4f} | **{r['ch_speedup']}** | {r['tnr_prep_ms']:.2f} | {r['tnr_query_ms']:.4f} | **{r['tnr_speedup']}** |"
        )

    lines.extend(
        [
            "",
            "## 6. Specialized Features & Operations",
            "",
            "| Feature / Operation | Target / Input | Execution Time (ms) | Notes / Throughput |",
            "|---|---|---|---|",
        ]
    )
    for r in t6_data:
        lines.append(
            f"| {r['feature']} | {r['target']} | {r['time_ms']:.3f} | {r['notes']} |"
        )

    lines.append("")
    return "\n".join(lines)


def run():
    print("=" * 80)
    print("scgraph Unified Benchmark Suite")
    print(
        f"Python: {platform.python_version()} | Platform: {platform.system()} {platform.machine()} | C++ Extension: {has_cpp()}"
    )
    print("=" * 80)

    t_suite_start = time.perf_counter()

    loaded_geos, t1_data, t2_data = bench_geograph_loading()
    t3_data = bench_geograph_queries(loaded_geos)
    t4_data = bench_gridgraphs()
    t5_data = bench_hierarchical_routing(loaded_geos)
    t6_data = bench_specialized_features(loaded_geos)

    total_suite_sec = time.perf_counter() - t_suite_start

    md_content = generate_markdown(
        t1_data, t2_data, t3_data, t4_data, t5_data, t6_data, total_suite_sec
    )
    with open(BENCHMARK_MD_PATH, "w") as f:
        f.write(md_content)

    print("\n" + "=" * 80)
    print(f"Benchmark finished successfully in {total_suite_sec:.2f} seconds!")
    print(f"Markdown output saved to: {BENCHMARK_MD_PATH}")
    print("=" * 80)


if __name__ == "__main__":
    run()
