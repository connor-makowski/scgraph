import time
import pytest
from scgraph import GeoGraph


def run_network_test(geograph_name):
    print(f"\n=======================================================")
    print(f"Loading {geograph_name} geograph...")
    geograph = GeoGraph.load_geograph(geograph_name)
    g_large = geograph.graph_object
    print(f"Loaded! Graph has {len(g_large.graph)} nodes.")

    # Pick 5 OD pairs
    origins = [0, 1000, 5000, 10000, 11000]
    origins = [o for o in origins if o < len(g_large.graph)]
    pairs = []
    for org in origins:
        tree = g_large.get_shortest_path_tree(org)
        dists = tree["distance_matrix"]
        valid = [i for i, d in enumerate(dists) if 0 < d < float("inf")]
        assert len(valid) > 0
        dest = valid[len(valid) // 2]
        pairs.append((org, dest))

    algorithms = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "dijkstra_negative",
        "a_star",
        "cached_shortest_path",
    ]

    timings = {}

    # 1. Run all algorithms on the ORIGINAL graph
    g_large.reset_cache()
    orig_results = {}
    for algo in algorithms:
        orig_paths = []
        t_orig = 0.0
        for org, dest in pairs:
            t0 = time.perf_counter()
            p = getattr(g_large, algo)(org, dest)
            t_orig += time.perf_counter() - t0
            orig_paths.append(p)
        orig_results[algo] = orig_paths
        timings[algo] = {"original": t_orig, "reduced": 0.0}

    # 2. Reduce the graph ONCE for standard algorithms
    g_large.reduce()

    # 3. Run all algorithms on the REDUCED graph
    red_results = {}
    for algo in algorithms:
        red_paths = []
        t_red = 0.0
        for org, dest in pairs:
            t0 = time.perf_counter()
            p = getattr(g_large, algo)(org, dest)
            t_red += time.perf_counter() - t0
            red_paths.append(p)
        red_results[algo] = red_paths
        timings[algo]["reduced"] = t_red

    # 4. Restore the original graph to evaluate path weights
    g_large.reset_cache()

    # 5. Assert consistency of standard algorithms
    for algo in algorithms:
        for i in range(len(pairs)):
            orig_p = orig_results[algo][i]
            red_p = red_results[algo][i]
            assert abs(orig_p["length"] - red_p["length"]) < 1e-5
            assert (
                abs(g_large.get_path_weight(red_p["path"]) - orig_p["length"])
                < 1e-5
            )

    # CH & TNR need separate preprocessing/warmup to measure query phase only
    # Distance Matrix timing
    timings["distance_matrix"] = {"original": 0.0, "reduced": 0.0}
    dm_nodes = [
        {"latitude": geograph.nodes[i][0], "longitude": geograph.nodes[i][1]}
        for i in range(
            0, min(1000, len(g_large.graph)), max(1, len(g_large.graph) // 500)
        )
    ][:10]

    geograph.graph_object.reset_cache()
    t0 = time.perf_counter()
    dm_orig = geograph.distance_matrix(dm_nodes)
    timings["distance_matrix"]["original"] = time.perf_counter() - t0

    geograph.graph_object.reduce()
    t0 = time.perf_counter()
    dm_red = geograph.distance_matrix(dm_nodes)
    timings["distance_matrix"]["reduced"] = time.perf_counter() - t0

    # Assert matrix equivalence
    for r in range(len(dm_nodes)):
        for c in range(len(dm_nodes)):
            assert abs(dm_orig[r][c] - dm_red[r][c]) < 1e-5

    # Print results
    print(
        f"\nGraph Reduction Consistency & Timing Benchmarks ({geograph_name})"
    )
    print(f"-------------------------------------------------------")
    for algo, data in timings.items():
        orig_ms = data["original"] * 1000
        red_ms = data["reduced"] * 1000
        speedup = orig_ms / red_ms if red_ms > 0 else 0.0
        print(
            f"{algo:<25} Solve Orig: {orig_ms:>7.2f} ms | Solve Red: {red_ms:>7.2f} ms | Solve Speedup: {speedup:>5.2f}x"
        )
        if "build_original" in data:
            build_orig_ms = data["build_original"] * 1000
            build_red_ms = data["build_reduced"] * 1000
            build_speedup = (
                build_orig_ms / build_red_ms if build_red_ms > 0 else 0.0
            )
            print(
                f"  └─ {algo + ' (build)':<20} Build Orig: {build_orig_ms:>7.2f} ms | Build Red: {build_red_ms:>7.2f} ms | Build Speedup: {build_speedup:>5.2f}x"
            )
    print(f"=======================================================")


def test_reduction_consistency():
    run_network_test("us_freeway")
    run_network_test("world_highways")


if __name__ == "__main__":
    test_reduction_consistency()
