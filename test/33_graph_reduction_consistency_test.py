import functools
import itertools
import random
import threading
import time
from copy import deepcopy
import pytest
from scgraph import GeoGraph
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    GRAPH_CLASSES = [PyGraph, CppGraph]
except ImportError:
    GRAPH_CLASSES = [PyGraph]


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
    run_network_test("marnet")


# Each graph catches reduction faults the others miss: two-way with unit
# weights and chains reduced over several passes; weighted with ties; one-way.
REDUCIBLE_GRAPHS = [
    [
        {1: 1, 6: 1},
        {0: 1, 2: 1},
        {1: 1, 3: 1},
        {2: 1, 4: 1, 7: 1, 8: 1},
        {3: 1, 5: 1},
        {4: 1, 10: 1, 11: 1},
        {0: 1, 7: 1},
        {3: 1, 6: 1},
        {3: 1, 9: 1},
        {8: 1, 12: 1, 13: 1},
        {5: 1},
        {5: 1},
        {9: 1},
        {9: 1},
    ],
    [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ],
    [
        {3: 5},
        {3: 5, 2: 3},
        {5: 2, 4: 3},
        {4: 1, 0: 5},
        {3: 1, 2: 3},
        {4: 4, 2: 2},
        {0: 3, 5: 5},
    ],
]


def _small_digraphs(max_nodes):
    # Every directed graph with up to max_nodes nodes, up to relabelling, with
    # unit weights
    graphs = []
    for n in range(1, max_nodes + 1):
        arcs = list(itertools.permutations(range(n), 2))
        relabellings = list(itertools.permutations(range(n)))
        seen = set()
        for mask in range(1 << len(arcs)):
            chosen = [arc for i, arc in enumerate(arcs) if mask >> i & 1]
            key = min(
                tuple(sorted((p[a], p[b]) for a, b in chosen))
                for p in relabellings
            )
            if key not in seen:
                seen.add(key)
                graph = [dict() for _ in range(n)]
                for a, b in chosen:
                    graph[a][b] = 1
                graphs.append(graph)
    return graphs


def _family_graphs(rng):
    # One small random graph per kind of structure
    def build(n, edges, one_way=0.0, weight=lambda: rng.randint(1, 5)):
        graph = [dict() for _ in range(n)]
        for a, b in edges:
            graph[a][b] = weight()
            if rng.random() >= one_way:
                graph[b][a] = graph[a][b]
        return graph

    def tree(n, extra):
        order = rng.sample(range(n), n)
        edges = [(order[i], order[rng.randrange(i)]) for i in range(1, n)]
        return edges + [tuple(rng.sample(range(n), 2)) for _ in range(extra)]

    def ring(n, start=0):
        return [(start + i, start + (i + 1) % n) for i in range(n)]

    with_loops = build(8, tree(8, 2), 0.3)
    for u in rng.sample(range(8), 3):
        with_loops[u][u] = rng.choice([0, 1])
    n = rng.randint(15, 25)
    return [
        build(7, ring(7)),
        build(7, ring(7), one_way=1.0),
        build(8, ring(4) + ring(4, 4) + [(0, 4)], one_way=0.5),
        build(9, ring(3) + ring(3, 3) + ring(3, 6) + [(0, 3), (3, 6)], 0.5),
        build(12, [(i, i + 1) for i in range(11)], one_way=0.5),
        # Two components and an isolated node (5)
        build(10, tree(5, 1) + [(a + 6, b + 6) for a, b in tree(4, 0)], 0.3),
        with_loops,
        build(9, tree(9, 3), 0.3, weight=lambda: rng.choice([0, 1, 2])),
        build(9, tree(9, 3), 0.3, weight=lambda: rng.uniform(0.1, 10)),
        build(10, tree(10, 0), one_way=0.6),
        build(7, itertools.combinations(range(7), 2), one_way=0.3),
        build(7, [(0, i) for i in range(1, 7)], one_way=0.5),
        build(n, tree(n, n // 3), one_way=0.3),
    ]


def _fail_instead_of_looping(seconds):
    # A fault that makes a search loop fails the test instead of hanging it.
    # The looping thread keeps running until the test session ends (later tests
    # run slower, in that failure case only). A loop inside the C++ extension
    # is not stopped.
    def decorator(test):
        @functools.wraps(test)
        def wrapper(*args, **kwargs):
            outcome = []

            def run():
                try:
                    test(*args, **kwargs)
                    outcome.append(None)
                except BaseException as error:
                    outcome.append(error)

            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            thread.join(seconds)
            if thread.is_alive():
                pytest.fail(f"no result after {seconds} s: a search loops")
            if outcome[0] is not None:
                raise outcome[0]

        return wrapper

    return decorator


def _assert_stored_paths_are_valid(graph, g):
    # Every distance reduce() stores (reduced_graph[x][B], from a node x to a
    # non-reduced node B; reduced_inverse_graph[x][A], from a non-reduced node
    # A to x) is the length of an original path whose inner nodes, the hidden
    # nodes stored with it, are all reduced. Searches cannot see an edge that
    # crosses a non-reduced node: its length is right, but the reduced graph
    # grows.
    reduced = g.is_reduced

    def assert_path(path, length, boundary):
        assert not reduced[boundary] and path[0] != path[-1], path
        assert all(reduced[v] for v in path[1:-1]), path
        assert all(v in graph[u] for u, v in zip(path, path[1:])), path
        weight = sum(graph[u][v] for u, v in zip(path, path[1:]))
        assert weight == pytest.approx(length), path

    hidden = g.reduced_graph_connections
    for x, row in enumerate(g.reduced_graph):
        for B, length in row.items():
            assert_path([x, *(hidden[x] or {}).get(B, []), B], length, B)
    hidden = g.reduced_inverse_graph_connections
    for x, row in enumerate(g.reduced_inverse_graph):
        for A, length in row.items():
            assert_path([A, *(hidden[x] or {}).get(A, []), x], length, A)


# Raise locally for a longer run: each round adds one graph per structure.
_RANDOM_ROUNDS = 1

# Tests cannot prove that reduction is exact: the proof does not depend on the
# graph (every reduced edge is a shortest path through reduced nodes, every
# original path splits at non-reduced nodes into such segments) and assumes
# non-negative weights. The graphs below check that both implementations follow
# it: the fixed graphs above, every directed graph up to 4 nodes, and random
# graphs of the structures a network can contain (rings, one-way edges,
# separate components, self-loops, zero and real weights, dead ends, dense
# parts, long chains). A fault that affects a fraction p of such graphs is
# missed after N graphs with probability (1 - p) ** N.
CHECKED_GRAPHS = (
    REDUCIBLE_GRAPHS
    + _small_digraphs(4)
    + [
        graph
        for seed in range(_RANDOM_ROUNDS)
        for graph in _family_graphs(random.Random(seed))
    ]
)


@pytest.mark.parametrize(
    "algorithm",
    [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "a_star",
        "bellman_ford",
        "bmssp",
        "cached_shortest_path",
        pytest.param(
            "contraction_hierarchy",
            marks=pytest.mark.xfail(
                reason="stale shortcut lists in CH preprocessing",
                strict=False,
            ),
        ),
        pytest.param(
            "tnr",
            marks=pytest.mark.xfail(
                reason="TNR is built on CH: stale shortcut lists",
                strict=False,
            ),
        ),
    ],
)
@pytest.mark.parametrize("iterations", [1, -1])
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
# The slowest case takes about 0.7 s: 20 s leaves a margin for slow runners.
@_fail_instead_of_looping(seconds=20)
def test_reduced_graph_matches_unreduced_graph(
    GraphClass, iterations, algorithm
):
    # Every search on a reduced graph finds, for every pair, a path of the
    # original graph with the shortest length of the unreduced graph, for plain
    # node ids, start/exit distances (as GeoGraph passes them) and several
    # destinations
    for graph in CHECKED_GRAPHS:
        reference = GraphClass(deepcopy(graph))
        g = GraphClass(deepcopy(graph))
        g.reduce(iterations)
        if algorithm == "dijkstra":
            # What reduce() stores does not depend on the search: checked once
            _assert_stored_paths_are_valid(graph, g)
        n = len(graph)
        leaving_chain = set()
        for o in range(n):
            for d in range(n):
                for origin, destination in (
                    (o, d),
                    ({o: 0.5}, {d: 0.25}),
                    (o, {d, (d + 1) % n}),
                ):
                    case = (graph, origin, destination)
                    try:
                        expected = reference.dijkstra(origin, destination)
                    except Exception:
                        continue  # not connected in the original graph
                    if algorithm == "bmssp" and (
                        n < 2 or (GraphClass is PyGraph and destination == 0)
                    ):
                        # Limits of bmsspy, not of reduction: it needs 2 nodes
                        # or more, and its pure-Python solver returns no path
                        # to node 0. Remove once bmsspy handles both.
                        continue
                    result = getattr(g, algorithm)(origin, destination)
                    if isinstance(destination, int) and not g.is_same_chain(
                        origin, destination
                    ):
                        leaving_chain.add(origin)
                    path = result["path"]
                    origins = origin if isinstance(origin, dict) else {origin}
                    targets = (
                        destination
                        if isinstance(destination, (dict, set))
                        else {destination}
                    )
                    assert path[0] in origins and path[-1] in targets, case
                    offsets = (
                        origin.get(path[0], 0)
                        if isinstance(origin, dict)
                        else 0
                    ) + (
                        destination.get(path[-1], 0)
                        if isinstance(destination, dict)
                        else 0
                    )
                    weight = sum(graph[u][v] for u, v in zip(path, path[1:]))
                    assert result["length"] == pytest.approx(
                        expected["length"]
                    ), case
                    assert weight + offsets == pytest.approx(
                        expected["length"]
                    ), case
        if algorithm == "cached_shortest_path":
            # Each origin queried beyond its own chain keeps its tree cached,
            # reduced origins included (distance matrices reuse it)
            cache = g.get_cache()
            assert all(cache[o] != 0 for o in leaving_chain), graph


if __name__ == "__main__":
    test_reduction_consistency()
