import pytest
from scgraph.graph import Graph as PyGraph
from scgraph.transit_node_routing import TNRGraph as PyTNRGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _build_test_graph():
    # Graph with 9 nodes:
    # Chain 1: 0 <-> 1 <-> 2 <-> 3 (1, 2 are degree-2 pass-through)
    # Chain 2: 3 <-> 4 <-> 5 <-> 6 (4, 5 are degree-2 pass-through)
    # Chain 3: 6 <-> 7 <-> 8 <-> 0 (7, 8 are degree-2 pass-through)
    # 0, 3, 6 are degree-4 junctions (non-reduced)
    # Cross branch from 3 <-> 0 directly with weight 20.0
    return [
        {1: 2.0, 8: 3.0, 3: 20.0},  # 0 (non-reduced junction)
        {0: 2.0, 2: 3.0},  # 1 (reduced)
        {1: 3.0, 3: 4.0},  # 2 (reduced)
        {2: 4.0, 4: 1.0, 0: 20.0},  # 3 (non-reduced junction)
        {3: 1.0, 5: 2.0},  # 4 (reduced)
        {4: 2.0, 6: 3.0},  # 5 (reduced)
        {5: 3.0, 7: 2.0},  # 6 (non-reduced junction)
        {6: 2.0, 8: 1.0},  # 7 (reduced)
        {7: 1.0, 0: 3.0},  # 8 (reduced)
    ]


def _run_ch_tnr_reduced_tests(graph_cls):
    g_data = _build_test_graph()
    g = graph_cls(g_data)
    g.reduce()

    assert g.is_reduced[0] is False
    assert g.is_reduced[1] is True
    assert g.is_reduced[2] is True
    assert g.is_reduced[3] is False
    assert g.is_reduced[4] is True
    assert g.is_reduced[5] is True
    assert g.is_reduced[6] is True
    assert g.is_reduced[7] is True
    assert g.is_reduced[8] is True

    # Preprocess CH and TNR on the reduced graph
    g.create_contraction_hierarchy()
    g.create_tnr_hierarchy(num_transit_nodes=2)

    # Test all possible pairs (0 to 8)
    for u in range(9):
        for v in range(9):
            # Ground truth from dijkstra
            dijkstra_res = g.dijkstra(u, v)

            # 1. Contraction Hierarchy
            ch_res = g.contraction_hierarchy(u, v)
            assert abs(ch_res["length"] - dijkstra_res["length"]) < 1e-6, (
                f"CH length mismatch for {u} -> {v}: "
                f"got {ch_res['length']}, expected {dijkstra_res['length']}"
            )
            assert ch_res["path"] == dijkstra_res["path"], (
                f"CH path mismatch for {u} -> {v}: "
                f"got {ch_res['path']}, expected {dijkstra_res['path']}"
            )

            # CH length_only
            ch_len = g.contraction_hierarchy(u, v, length_only=True)
            assert abs(ch_len["length"] - dijkstra_res["length"]) < 1e-6
            assert "path" not in ch_len or ch_len["path"] == []

            # 2. Transit Node Routing
            tnr_res = g.tnr(u, v)
            assert abs(tnr_res["length"] - dijkstra_res["length"]) < 1e-6, (
                f"TNR length mismatch for {u} -> {v}: "
                f"got {tnr_res['length']}, expected {dijkstra_res['length']}"
            )
            assert tnr_res["path"] == dijkstra_res["path"], (
                f"TNR path mismatch for {u} -> {v}: "
                f"got {tnr_res['path']}, expected {dijkstra_res['path']}"
            )

            # TNR length_only
            tnr_len = g.tnr(u, v, length_only=True)
            assert abs(tnr_len["length"] - dijkstra_res["length"]) < 1e-6
            assert "path" not in tnr_len or tnr_len["path"] == []


def _run_tree_ops_reduced_tests(graph_cls):
    g_data = _build_test_graph()
    g = graph_cls(g_data)
    g.reduce()

    # Verify that get_shortest_path_tree, get_tree_path, and cached_shortest_path
    # work across all nodes (including reduced nodes) and do not return inf for valid reachable nodes.
    for u in range(9):
        tree = g.get_shortest_path_tree(u)
        assert len(tree["distance_matrix"]) == 9
        for v in range(9):
            dijkstra_res = g.dijkstra(u, v)
            assert (
                abs(tree["distance_matrix"][v] - dijkstra_res["length"]) < 1e-6
            )

            tree_path = g.get_tree_path(u, v, tree)
            assert abs(tree_path["length"] - dijkstra_res["length"]) < 1e-6
            assert tree_path["path"] == dijkstra_res["path"]

            # cached_shortest_path
            cached_res = g.cached_shortest_path(u, v)
            assert abs(cached_res["length"] - dijkstra_res["length"]) < 1e-6
            assert cached_res["path"] == dijkstra_res["path"]


def test_python_ch_tnr_reduced_graph():
    _run_ch_tnr_reduced_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_ch_tnr_reduced_graph():
    _run_ch_tnr_reduced_tests(CppGraph)


def test_python_tree_ops_reduced_graph():
    _run_tree_ops_reduced_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_tree_ops_reduced_graph():
    _run_tree_ops_reduced_tests(CppGraph)
