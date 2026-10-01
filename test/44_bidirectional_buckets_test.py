import random
import pytest
from scgraph.graph import Graph as PyGraph
from helpers import assert_result

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

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


def _run_basic_bidirectional_buckets_tests(graph_cls):
    g = graph_cls(_GRAPH_DATA)

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

    # All-pairs equivalence with standard Dijkstra
    for u in range(len(_GRAPH_DATA)):
        for v in range(len(_GRAPH_DATA)):
            d_res = g.dijkstra(u, v)
            bi_res = g.bidirectional_buckets(u, v)
            assert abs(d_res["length"] - bi_res["length"]) < 1e-6
            assert (
                abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-6
            )


def _run_disconnected_tests(graph_cls):
    g = graph_cls(_DISCONNECTED_DATA)
    with pytest.raises(Exception):
        g.bidirectional_buckets(origin_id=0, destination_id=7)


def _run_directed_asymmetric_tests(graph_cls):
    data = [
        {1: 1.0, 2: 10.0},
        {2: 2.0},
        {3: 3.0},
        {0: 100.0},
    ]
    g = graph_cls(data)

    res = g.bidirectional_buckets(0, 3)
    assert res["length"] == 6.0
    assert res["path"] == [0, 1, 2, 3]

    res_back = g.bidirectional_buckets(3, 1)
    assert res_back["length"] == 101.0
    assert res_back["path"] == [3, 0, 1]


def _run_reduced_graph_tests(graph_cls):
    # Chain graph: 0 -> 1 -> 2 -> 3 -> 4 -> 5
    data = [
        {1: 2.0},
        {2: 3.0},
        {3: 1.5},
        {4: 4.0},
        {5: 2.5},
        {},
    ]
    g = graph_cls(data)
    g.reduce()

    # Same-chain query
    res_same_chain = g.bidirectional_buckets(1, 3)
    assert abs(res_same_chain["length"] - 4.5) < 1e-6
    assert res_same_chain["path"] == [1, 2, 3]

    # End-to-end query
    res_full = g.bidirectional_buckets(0, 5)
    assert abs(res_full["length"] - 13.0) < 1e-6
    assert res_full["path"] == [0, 1, 2, 3, 4, 5]


def test_python_basic_bidirectional_buckets():
    _run_basic_bidirectional_buckets_tests(PyGraph)


def test_python_disconnected_bidirectional_buckets():
    _run_disconnected_tests(PyGraph)


def test_python_directed_asymmetric_bidirectional_buckets():
    _run_directed_asymmetric_tests(PyGraph)


def test_python_reduced_bidirectional_buckets():
    _run_reduced_graph_tests(PyGraph)


def test_python_buckets_grid_int():
    data = _make_int_grid(50)
    g = PyGraph(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.bidirectional_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


def test_python_buckets_grid_float():
    data = _make_float_grid(50)
    g = PyGraph(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.bidirectional_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_basic_bidirectional_buckets():
    _run_basic_bidirectional_buckets_tests(CppGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_disconnected_bidirectional_buckets():
    _run_disconnected_tests(CppGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_directed_asymmetric_bidirectional_buckets():
    _run_directed_asymmetric_tests(CppGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_reduced_bidirectional_buckets():
    _run_reduced_graph_tests(CppGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_buckets_grid_int():
    data = _make_int_grid(50)
    g = CppGraph(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.bidirectional_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_buckets_grid_float():
    data = _make_float_grid(50)
    g = CppGraph(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.bidirectional_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)
