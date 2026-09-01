import pytest
from scgraph.graph import Graph as PyGraph
from scgraph.transit_node_routing import TNRGraph as PyTNRGraph

try:
    from scgraph.cpp import Graph as CppGraph
    from scgraph.cpp import TNRGraph as CppTNRGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

# Adversarial contraction graph:
# 1 -> 2 -> 3 (weight 1.5 + 1.5 = 3.0)
# 1 -> 0 -> 4 -> 3 (weight 1.0 + 1.0 + 1.0 = 3.0)
# Node 4 has high degree, so it is contracted after 1 and 3.
# Node 0 and 1 also have higher degrees so they are contracted after 2.
# When 2 is contracted, 0, 1, 4 are all uncontracted.
# - High settled_limit finds witness path 1 -> 0 -> 4 -> 3 and skips shortcut (1, 3).
# - Low settled_limit aborts and adds shortcut (1, 3) via 2.
_ADVERSARIAL_GRAPH = [
    {4: 1.0, 12: 1.0, 13: 1.0},  # 0
    {2: 1.5, 0: 1.0, 11: 1.0},  # 1
    {3: 1.5},  # 2
    {},  # 3
    {3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0, 10: 1.0},  # 4
    {},  # 5
    {},  # 6
    {},  # 7
    {},  # 8
    {},  # 9
    {},  # 10
    {},  # 11
    {},  # 12
    {},  # 13
]


def _run_settled_limit_comparison(graph_class):
    # 1. High settled limit: should find the witness path and skip adding the shortcut
    g_high = graph_class(_ADVERSARIAL_GRAPH)
    ch_high = g_high.create_contraction_hierarchy(settled_limit=10)
    shortcuts_high = ch_high.shortcuts

    # 2. Low settled limit: should abort and add the shortcut
    g_low = graph_class(_ADVERSARIAL_GRAPH)
    ch_low = g_low.create_contraction_hierarchy(settled_limit=2)
    shortcuts_low = ch_low.shortcuts

    # Verify that shortcuts_low has more shortcuts than shortcuts_high
    assert len(shortcuts_low) > len(shortcuts_high), (
        f"Low settled limit should add more shortcuts ({len(shortcuts_low)}) "
        f"than high settled limit ({len(shortcuts_high)})"
    )

    # Verify that query correctness is preserved in both cases
    res_high = g_high.contraction_hierarchy(1, 3)
    res_low = g_low.contraction_hierarchy(1, 3)
    res_dijkstra = g_high.dijkstra(1, 3)

    assert abs(res_high["length"] - 3.0) < 1e-9
    assert abs(res_low["length"] - 3.0) < 1e-9
    assert abs(res_dijkstra["length"] - 3.0) < 1e-9


def test_python_settled_limit():
    _run_settled_limit_comparison(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_settled_limit():
    _run_settled_limit_comparison(CppGraph)


# --- Disconnected Graphs / Unreachable Target Test ---
def _run_disconnected_graph_tests(graph_class, tnr_class):
    # Two disconnected components: (0, 1) and (2, 3)
    data = [
        {1: 1.0},  # 0
        {0: 1.0},  # 1
        {3: 2.0},  # 2
        {2: 2.0},  # 3
    ]
    g = graph_class(data)

    # 1. Same-node queries (0 -> 0)
    res_ch = g.contraction_hierarchy(0, 0)
    assert res_ch["length"] == 0.0
    assert res_ch["path"] == [0]

    # 2. Connected query (0 -> 1)
    res_ch = g.contraction_hierarchy(0, 1)
    assert res_ch["length"] == 1.0
    assert res_ch["path"] == [0, 1]

    # 3. Unreachable query (0 -> 2)
    with pytest.raises(Exception):
        g.contraction_hierarchy(0, 2)

    # TNR behavior
    tnr = tnr_class(graph=data, num_transit_nodes=2)

    # Connected
    res_tnr = tnr.get_shortest_path(0, 1)
    assert res_tnr["length"] == 1.0
    assert res_tnr["path"] == [0, 1]

    # Unreachable
    with pytest.raises(Exception):
        tnr.get_shortest_path(0, 2)


def test_python_disconnected_graph():
    _run_disconnected_graph_tests(PyGraph, PyTNRGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_disconnected_graph():
    _run_disconnected_graph_tests(CppGraph, CppTNRGraph)


# --- Very Small Graphs Test ---
def _run_very_small_graph_tests(graph_class, tnr_class):
    # Single node graph
    g1 = graph_class([{}])
    res_ch1 = g1.contraction_hierarchy(0, 0)
    assert res_ch1["length"] == 0.0
    assert res_ch1["path"] == [0]

    # Single node TNR
    tnr1 = tnr_class(graph=[{}], num_transit_nodes=1)
    res_tnr1 = tnr1.get_shortest_path(0, 0)
    assert res_tnr1["length"] == 0.0
    assert res_tnr1["path"] == [0]

    # Two nodes, disconnected
    g2 = graph_class([{}, {}])
    with pytest.raises(Exception):
        g2.contraction_hierarchy(0, 1)

    tnr2 = tnr_class(graph=[{}, {}], num_transit_nodes=1)
    with pytest.raises(Exception):
        tnr2.get_shortest_path(0, 1)


def test_python_very_small_graph():
    _run_very_small_graph_tests(PyGraph, PyTNRGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_very_small_graph():
    _run_very_small_graph_tests(CppGraph, CppTNRGraph)


# --- Transit Nodes Selection Edge Cases in TNR ---
def _run_tnr_transit_count_edge_cases(tnr_class):
    # Graph of 4 nodes
    data = [
        {1: 1.0},
        {2: 1.0},
        {3: 1.0},
        {},
    ]

    # Case A: Request more transit nodes than exists in graph
    tnr_large = tnr_class(graph=data, num_transit_nodes=10)
    res_large = tnr_large.get_shortest_path(0, 3)
    assert res_large["length"] == 3.0
    assert res_large["path"] == [0, 1, 2, 3]

    # Case B: Request 0 transit nodes
    tnr_zero = tnr_class(graph=data, num_transit_nodes=0)
    res_zero = tnr_zero.get_shortest_path(0, 3)
    assert res_zero["length"] == 3.0
    assert res_zero["path"] == [0, 1, 2, 3]


def test_python_tnr_transit_count_edge_cases():
    _run_tnr_transit_count_edge_cases(PyTNRGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_tnr_transit_count_edge_cases():
    _run_tnr_transit_count_edge_cases(CppTNRGraph)


# --- Dynamic Node Addition Test ---
def _run_dynamic_node_addition_tests(graph_class, tnr_class):
    # Standard graph
    data = [
        {1: 5.0, 2: 1.0},
        {0: 5.0, 2: 2.0, 3: 1.0},
        {0: 1.0, 1: 2.0, 3: 4.0, 4: 8.0},
        {1: 1.0, 2: 4.0, 4: 3.0, 5: 6.0},
        {2: 8.0, 3: 3.0},
        {3: 6.0},
    ]
    # Use separate copies to prevent in-place modifications from interfering
    data_ch = [d.copy() for d in data]
    g = graph_class(data_ch)
    g.create_contraction_hierarchy()

    # Dynamic add new node 6, connected to node 0 with weight 2.0 and node 5 with weight 3.0
    new_node_id = g.add_node({0: 2.0, 5: 3.0}, symmetric=True)
    assert new_node_id == 6

    # Query using CH from the dynamic node to other nodes
    res_ch_to = g.contraction_hierarchy(6, 3)
    res_ch_from = g.contraction_hierarchy(3, 6)

    # Dijkstra baseline for verification (should include the new node)
    res_dijkstra = g.dijkstra(6, 3)

    assert abs(res_ch_to["length"] - res_dijkstra["length"]) < 1e-9
    assert abs(res_ch_from["length"] - res_dijkstra["length"]) < 1e-9
    assert res_ch_to["path"] == res_dijkstra["path"]

    # TNR Dynamic node addition test
    data_tnr = [d.copy() for d in data]
    tnr = tnr_class(graph=data_tnr, num_transit_nodes=2)
    # Add dynamic node to TNR
    new_tnr_node_id = tnr.add_node({0: 2.0, 5: 3.0}, symmetric=True)
    assert new_tnr_node_id == 6

    res_tnr_to = tnr.get_shortest_path(6, 3)
    res_tnr_from = tnr.get_shortest_path(3, 6)

    assert abs(res_tnr_to["length"] - res_dijkstra["length"]) < 1e-9
    assert abs(res_tnr_from["length"] - res_dijkstra["length"]) < 1e-9
    assert res_tnr_to["path"] == res_dijkstra["path"]


def test_python_dynamic_node_addition():
    _run_dynamic_node_addition_tests(PyGraph, PyTNRGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_dynamic_node_addition():
    _run_dynamic_node_addition_tests(CppGraph, CppTNRGraph)


# --- Query-Time Dynamic Node Addition on C++ hierarchy classes directly ---
@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_hierarchy_query_time_add_node():
    data = [
        {1: 5.0, 2: 1.0},
        {0: 5.0, 2: 2.0, 3: 1.0},
        {0: 1.0, 1: 2.0, 3: 4.0, 4: 8.0},
        {1: 1.0, 2: 4.0, 4: 3.0, 5: 6.0},
        {2: 8.0, 3: 3.0},
        {3: 6.0},
    ]

    # Create C++ Graph and warm up CH
    g = CppGraph(data)
    ch = g.create_contraction_hierarchy()

    # Add dynamic node to CH object directly at query-time (bypassing rebuilding contraction rank)
    new_node_id = ch.add_node({0: 2.0, 5: 3.0}, True)
    assert new_node_id == 6

    # Test CH directly
    res_ch = ch.search(6, 3)
    # Re-calculate correct dijkstra distance including new node
    # Since CppGraph does not rebuild its internal graph structure automatically,
    # we can rebuild to verify with dijkstra, or use known ground truth:
    # 6 -> 0 (2.0) -> 2 (1.0) -> 1 (2.0) -> 3 (1.0) = 6.0
    assert abs(res_ch["length"] - 6.0) < 1e-9
    assert res_ch["path"] == [6, 0, 2, 1, 3]

    # Create C++ TNRGraph
    tnr = CppTNRGraph(graph=data, num_transit_nodes=2)
    # Add dynamic node to C++ TNR object directly
    new_tnr_node_id = tnr.add_node({0: 2.0, 5: 3.0}, True)
    assert new_tnr_node_id == 6

    # Query TNR directly
    res_tnr = tnr.get_shortest_path(6, 3)
    assert abs(res_tnr["length"] - 6.0) < 1e-9
    assert res_tnr["path"] == [6, 0, 2, 1, 3]
