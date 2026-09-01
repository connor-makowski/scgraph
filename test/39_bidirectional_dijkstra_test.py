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


def _run_basic_bidirectional_tests(graph_cls):
    g = graph_cls(_GRAPH_DATA)

    # Basic test
    res = g.bidirectional_dijkstra(origin_id=0, destination_id=5)
    assert_result(res, _EXPECTED)

    # Origin == Destination
    res_same = g.bidirectional_dijkstra(origin_id=3, destination_id=3)
    assert res_same["length"] == 0
    assert res_same["path"] == [3]

    # Multi-origin
    res_multi = g.bidirectional_dijkstra(origin_id={0, 4}, destination_id=5)
    assert res_multi["length"] == 9  # 4 -> 3 (3) + 3 -> 5 (6) = 9
    assert res_multi["path"] == [4, 3, 5]

    # All-pairs equivalence with standard Dijkstra
    for u in range(len(_GRAPH_DATA)):
        for v in range(len(_GRAPH_DATA)):
            d_res = g.dijkstra(u, v)
            bi_res = g.bidirectional_dijkstra(u, v)
            assert abs(d_res["length"] - bi_res["length"]) < 1e-6
            # Path weight verification
            assert (
                abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-6
            )


def _run_disconnected_tests(graph_cls):
    g = graph_cls(_DISCONNECTED_DATA)
    with pytest.raises(Exception):
        g.bidirectional_dijkstra(origin_id=0, destination_id=7)


def _run_directed_asymmetric_tests(graph_cls):
    # Directed graph with asymmetric weights
    # 0 -> 1 (1) -> 2 (2) -> 3 (3)
    # 0 -> 2 (10)
    # 3 -> 0 (100)
    data = [
        {1: 1.0, 2: 10.0},
        {2: 2.0},
        {3: 3.0},
        {0: 100.0},
    ]
    g = graph_cls(data)

    res = g.bidirectional_dijkstra(0, 3)
    assert res["length"] == 6.0
    assert res["path"] == [0, 1, 2, 3]

    res_back = g.bidirectional_dijkstra(3, 1)
    assert res_back["length"] == 101.0
    assert res_back["path"] == [3, 0, 1]


def test_python_basic_bidirectional():
    _run_basic_bidirectional_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_basic_bidirectional():
    _run_basic_bidirectional_tests(CppGraph)


def test_python_disconnected():
    _run_disconnected_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_disconnected():
    _run_disconnected_tests(CppGraph)


def test_python_directed_asymmetric():
    _run_directed_asymmetric_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_directed_asymmetric():
    _run_directed_asymmetric_tests(CppGraph)


def test_bidirectional_dijkstra_on_marnet(marnet):
    g = marnet.graph_object
    test_pairs = [(0, 100), (50, 200), (300, 400), (10, 500)]
    for u, v in test_pairs:
        d_res = g.dijkstra(u, v)
        bi_res = g.bidirectional_dijkstra(u, v)
        assert abs(d_res["length"] - bi_res["length"]) < 1e-5
        assert abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-5


def test_bidirectional_dijkstra_on_us_freeway(us_freeway):
    g = us_freeway.graph_object
    test_pairs = [(0, 500), (1000, 2000), (3000, 4000)]
    for u, v in test_pairs:
        d_res = g.dijkstra(u, v)
        bi_res = g.bidirectional_dijkstra(u, v)
        assert abs(d_res["length"] - bi_res["length"]) < 1e-5
        assert abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-5
