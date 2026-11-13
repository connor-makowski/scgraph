import random
import pytest
from scgraph import PathNotFoundError
from helpers import assert_result

_GRAPH_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]

_DISCONNECTED_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
    {7: 1},
    {8: 1},
    {6: 1},
]

_EXPECTED = {"path": [0, 2, 1, 3, 5], "length": 10}


def _make_int_grid(size, seed=42):
    rng = random.Random(seed)
    data = []
    for y in range(size):
        for x in range(size):
            node_id = x + y * size
            edges = {}
            if x + 1 < size:
                edges[node_id + 1] = rng.randint(1, 10)
            if y + 1 < size:
                edges[node_id + size] = rng.randint(1, 10)
            data.append(edges)
    return data


def _make_float_grid(size, seed=42):
    rng = random.Random(seed)
    data = []
    for y in range(size):
        for x in range(size):
            node_id = x + y * size
            edges = {}
            if x + 1 < size:
                edges[node_id + 1] = rng.uniform(0.1, 10.0)
            if y + 1 < size:
                edges[node_id + size] = rng.uniform(0.1, 10.0)
            data.append(edges)
    return data


def test_basic_bidirectional_buckets(graph_class):
    g = graph_class(_GRAPH_DATA)

    # Basic test
    res = g.bidirectional_buckets(origin_id=0, destination_id=5)
    assert_result(res, _EXPECTED)

    # Origin == Destination
    res_same = g.bidirectional_buckets(origin_id=3, destination_id=3)
    assert res_same["length"] == 0
    assert res_same["path"] == [3]

    # Multi-origin
    res_multi = g.bidirectional_buckets(origin_id={0, 4}, destination_id=5)
    assert res_multi["length"] == 9  # 4 -> 3 (3) + 3 -> 5 (6) = 9
    assert res_multi["path"] == [4, 3, 5]

    # Explicit max_edge_weight
    res_max_w = g.bidirectional_buckets(
        origin_id=0, destination_id=5, max_edge_weight=10
    )
    assert_result(res_max_w, _EXPECTED)

    # All-pairs equivalence with standard Dijkstra, whatever the bucket width:
    # default, under one unit, several units, wider than the longest edge
    for u in range(len(_GRAPH_DATA)):
        for v in range(len(_GRAPH_DATA)):
            d_res = g.dijkstra(u, v)
            for width in (None, 0.5, 3, 100):
                for algorithm in (g.bidirectional_buckets, g.dijkstra_buckets):
                    res = algorithm(u, v, bucket_width=width)
                    assert abs(d_res["length"] - res["length"]) < 1e-6
                    assert (
                        abs(g.get_path_weight(res["path"]) - d_res["length"])
                        < 1e-6
                    )
                    # Start and end offsets are distances, whatever the width
                    res = algorithm({u: 7.5}, {v: 100.0}, bucket_width=width)
                    assert abs(res["length"] - d_res["length"] - 107.5) < 1e-6

    # All weights zero (median and maximum 0): the default width still works
    z = graph_class([{1: 0, 2: 0}, {2: 0}, {0: 0}])
    for u in range(3):
        for v in range(3):
            for algorithm in (z.bidirectional_buckets, z.dijkstra_buckets):
                assert algorithm(u, v)["length"] == 0

    for algorithm in (g.bidirectional_buckets, g.dijkstra_buckets):
        for width in (0, float("inf")):
            with pytest.raises(ValueError):
                algorithm(0, 5, bucket_width=width)


def test_disconnected_bidirectional_buckets(graph_class):
    g = graph_class(_DISCONNECTED_DATA)
    with pytest.raises(PathNotFoundError):
        g.bidirectional_buckets(origin_id=0, destination_id=7)


def test_directed_asymmetric_bidirectional_buckets(graph_class):
    data = [
        {1: 1.0, 2: 10.0},
        {2: 2.0},
        {3: 3.0},
        {0: 100.0},
    ]
    g = graph_class(data)

    res = g.bidirectional_buckets(0, 3)
    assert res["length"] == 6.0
    assert res["path"] == [0, 1, 2, 3]

    res_back = g.bidirectional_buckets(3, 1)
    assert res_back["length"] == 101.0
    assert res_back["path"] == [3, 0, 1]


def test_reduced_bidirectional_buckets(graph_class):
    # Chain graph: 0 -> 1 -> 2 -> 3 -> 4 -> 5
    data = [
        {1: 2.0},
        {2: 3.0},
        {3: 1.5},
        {4: 4.0},
        {5: 2.5},
        {},
    ]
    g = graph_class(data)
    g.reduce()

    # Same-chain query
    res_same_chain = g.bidirectional_buckets(1, 3)
    assert abs(res_same_chain["length"] - 4.5) < 1e-6
    assert res_same_chain["path"] == [1, 2, 3]

    # End-to-end query
    res_full = g.bidirectional_buckets(0, 5)
    assert abs(res_full["length"] - 13.0) < 1e-6
    assert res_full["path"] == [0, 1, 2, 3, 4, 5]


def test_buckets_grid_int(graph_class):
    data = _make_int_grid(50)
    g = graph_class(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.bidirectional_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


def test_buckets_grid_float(graph_class):
    data = _make_float_grid(50)
    g = graph_class(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.bidirectional_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


def test_geograph_default_algorithm_bibuckets(marnet):
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    # Default call should use bidirectional_buckets
    res_default = marnet.get_shortest_path(origin, dest)

    res_explicit = marnet.get_shortest_path(
        origin, dest, algorithm_fn="bidirectional_buckets"
    )

    assert_result(res_default, res_explicit)
