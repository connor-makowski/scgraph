import pytest
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _build_iterative_reducible_graph():
    graph = [
        {1: 1.0, 6: 1.0},  # 0
        {0: 1.0, 2: 1.0},  # 1
        {1: 1.0, 3: 1.0},  # 2
        {2: 1.0, 4: 1.0, 7: 1.0, 8: 1.0},  # 3
        {3: 1.0, 5: 1.0},  # 4
        {4: 1.0, 10: 1.0, 11: 1.0},  # 5 (degree 3)
        {0: 1.0, 7: 1.0},  # 6
        {3: 1.0, 6: 1.0},  # 7
        {3: 1.0, 9: 1.0},  # 8
        {8: 1.0, 12: 1.0, 13: 1.0},  # 9 (degree 3)
        {5: 1.0},  # 10
        {5: 1.0},  # 11
        {9: 1.0},  # 12
        {9: 1.0},  # 13
    ]
    return graph


def test_reduce_iterations_python():
    g = PyGraph(_build_iterative_reducible_graph())

    # iterations = 0 -> no reduction
    g.reduce(0)
    assert g.reduced_graph is None

    # iterations = 1 -> pass 1 only
    g.reduce(1)
    assert g.reduced_graph is not None
    assert g.is_reduced[1] is True
    assert g.is_reduced[2] is True
    assert g.is_reduced[4] is True
    assert g.is_reduced[6] is True
    assert g.is_reduced[7] is True
    assert g.is_reduced[8] is True
    assert g.is_reduced[0] is True
    assert g.is_reduced[3] is False  # not reduced in pass 1
    assert g.is_reduced[5] is False  # degree 3
    assert g.is_reduced[9] is False  # degree 3

    # iterations = 2 -> pass 2 reduces node 3
    g.reduce(2)
    assert g.is_reduced[3] is True

    # iterations = -1 -> convergence (same as 2 here)
    g.reduce(-1)
    assert g.is_reduced[3] is True

    # Query works across multi-iteration reduction
    res = g.dijkstra(10, 12)
    assert res["path"] == [10, 5, 4, 3, 8, 9, 12]
    assert abs(res["length"] - 6.0) < 1e-6


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_reduce_iterations_parity():
    py_g = PyGraph(_build_iterative_reducible_graph())
    cpp_g = CppGraph(_build_iterative_reducible_graph())

    for iters in [0, 1, 2, -1]:
        py_g.reduce(iters)
        cpp_g.reduce(iters)

        assert py_g.is_reduced == cpp_g.is_reduced
        assert py_g.reduced_node_chain_ids == cpp_g.reduced_node_chain_ids
        assert py_g.reduced_graph == cpp_g.reduced_graph
        assert py_g.reduced_inverse_graph == cpp_g.reduced_inverse_graph

        if py_g.reduced_graph is not None:
            py_res = py_g.dijkstra(10, 12)
            cpp_res = cpp_g.dijkstra(10, 12)
            assert py_res == cpp_res
