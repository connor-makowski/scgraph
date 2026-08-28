import pytest
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _build_complex_chain_graph(graph_cls):
    # Graph layout:
    # J0 (0) is a junction (degree 3) -> unreduced
    # Chain 1: 0 - 1 - 2 - 3 (1, 2 reduced)
    # J1 (3) is a junction (degree 3) -> unreduced
    # Chain 2: 3 - 4 - 5 - 6 (4, 5 reduced)
    # J2 (6) is a junction (degree 3) -> unreduced
    # Side dummy nodes on junctions with degree 3:
    # 0 connects to 100, 101
    # 3 connects to 102, 103
    # 6 connects to 104, 105
    data = {
        0: {1: 2.0, 100: 10.0, 101: 10.0},
        1: {0: 2.0, 2: 3.0},  # reduced, Chain A
        2: {1: 3.0, 3: 4.0},  # reduced, Chain A
        3: {2: 4.0, 4: 1.5, 102: 10.0, 103: 10.0},  # unreduced junction
        4: {3: 1.5, 5: 2.5},  # reduced, Chain B
        5: {4: 2.5, 6: 3.5},  # reduced, Chain B
        6: {5: 3.5, 104: 10.0, 105: 10.0},  # unreduced junction
        100: {0: 10.0, 106: 1.0, 107: 1.0},
        101: {0: 10.0, 108: 1.0, 109: 1.0},
        102: {3: 10.0, 110: 1.0, 111: 1.0},
        103: {3: 10.0, 112: 1.0, 113: 1.0},
        104: {6: 10.0, 114: 1.0, 115: 1.0},
        105: {6: 10.0, 116: 1.0, 117: 1.0},
        106: {100: 1.0},
        107: {100: 1.0},
        108: {101: 1.0},
        109: {101: 1.0},
        110: {102: 1.0},
        111: {102: 1.0},
        112: {103: 1.0},
        113: {103: 1.0},
        114: {104: 1.0},
        115: {104: 1.0},
        116: {105: 1.0},
        117: {105: 1.0},
    }

    max_node = max(data.keys())
    adj_list = [data.get(i, {}) for i in range(max_node + 1)]
    return graph_cls(adj_list)


def _run_dual_sided_reduction_tests(graph_cls):
    g = _build_complex_chain_graph(graph_cls)
    g.reduce()

    # Verify reduced state
    assert g.is_reduced[1] is True
    assert g.is_reduced[2] is True
    assert g.is_reduced[4] is True
    assert g.is_reduced[5] is True
    assert g.is_reduced[0] is False
    assert g.is_reduced[3] is False
    assert g.is_reduced[6] is False

    # Outbound reduced_graph connections
    # Node 1 is reduced; in reduced_graph, it should have outbound edges to boundary nodes 0 and 3
    rg_1 = g.reduced_graph[1]
    assert 0 in rg_1
    assert 3 in rg_1
    assert rg_1[0] == 2.0  # 1 -> 0
    assert rg_1[3] == 7.0  # 1 -> 2 -> 3 (3.0 + 4.0)

    # Inbound reduced_inverse_graph connections
    # Node 2 is reduced; in reduced_inverse_graph, it should have inbound edges from boundary nodes 0 and 3
    rig_2 = g.reduced_inverse_graph[2]
    assert 0 in rig_2
    assert 3 in rig_2
    assert rig_2[0] == 5.0  # 0 -> 1 -> 2 (2.0 + 3.0)
    assert rig_2[3] == 4.0  # 3 -> 2 (4.0)

    algorithms = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "dijkstra_negative",
        "a_star",
        "bellman_ford",
    ]

    # Test cases:
    # Case 1: Same chain query (1 -> 2)
    for algo in algorithms:
        res = getattr(g, algo)(1, 2)
        assert (
            abs(res["length"] - 3.0) < 1e-6
        ), f"{algo} same-chain length mismatch"
        assert res["path"] == [1, 2], f"{algo} same-chain path mismatch"

    # Case 2: Unreduced origin to Reduced destination across junction (0 -> 4)
    # Path: 0 -> 1 -> 2 -> 3 -> 4 (length: 2 + 3 + 4 + 1.5 = 10.5)
    for algo in algorithms:
        res = getattr(g, algo)(0, 4)
        assert (
            abs(res["length"] - 10.5) < 1e-6
        ), f"{algo} 0->4 length mismatch: {res}"
        assert res["path"] == [
            0,
            1,
            2,
            3,
            4,
        ], f"{algo} 0->4 path mismatch: {res}"

    # Case 3: Reduced origin in Chain A to Reduced destination in Chain B (1 -> 5)
    # Path: 1 -> 2 -> 3 -> 4 -> 5 (length: 3 + 4 + 1.5 + 2.5 = 11.0)
    for algo in algorithms:
        res = getattr(g, algo)(1, 5)
        assert (
            abs(res["length"] - 11.0) < 1e-6
        ), f"{algo} 1->5 length mismatch: {res}"
        assert res["path"] == [
            1,
            2,
            3,
            4,
            5,
        ], f"{algo} 1->5 path mismatch: {res}"

    # Case 4: Reverse query from Chain B to Chain A (5 -> 1)
    # Path: 5 -> 4 -> 3 -> 2 -> 1 (length: 2.5 + 1.5 + 4 + 3 = 11.0)
    for algo in algorithms:
        res = getattr(g, algo)(5, 1)
        assert (
            abs(res["length"] - 11.0) < 1e-6
        ), f"{algo} 5->1 length mismatch: {res}"
        assert res["path"] == [
            5,
            4,
            3,
            2,
            1,
        ], f"{algo} 5->1 path mismatch: {res}"

    # Case 5: Multi-origin query ({0, 100} -> 5)
    for algo in ["dijkstra", "bidirectional_dijkstra"]:
        res = getattr(g, algo)({0, 100}, 5)
        assert (
            abs(res["length"] - 13.0) < 1e-6
        ), f"{algo} multi-origin length mismatch"
        assert res["path"] == [
            0,
            1,
            2,
            3,
            4,
            5,
        ], f"{algo} multi-origin path mismatch"


def test_python_dual_sided_reduction():
    _run_dual_sided_reduction_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_dual_sided_reduction():
    _run_dual_sided_reduction_tests(CppGraph)


def test_dual_sided_reduction_parity_marnet(marnet):
    if not HAS_CPP:
        pytest.skip("C++ extension not available")

    py_g = PyGraph(marnet.graph)
    cpp_g = CppGraph(marnet.graph)

    py_g.reduce()
    cpp_g.reduce()

    # Compare properties
    assert py_g.is_reduced == cpp_g.is_reduced
    assert py_g.reduced_node_chain_ids == cpp_g.reduced_node_chain_ids
    assert py_g.reduced_graph == cpp_g.reduced_graph
    assert py_g.reduced_inverse_graph == cpp_g.reduced_inverse_graph

    # Compare query outputs for 20 pairs
    pairs = [
        (0, 5),
        (100, 7999),
        (4022, 8342),
        (10, 20),
        (50, 60),
        (500, 1500),
    ]
    for org, dest in pairs:
        for algo in [
            "dijkstra",
            "bidirectional_dijkstra",
            "a_star",
            "dijkstra_buckets",
        ]:
            py_res = getattr(py_g, algo)(org, dest)
            cpp_res = getattr(cpp_g, algo)(org, dest)
            assert abs(py_res["length"] - cpp_res["length"]) < 1e-5
            assert py_res["path"] == cpp_res["path"]


def test_dual_sided_reduction_thread_safety(marnet):
    import concurrent.futures

    py_g = PyGraph(marnet.graph)
    py_g.reduce()

    pairs = [
        (0, 5),
        (100, 7999),
        (4022, 8342),
        (10, 20),
        (50, 60),
    ]

    def run_query(pair):
        org, dest = pair
        return py_g.dijkstra(org, dest)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(run_query, pair) for pair in pairs * 10]
        results = [f.result() for f in futures]
        assert len(results) == 50

    if HAS_CPP:
        cpp_g = CppGraph(marnet.graph)
        cpp_g.reduce()

        def run_cpp_query(pair):
            org, dest = pair
            return cpp_g.dijkstra(org, dest)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(run_cpp_query, pair) for pair in pairs * 10
            ]
            results = [f.result() for f in futures]
            assert len(results) == 50
