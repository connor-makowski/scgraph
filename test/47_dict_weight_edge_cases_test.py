import pytest
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

GRAPH_CLASSES = [PyGraph] + ([CppGraph] if HAS_CPP else [])

ALL_ALGORITHMS = [
    "dijkstra",
    "bidirectional_dijkstra",
    "dijkstra_buckets",
    "bidirectional_buckets",
    "dijkstra_negative",
    "bellman_ford",
    "a_star",
    "bmssp",
    "cached_shortest_path",
    "contraction_hierarchy",
    "tnr",
]


@pytest.fixture
def edge_case_graph():
    # 0 --(1)--> 1 --(1)--> 2
    # 0 --------(5)-------> 3
    # 4 --------(5)-------> 2
    # 4 --------(6)-------> 3
    return [
        {1: 1.0, 3: 5.0},  # 0
        {2: 1.0},  # 1
        {},  # 2
        {},  # 3
        {2: 5.0, 3: 6.0},  # 4
    ]


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_exit_weights_inversion_all_algorithms(edge_case_graph, GraphClass):
    """Test that a shorter internal graph destination (node 2, dist 2) is bypassed in favor

    of a longer internal destination (node 3, dist 5) when destination exit weights make node 3 cheaper.
    """
    g = GraphClass(edge_case_graph)
    g.create_contraction_hierarchy()
    g.create_tnr_hierarchy(num_transit_nodes=3)

    origin = 0
    # Inbound to node 2: path length 2.0. With exit penalty 100.0 -> total 102.0
    # Inbound to node 3: path length 5.0. With exit penalty 1.0   -> total 6.0
    dest_dict = {2: 100.0, 3: 1.0}

    for algo in ALL_ALGORITHMS:
        fn = getattr(g, algo)
        res = fn(origin_id=origin, destination_id=dest_dict)
        assert res["path"] == [
            0,
            3,
        ], f"{algo} failed to pick destination with lower total cost"
        assert (
            abs(res["length"] - 6.0) < 1e-6
        ), f"{algo} computed incorrect total length with exit weights"

    # Reversed exit weights: node 2 has exit 1.0 (total 3.0), node 3 has exit 100.0 (total 105.0)
    dest_dict_rev = {2: 1.0, 3: 100.0}
    for algo in ALL_ALGORITHMS:
        fn = getattr(g, algo)
        res = fn(origin_id=origin, destination_id=dest_dict_rev)
        assert res["path"] == [0, 1, 2], f"{algo} failed to pick destination 2"
        assert (
            abs(res["length"] - 3.0) < 1e-6
        ), f"{algo} computed incorrect length for destination 2"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_origin_weights_inversion_all_algorithms(edge_case_graph, GraphClass):
    """Test that a shorter internal graph origin (node 0, dist 2) is bypassed in favor

    of a longer internal origin (node 4, dist 5) when origin starting weights make node 4 cheaper.
    """
    g = GraphClass(edge_case_graph)
    g.create_contraction_hierarchy()
    g.create_tnr_hierarchy(num_transit_nodes=3)

    destination = 2
    # Outbound from node 0 to 2: path length 2.0. With start penalty 100.0 -> total 102.0
    # Outbound from node 4 to 2: path length 5.0. With start penalty 1.0   -> total 6.0
    origin_dict = {0: 100.0, 4: 1.0}

    for algo in ALL_ALGORITHMS:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict, destination_id=destination)
        assert res["path"] == [
            4,
            2,
        ], f"{algo} failed to pick origin with lower total cost"
        assert (
            abs(res["length"] - 6.0) < 1e-6
        ), f"{algo} computed incorrect total length with start weights"

    # Reversed start weights: node 0 has start 1.0 (total 3.0), node 4 has start 100.0 (total 105.0)
    origin_dict_rev = {0: 1.0, 4: 100.0}
    for algo in ALL_ALGORITHMS:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict_rev, destination_id=destination)
        assert res["path"] == [0, 1, 2], f"{algo} failed to pick origin 0"
        assert (
            abs(res["length"] - 3.0) < 1e-6
        ), f"{algo} computed incorrect length for origin 0"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_combined_origin_and_exit_weights_all_algorithms(
    edge_case_graph, GraphClass
):
    """Test combining both origin start weights and destination exit weights simultaneously."""
    g = GraphClass(edge_case_graph)
    g.create_contraction_hierarchy()
    g.create_tnr_hierarchy(num_transit_nodes=3)

    # 0 -> 2: 50.0 (start) + 2.0 (graph) + 50.0 (exit) = 102.0
    # 0 -> 3: 50.0 (start) + 5.0 (graph) + 1.0 (exit)  = 56.0
    # 4 -> 2: 1.0 (start)  + 5.0 (graph) + 50.0 (exit) = 56.0
    # 4 -> 3: 1.0 (start)  + 6.0 (graph) + 1.0 (exit)  = 8.0 (optimal)
    origin_dict = {0: 50.0, 4: 1.0}
    dest_dict = {2: 50.0, 3: 1.0}

    for algo in ALL_ALGORITHMS:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict, destination_id=dest_dict)
        assert res["path"] == [
            4,
            3,
        ], f"{algo} failed combined start/exit weight selection"
        assert (
            abs(res["length"] - 8.0) < 1e-6
        ), f"{algo} computed incorrect length for combined weights"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_tree_path_exit_and_start_weight_inversions(
    edge_case_graph, GraphClass
):
    """Test get_tree_path with tree built from node 0 and queried with start distance offset and exit weights."""
    g = GraphClass(edge_case_graph)
    tree = g.get_shortest_path_tree(origin_id=0)

    # 1. Start offset 10.0 on origin 0; exit weights make destination 3 cheaper (10+5+1=16 vs 10+2+100=112)
    res = g.get_tree_path(
        origin_id={0: 10.0},
        destination_id={2: 100.0, 3: 1.0},
        tree_data=tree,
    )
    assert res["path"] == [0, 3]
    assert abs(res["length"] - 16.0) < 1e-6

    # 2. Length-only mode
    res_len = g.get_tree_path(
        origin_id={0: 10.0},
        destination_id={2: 100.0, 3: 1.0},
        tree_data=tree,
        length_only=True,
    )
    assert res_len["path"] == []
    assert abs(res_len["length"] - 16.0) < 1e-6

    # 3. Swap exit weights so destination 2 is cheaper (10+2+1=13 vs 10+5+100=115)
    res2 = g.get_tree_path(
        origin_id={0: 10.0},
        destination_id={2: 1.0, 3: 100.0},
        tree_data=tree,
    )
    assert res2["path"] == [0, 1, 2]
    assert abs(res2["length"] - 13.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_overlap_direct_vs_path_with_weights(GraphClass):
    """Test when origin and destination sets overlap, checking whether a direct same-node

    or a traversable multi-hop path is selected based on start/exit weights.
    """
    # 0 --(2)--> 1 --(2)--> 2
    graph = [
        {1: 2.0},  # 0
        {2: 2.0},  # 1
        {},  # 2
    ]
    g = GraphClass(graph)

    # Overlapping node 1 has huge start & exit weights (20.0 + 20.0 = 40.0)
    # Path 0 -> 1 -> 2 has start 1.0 + graph (2+2) + exit 1.0 = 6.0
    origin_dict = {1: 20.0, 0: 1.0}
    dest_dict = {1: 20.0, 2: 1.0}

    for algo in ALL_ALGORITHMS:
        if algo in ["contraction_hierarchy", "tnr"]:
            continue  # CH/TNR preprocessor requires larger graph
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict, destination_id=dest_dict)
        assert res["path"] == [
            0,
            1,
            2,
        ], f"{algo} failed to choose multi-hop over expensive overlap"
        assert abs(res["length"] - 6.0) < 1e-6

    # Now make the overlapping node 1 very cheap (1.0 + 1.0 = 2.0) vs path 0 -> 2 (10.0 + 4.0 + 10.0 = 24.0)
    cheap_origin_dict = {1: 1.0, 0: 10.0}
    cheap_dest_dict = {1: 1.0, 2: 10.0}

    for algo in ALL_ALGORITHMS:
        if algo in ["contraction_hierarchy", "tnr"]:
            continue
        fn = getattr(g, algo)
        res = fn(origin_id=cheap_origin_dict, destination_id=cheap_dest_dict)
        assert res["path"] == [
            1
        ], f"{algo} failed to choose cheap direct connection"
        assert abs(res["length"] - 2.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_reduced_graph_with_weight_inversions(edge_case_graph, GraphClass):
    """Test that graph reduction preserves start and exit weight inversions."""
    g = GraphClass(edge_case_graph)
    g.reduce(iterations=1)

    reduced_algos = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "bellman_ford",
        "a_star",
        "cached_shortest_path",
    ]

    # Destination weight inversion on reduced graph:
    # Inbound to node 2 is contracted chain 0 -> 1 -> 2 (dist 2) + exit 100.0 = 102.0
    # Inbound to node 3 is direct edge 0 -> 3 (dist 5) + exit 1.0 = 6.0
    dest_dict = {2: 100.0, 3: 1.0}
    for algo in reduced_algos:
        fn = getattr(g, algo)
        res = fn(origin_id=0, destination_id=dest_dict)
        assert res["path"] == [
            0,
            3,
        ], f"{algo} failed on reduced graph destination inversion"
        assert abs(res["length"] - 6.0) < 1e-6

    # Origin weight inversion on reduced graph:
    origin_dict = {0: 100.0, 4: 1.0}
    for algo in reduced_algos:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict, destination_id=2)
        assert res["path"] == [
            4,
            2,
        ], f"{algo} failed on reduced graph origin inversion"
        assert abs(res["length"] - 6.0) < 1e-6
