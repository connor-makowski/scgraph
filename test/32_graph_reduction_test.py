import time
from scgraph import Graph, GeoGraph


def test_graph_reduction():
    # Simple chain graph
    # 0 (non-reduced) -> 1 (reduced) -> 2 (reduced) -> 3 (non-reduced)
    g_data = [
        {1: 5},  # 0: non-reduced
        {2: 10},  # 1: reduced (1 outflow)
        {3: 3},  # 2: reduced (1 outflow)
        {},  # 3: non-reduced
    ]
    g = Graph(g_data)
    g.reduce()
    assert g.is_reduced == [False, True, True, False]
    assert g.reduced_graph[0] == {3: 18.0}
    assert g.reduced_graph_connections[0] == {3: [1, 2]}

    # Verify routing outputs match
    p_orig = 18.0
    for algo in ["dijkstra", "dijkstra_buckets", "a_star", "bellman_ford"]:
        fn = getattr(g, algo)
        res = fn(0, 3)
        assert abs(res["length"] - p_orig) < 1e-5
        assert res["path"] == [0, 1, 2, 3]


def test_graph_reduction_endpoints():
    g_data = [
        {1: 5},
        {2: 10},
        {3: 3},
        {},
    ]
    g = Graph(g_data)
    g.reduce()

    # 1 is reduced origin node
    res1 = g.dijkstra(1, 3)
    assert res1["length"] == 13.0
    assert res1["path"] == [1, 2, 3]

    # 2 is reduced destination node
    res2 = g.dijkstra(0, 2)
    assert res2["length"] == 15.0
    assert res2["path"] == [0, 1, 2]


def test_split_rejoin_path():
    # Graph split at 1 and rejoin at 4
    g_data = [
        {1: 1},
        {2: 1, 3: 2},
        {4: 1},
        {4: 2},
        {5: 1},
        {},
    ]
    g = Graph(g_data)
    g.reduce()

    # If origin is 0 and destination is 5, it should use the shorter path via 2
    res_0_5 = g.dijkstra(0, 5)
    assert res_0_5["length"] == 4.0
    assert res_0_5["path"] == [0, 1, 2, 4, 5]

    # If origin is 0 and destination is 3, it should go 0, 1, 3
    res_0_3 = g.dijkstra(0, 3)
    assert res_0_3["length"] == 3.0
    assert res_0_3["path"] == [0, 1, 3]


def test_reduction_cache_clearing():
    g_data = [
        {1: 5},
        {2: 10},
        {3: 3},
        {},
    ]
    g = Graph(g_data)
    g.reduce()
    assert getattr(g, "reduced_graph", None) is not None
    g.add_edge(0, 3, 50)
    assert getattr(g, "reduced_graph", None) is None


def test_performance_timing():
    # Load world_highways geograph
    geograph = GeoGraph.load_geograph("us_freeway")
    g_large = geograph.graph_object

    # Pick 5 different origins
    origins = [0, 1000, 5000, 10000, 11000]
    pairs = []

    for idx, org in enumerate(origins):
        tree = g_large.get_shortest_path_tree(org)
        dists = tree["distance_matrix"]
        valid = [i for i, d in enumerate(dists) if 0 < d < float("inf")]
        assert len(valid) > 0, f"No connected nodes found from origin {org}!"
        # Use different fractions to ensure unique destinations
        fraction = [4, 3, 2, 5, 8][idx]
        dest = valid[len(valid) * (fraction - 1) // fraction]
        pairs.append((org, dest))

    # Time Dijkstra on original graph
    orig_times = []
    orig_results = []
    for org, dest in pairs:
        t0 = time.perf_counter()
        p = g_large.dijkstra(org, dest)
        orig_times.append(time.perf_counter() - t0)
        orig_results.append(p)

    # Time preprocessing (reduction) once
    t1 = time.perf_counter()
    g_large.reduce()
    t_reduce = time.perf_counter() - t1

    # Time Dijkstra on reduced graph
    red_times = []
    red_results = []
    for org, dest in pairs:
        t2 = time.perf_counter()
        p = g_large.dijkstra(org, dest)
        red_times.append(time.perf_counter() - t2)
        red_results.append(p)

    # Assert correctness and print times
    print(f"\n[Reduction Timing Results on 5 OD Pairs (us_freeway)]")
    print(f"Reduction Preprocessing time: {t_reduce:.4f}s")
    for i, (org, dest) in enumerate(pairs):
        p_orig = orig_results[i]
        p_red = red_results[i]
        assert abs(p_orig["length"] - p_red["length"]) < 1e-5
        assert p_orig["path"] == p_red["path"]
        print(
            f"  Pair {i+1} ({org} -> {dest}): Original={orig_times[i]:.4f}s | Reduced={red_times[i]:.4f}s"
        )


if __name__ == "__main__":
    test_graph_reduction()
    test_graph_reduction_endpoints()
    test_split_rejoin_path()
    test_reduction_cache_clearing()
    test_performance_timing()
