import pytest
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _build_test_graphs(graph_cls):
    # Graph with 2 separate chains between junctions:
    # Junction J0 (0): connects to 1, 100, 101 (degree 3 -> unreduced)
    # Chain 1: 0 - 1 - 2 - 3 (1, 2 pass-through)
    # Junction J1 (3): connects to 2, 4, 6 (degree 3 -> unreduced)
    # Branch 1: 3 - 4 - 5
    # Branch 2: 3 - 6 - 7
    # Junction J2 (5): connects to 4, 102, 103 (degree 3 -> unreduced)
    # Junction J3 (7): connects to 6, 104, 105 (degree 3 -> unreduced)
    # Junction J4 (8): connects to 9, 106, 107 (degree 3 -> unreduced)
    # Chain 2: 8 - 9 - 10 - 11 (9, 10 pass-through)
    # Junction J5 (11): connects to 10, 108, 109 (degree 3 -> unreduced)
    data = {
        0: {1: 1.0, 100: 1.0, 101: 1.0},  # J0 (unreduced)
        1: {0: 1.0, 2: 1.0},  # 1 (reduced, chain 1)
        2: {1: 1.0, 3: 1.0},  # 2 (reduced, chain 1)
        3: {2: 1.0, 4: 1.0, 6: 1.0},  # J1 (unreduced)
        4: {3: 1.0, 5: 1.0},  # 4 (reduced, branch 1)
        5: {4: 1.0, 102: 1.0, 103: 1.0},  # J2 (unreduced)
        6: {3: 1.0, 7: 1.0},  # 6 (reduced, branch 2)
        7: {6: 1.0, 104: 1.0, 105: 1.0},  # J3 (unreduced)
        8: {9: 1.0, 106: 1.0, 107: 1.0},  # J4 (unreduced)
        9: {8: 1.0, 10: 1.0},  # 9 (reduced, chain 2)
        10: {9: 1.0, 11: 1.0},  # 10 (reduced, chain 2)
        11: {10: 1.0, 108: 1.0, 109: 1.0},  # J5 (unreduced)
        100: {0: 1.0, 110: 1.0, 111: 1.0},
        101: {0: 1.0, 112: 1.0, 113: 1.0},
        102: {5: 1.0, 114: 1.0, 115: 1.0},
        103: {5: 1.0, 116: 1.0, 117: 1.0},
        104: {7: 1.0, 118: 1.0, 119: 1.0},
        105: {7: 1.0, 120: 1.0, 121: 1.0},
        106: {8: 1.0, 122: 1.0, 123: 1.0},
        107: {8: 1.0, 124: 1.0, 125: 1.0},
        108: {11: 1.0, 126: 1.0, 127: 1.0},
        109: {11: 1.0, 128: 1.0, 129: 1.0},
    }
    for i in range(110, 130):
        data[i] = {i - 10: 1.0}

    # Convert to contiguous list
    max_node = max(data.keys())
    adj_list = [data.get(i, {}) for i in range(max_node + 1)]
    return graph_cls(adj_list)


def _run_chain_id_tests(graph_cls):
    g = _build_test_graphs(graph_cls)

    # Before reduce
    assert g.reduced_node_chain_ids is None
    assert g.is_same_chain(1, 2) is False

    g.reduce()

    assert g.reduced_node_chain_ids is not None
    chain_ids = g.reduced_node_chain_ids

    # Unreduced nodes should have None
    assert chain_ids[0] is None
    assert chain_ids[3] is None  # junction
    assert chain_ids[5] is None
    assert chain_ids[7] is None
    assert chain_ids[8] is None
    assert chain_ids[11] is None

    # Reduced nodes in Chain 1 (1 and 2) must share the same chain ID
    assert chain_ids[1] is not None
    assert chain_ids[2] is not None
    assert chain_ids[1] == chain_ids[2]

    # Reduced nodes in branches (4 and 6)
    assert chain_ids[4] is not None
    assert chain_ids[6] is not None
    # 4 and 6 are isolated branches separated by unreduced junction 3
    assert chain_ids[4] != chain_ids[1]
    assert chain_ids[6] != chain_ids[1]
    assert chain_ids[4] != chain_ids[6]

    # Reduced nodes in Chain 2 (9 and 10) must share the same chain ID
    assert chain_ids[9] is not None
    assert chain_ids[10] is not None
    assert chain_ids[9] == chain_ids[10]
    assert chain_ids[9] != chain_ids[1]

    # Test is_same_chain
    assert g.is_same_chain(1, 2) is True
    assert g.is_same_chain(2, 1) is True
    assert g.is_same_chain(9, 10) is True
    assert g.is_same_chain(1, 9) is False
    assert g.is_same_chain(1, 4) is False
    assert g.is_same_chain(4, 6) is False

    # Unreduced or invalid nodes
    assert g.is_same_chain(0, 3) is False
    assert g.is_same_chain(1, 3) is False
    assert g.is_same_chain(3, 1) is False
    assert g.is_same_chain(1, 999) is False
    assert g.is_same_chain(999, 1) is False

    # Multi-origin queries
    assert g.is_same_chain({1, 9}, 2) is True  # 1 and 2 share chain
    assert g.is_same_chain({0, 8}, 2) is False  # 0 and 8 unreduced
    assert g.is_same_chain({4, 6}, 2) is False  # different chains

    # Reset cache
    g.reset_cache()
    assert g.reduced_node_chain_ids is None
    assert g.is_same_chain(1, 2) is False


def test_python_chain_ids():
    _run_chain_id_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_chain_ids():
    _run_chain_id_tests(CppGraph)


def test_python_cpp_chain_id_parity_marnet(marnet):
    if not HAS_CPP:
        pytest.skip("C++ extension not available")

    py_g = PyGraph(marnet.graph)
    cpp_g = CppGraph(marnet.graph)

    py_g.reduce()
    cpp_g.reduce()

    py_chains = py_g.reduced_node_chain_ids
    cpp_chains = cpp_g.reduced_node_chain_ids

    assert len(py_chains) == len(cpp_chains)

    # Check is_reduced parity
    assert py_g.is_reduced == cpp_g.is_reduced

    # Check that connected components match exactly
    # Two nodes u and v have the same chain in Python iff they have the same chain in C++
    for u in range(0, len(py_chains), 20):
        for v in range(0, len(py_chains), 20):
            py_same = py_g.is_same_chain(u, v)
            cpp_same = cpp_g.is_same_chain(u, v)
            assert (
                py_same == cpp_same
            ), f"Mismatch for pair ({u}, {v}): py={py_same}, cpp={cpp_same}"
