import pytest
from scgraph.graph import Graph as PyGraph
from scgraph.utils import haversine

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

GRAPH_CLASSES = [PyGraph] + ([CppGraph] if HAS_CPP else [])


@pytest.fixture
def sample_graph():
    return [
        {1: 2.0},  # 0
        {2: 3.0},  # 1
        {3: 4.0, 5: 2.0},  # 2
        {},  # 3
        {1: 1.0},  # 4
        {},  # 5
    ]


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_get_tree_path_dict_inputs(sample_graph, GraphClass):
    """Test get_tree_path with dict origins (with start offsets) and dict destinations (with exit penalties)."""
    g = GraphClass(sample_graph)
    tree = g.get_shortest_path_tree(origin_id=0)

    # 0 -> 1(2) -> 2(3) -> 3(4) = 9.0; with start_dist=5.0 and exit_dist=1.0 -> 15.0
    # 0 -> 1(2) -> 2(3) -> 5(2) = 7.0; with start_dist=5.0 and exit_dist=10.0 -> 22.0
    res = g.get_tree_path(
        origin_id={0: 5.0},
        destination_id={3: 1.0, 5: 10.0},
        tree_data=tree,
    )
    assert res["path"] == [0, 1, 2, 3]
    assert abs(res["length"] - 15.0) < 1e-6

    # length_only mode
    res_len = g.get_tree_path(
        origin_id={0: 5.0},
        destination_id={3: 1.0, 5: 10.0},
        tree_data=tree,
        length_only=True,
    )
    assert res_len["path"] == []
    assert abs(res_len["length"] - 15.0) < 1e-6

    # Single int origin with set destinations -> node 5 is closer (7.0 < 9.0)
    res_set = g.get_tree_path(
        origin_id=0,
        destination_id={3, 5},
        tree_data=tree,
    )
    assert res_set["path"] == [0, 1, 2, 5]
    assert abs(res_set["length"] - 7.0) < 1e-6

    # Origin mismatch raises exception
    with pytest.raises(Exception):
        g.get_tree_path(
            origin_id=1,
            destination_id=3,
            tree_data=tree,
        )


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_all_graph_algorithms_dict_origins_and_destinations(
    sample_graph, GraphClass
):
    """Test all graph algorithms with dictionary origins and destinations."""
    g = GraphClass(sample_graph)
    g.create_contraction_hierarchy()
    g.create_tnr_hierarchy(num_transit_nodes=3)

    algorithms = [
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

    # Scenario 1:
    # 0 with start 10.0, 4 with start 2.0 -> destinations: 3 with exit 5.0, 5 with exit 1.0
    # From 4 to 5: 2 + 6 + 1 = 9.0 (path [4, 1, 2, 5])
    origin_dict_1 = {0: 10.0, 4: 2.0}
    dest_dict_1 = {3: 5.0, 5: 1.0}

    for algo in algorithms:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict_1, destination_id=dest_dict_1)
        assert res["path"] == [4, 1, 2, 5], f"{algo} failed path check"
        assert abs(res["length"] - 9.0) < 1e-6, f"{algo} failed length check"

    # Scenario 2:
    # 0 with start 10.0, 4 with start 2.0 -> destinations: 3 with exit 1.0, 5 with exit 10.0
    # From 4 to 3: 2 + 8 + 1 = 11.0 (path [4, 1, 2, 3])
    dest_dict_2 = {3: 1.0, 5: 10.0}

    for algo in algorithms:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict_1, destination_id=dest_dict_2)
        assert res["path"] == [4, 1, 2, 3], f"{algo} failed path check"
        assert abs(res["length"] - 11.0) < 1e-6, f"{algo} failed length check"

    # Scenario 3:
    # 0 with start 0.0, 4 with start 20.0 -> destinations: 3 with exit 1.0, 5 with exit 10.0
    # From 0 to 3: 0 + 9 + 1 = 10.0 (path [0, 1, 2, 3])
    origin_dict_3 = {0: 0.0, 4: 20.0}

    for algo in algorithms:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict_3, destination_id=dest_dict_2)
        assert res["path"] == [0, 1, 2, 3], f"{algo} failed path check"
        assert abs(res["length"] - 10.0) < 1e-6, f"{algo} failed length check"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_all_graph_algorithms_dict_inputs_on_reduced_graph(
    sample_graph, GraphClass
):
    """Test graph algorithms with dictionary origins and destinations on a reduced graph."""
    g = GraphClass(sample_graph)
    g.reduce(iterations=1)

    algorithms = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "bellman_ford",
        "a_star",
        "cached_shortest_path",
    ]

    origin_dict = {0: 10.0, 4: 2.0}
    dest_dict = {3: 5.0, 5: 1.0}

    for algo in algorithms:
        fn = getattr(g, algo)
        res = fn(origin_id=origin_dict, destination_id=dest_dict)
        assert res["path"] == [
            4,
            1,
            2,
            5,
        ], f"{algo} on reduced graph failed path"
        assert (
            abs(res["length"] - 9.0) < 1e-6
        ), f"{algo} on reduced graph failed length"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_cached_shortest_path_dict_inputs(sample_graph, GraphClass):
    """Test cached_shortest_path multi-origin fallback to Dijkstra."""
    g = GraphClass(sample_graph)
    origin_dict = {0: 10.0, 4: 5.0}
    destination_dict = {3: 0.0}

    res = g.cached_shortest_path(
        origin_id=origin_dict, destination_id=destination_dict
    )
    assert res["path"] == [4, 1, 2, 3]
    assert abs(res["length"] - 13.0) < 1e-6

    # Test with length_only
    res_len = g.cached_shortest_path(
        origin_id=origin_dict, destination_id=destination_dict, length_only=True
    )
    assert res_len["path"] == []
    assert abs(res_len["length"] - 13.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_cached_shortest_path_single_key_dict_and_set(sample_graph, GraphClass):
    """Test cached_shortest_path with 1-key dict, 1-element set, and cache reuse."""
    g = GraphClass(sample_graph)

    # 1-key dict with starting distance 10.0 from node 0 to destination 3
    # 0 -> 1(2) -> 2(3) -> 3(4) = 9.0 + 10.0 = 19.0
    res_dict = g.cached_shortest_path(origin_id={0: 10.0}, destination_id=3)
    assert res_dict["path"] == [0, 1, 2, 3]
    assert abs(res_dict["length"] - 19.0) < 1e-6

    # 1-key dict with length_only
    res_dict_len = g.cached_shortest_path(
        origin_id={0: 10.0}, destination_id=3, length_only=True
    )
    assert res_dict_len["path"] == []
    assert abs(res_dict_len["length"] - 19.0) < 1e-6

    # 1-element set from node 0 to destination 3 -> length 9.0
    res_set = g.cached_shortest_path(origin_id={0}, destination_id=3)
    assert res_set["path"] == [0, 1, 2, 3]
    assert abs(res_set["length"] - 9.0) < 1e-6

    # 1-element set with length_only
    res_set_len = g.cached_shortest_path(
        origin_id={0}, destination_id=3, length_only=True
    )
    assert res_set_len["path"] == []
    assert abs(res_set_len["length"] - 9.0) < 1e-6

    # Verify cache reuse: different starting distance on the same cached node 0
    res_dict2 = g.cached_shortest_path(origin_id={0: 50.0}, destination_id=3)
    assert res_dict2["path"] == [0, 1, 2, 3]
    assert abs(res_dict2["length"] - 59.0) < 1e-6

    # Plain int query also reuses the same cached tree
    res_int = g.cached_shortest_path(origin_id=0, destination_id=3)
    assert res_int["path"] == [0, 1, 2, 3]
    assert abs(res_int["length"] - 9.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_cached_shortest_path_multiple_exit_nodes(sample_graph, GraphClass):
    """Test cached_shortest_path with multiple exit nodes (set and dict with exit distances)."""
    g = GraphClass(sample_graph)

    # 1. Multiple exit nodes as a set {3, 5} -> destination 5 is closer (7.0 vs 9.0)
    res_set = g.cached_shortest_path(origin_id=0, destination_id={3, 5})
    assert res_set["path"] == [0, 1, 2, 5]
    assert abs(res_set["length"] - 7.0) < 1e-6

    # With length_only
    res_set_len = g.cached_shortest_path(
        origin_id=0, destination_id={3, 5}, length_only=True
    )
    assert res_set_len["path"] == []
    assert abs(res_set_len["length"] - 7.0) < 1e-6

    # 2. Multiple exit nodes as a dict with exit penalties:
    # 3 with exit cost 1.0 (9 + 1 = 10.0), 5 with exit cost 10.0 (7 + 10 = 17.0) -> 3 is better
    res_dict = g.cached_shortest_path(
        origin_id=0, destination_id={3: 1.0, 5: 10.0}
    )
    assert res_dict["path"] == [0, 1, 2, 3]
    assert abs(res_dict["length"] - 10.0) < 1e-6

    # 3. Multiple exit nodes combined with single-key dict origin {0: 5.0}:
    # 3: 5.0 (origin) + 9 (path) + 1.0 (exit) = 15.0
    # 5: 5.0 (origin) + 7 (path) + 10.0 (exit) = 22.0 -> 3 is chosen
    res_both = g.cached_shortest_path(
        origin_id={0: 5.0}, destination_id={3: 1.0, 5: 10.0}
    )
    assert res_both["path"] == [0, 1, 2, 3]
    assert abs(res_both["length"] - 15.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_cached_shortest_path_multiple_exit_nodes_all_origin_types(
    sample_graph, GraphClass
):
    """Test multiple exit destinations paired with int, 1-element set, 1-key dict, and multi-key dict origins."""
    g = GraphClass(sample_graph)
    destinations = {
        3: 5.0,
        5: 1.0,
    }  # to 3: path cost 9 + 5 = 14; to 5: path cost 7 + 1 = 8

    # Int origin 0
    res_int = g.cached_shortest_path(origin_id=0, destination_id=destinations)
    assert res_int["path"] == [0, 1, 2, 5]
    assert abs(res_int["length"] - 8.0) < 1e-6

    # 1-element set origin {0}
    res_set = g.cached_shortest_path(origin_id={0}, destination_id=destinations)
    assert res_set["path"] == [0, 1, 2, 5]
    assert abs(res_set["length"] - 8.0) < 1e-6

    # 1-key dict origin {0: 10.0}
    res_1dict = g.cached_shortest_path(
        origin_id={0: 10.0}, destination_id=destinations
    )
    assert res_1dict["path"] == [0, 1, 2, 5]
    assert abs(res_1dict["length"] - 18.0) < 1e-6

    # Multi-key dict origin {0: 10.0, 4: 2.0} (from 4: 4->1(1)->2(3)->5(2)=6 + 2 = 8 + 1 = 9)
    res_mdict = g.cached_shortest_path(
        origin_id={0: 10.0, 4: 2.0}, destination_id=destinations
    )
    assert res_mdict["path"] == [4, 1, 2, 5]
    assert abs(res_mdict["length"] - 9.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_cached_shortest_path_same_node_overlap(sample_graph, GraphClass):
    """Test cached_shortest_path when origin and destination contain overlapping nodes."""
    g = GraphClass(sample_graph)
    res = g.cached_shortest_path(
        origin_id={1: 5.0}, destination_id={1: 2.0, 3: 10.0}
    )
    assert res["path"] == [1]
    assert abs(res["length"] - 7.0) < 1e-6


def test_geograph_immutability_all_node_addition_types(marnet):
    """Test that all node_addition_types do not mutate the underlying graph or nodes."""
    orig_graph_len = len(marnet.graph_object.graph)
    orig_nodes_len = len(marnet.nodes)
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    addition_types = ["all", "kdquadrant", "quadrant", "kdclosest", "closest"]

    for add_type in addition_types:
        res = marnet.get_shortest_path(
            origin,
            dest,
            node_addition_type=add_type,
            destination_node_addition_type=add_type,
            output_path=True,
        )
        assert (
            len(marnet.graph_object.graph) == orig_graph_len
        ), f"Graph mutated with {add_type}!"
        assert (
            len(marnet.nodes) == orig_nodes_len
        ), f"Nodes mutated with {add_type}!"
        assert "path" in res
        assert "coordinate_path" in res
        assert res["length"] > 0


def test_geograph_all_node_addition_type_across_algorithms(marnet):
    """Test GeoGraph with node_addition_type='all' across all algorithms on marnet."""
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    marnet.graph_object.create_contraction_hierarchy()
    marnet.graph_object.create_tnr_hierarchy(num_transit_nodes=20)

    alg_names = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "a_star",
        "bellman_ford",
        "bmssp",
        "cached_shortest_path",
        "contraction_hierarchy",
        "tnr",
    ]

    results = {}
    for algo in alg_names:
        kwargs = {}
        if algo == "a_star":
            kwargs["heuristic_fn"] = marnet.haversine
        res = marnet.get_shortest_path(
            origin,
            dest,
            algorithm_fn=algo,
            algorithm_kwargs=kwargs,
            node_addition_type="all",
            destination_node_addition_type="all",
            node_addition_lat_lon_bound=5,
        )
        results[algo] = res["length"]

    # All shortest path algorithms should agree on the shortest path length
    dijkstra_len = results["dijkstra"]
    for algo, length in results.items():
        assert (
            abs(length - dijkstra_len) < 1e-2
        ), f"{algo} length {length} differs from dijkstra {dijkstra_len}"


def test_geograph_cached_shortest_path_multiple_exit_snapping(marnet):
    """Test GeoGraph with cached_shortest_path and multi-exit snapping (quadrant and all)."""
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    # Closest origin (cached) + quadrant destination (multiple exit nodes)
    res_quad = marnet.get_shortest_path(
        origin,
        dest,
        algorithm_fn="cached_shortest_path",
        node_addition_type="closest",
        destination_node_addition_type="quadrant",
    )
    res_dijk_quad = marnet.get_shortest_path(
        origin,
        dest,
        algorithm_fn="dijkstra",
        node_addition_type="closest",
        destination_node_addition_type="quadrant",
    )
    assert abs(res_quad["length"] - res_dijk_quad["length"]) < 1e-3
    assert res_quad["coordinate_path"] == res_dijk_quad["coordinate_path"]

    # Closest origin (cached) + all destination (multiple exit nodes in bounding box)
    res_all = marnet.get_shortest_path(
        origin,
        dest,
        algorithm_fn="cached_shortest_path",
        node_addition_type="closest",
        destination_node_addition_type="all",
        node_addition_lat_lon_bound=5,
    )
    res_dijk_all = marnet.get_shortest_path(
        origin,
        dest,
        algorithm_fn="dijkstra",
        node_addition_type="closest",
        destination_node_addition_type="all",
        node_addition_lat_lon_bound=5,
    )
    assert abs(res_all["length"] - res_dijk_all["length"]) < 1e-3
    assert res_all["coordinate_path"] == res_dijk_all["coordinate_path"]


def test_geograph_direct_connection(marnet):
    """Test origin and destination snapping to the same node (direct connection)."""
    origin = {"latitude": 30.001, "longitude": 160.001}
    dest = {"latitude": 30.002, "longitude": 160.002}

    res = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )
    assert len(res["coordinate_path"]) == 2
    assert res["coordinate_path"][0] == [30.001, 160.001]
    assert res["coordinate_path"][1] == [30.002, 160.002]
    assert res["length"] > 0


def test_geograph_direct_connection_shorter_than_network(marnet):
    """Test that two off-graph points close to each other take the direct connection

    when direct haversine * node_addition_circuity is shorter than the network route.
    """
    origin = {"latitude": 30.001, "longitude": 160.001}
    dest = {"latitude": 30.002, "longitude": 160.001}

    # Off graph circuity 1.2, node_addition_circuity 2.0
    res = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="quadrant",
        destination_node_addition_type="quadrant",
        off_graph_circuity=1.2,
        node_addition_circuity=2.0,
    )
    assert len(res["coordinate_path"]) == 2
    expected_direct = haversine(
        [origin["latitude"], origin["longitude"]],
        [dest["latitude"], dest["longitude"]],
        circuity=1.2,
        units=marnet.geograph_units,
    )
    assert abs(res["length"] - expected_direct) < 1e-3


def test_geograph_kdclosest_circuity_handling(marnet):
    """Test that kdclosest does not undo node_addition_circuity and applies off_graph_circuity."""
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    # Query with off_graph_circuity=1.5 and node_addition_circuity=10.0
    res_kd = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="kdclosest",
        destination_node_addition_type="kdclosest",
        off_graph_circuity=1.5,
        node_addition_circuity=10.0,
        output_path=True,
    )

    # Compute expected length: graph path + entry with 1.5 + exit with 1.5
    snap_orig = marnet.geokdtree.closest_idx(point=[30.0, 160.0])
    snap_dest = marnet.geokdtree.closest_idx(point=[30.0, -160.0])
    graph_res = marnet.graph_object.dijkstra(snap_orig, snap_dest)
    entry_len = haversine(
        [30.0, 160.0],
        marnet.nodes[snap_orig],
        circuity=1.5,
        units=marnet.geograph_units,
    )
    exit_len = haversine(
        marnet.nodes[snap_dest],
        [30.0, -160.0],
        circuity=1.5,
        units=marnet.geograph_units,
    )
    expected_len = graph_res["length"] + entry_len + exit_len

    assert abs(res_kd["length"] - expected_len) < 1e-3


def test_geograph_custom_numeric_bounds(marnet):
    """Test custom numeric lat_lon_bounds with node_addition_type='all'."""
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    res = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="all",
        destination_node_addition_type="all",
        node_addition_lat_lon_bound=5,
    )
    assert res["length"] > 0
    assert len(res["coordinate_path"]) > 2


def test_geograph_cached_shortest_path_repeated_queries_with_multi_exit(
    marnet,
):
    """Test repeated cached_shortest_path queries with varying destination snapping."""
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest1 = {"latitude": 30.0, "longitude": -160.0}
    dest2 = {"latitude": 35.0, "longitude": -150.0}

    # First call: populates cache for origin node
    res1 = marnet.get_shortest_path(
        origin,
        dest1,
        algorithm_fn="cached_shortest_path",
        destination_node_addition_type="quadrant",
    )
    dijk1 = marnet.get_shortest_path(
        origin,
        dest1,
        algorithm_fn="dijkstra",
        destination_node_addition_type="quadrant",
    )
    assert abs(res1["length"] - dijk1["length"]) < 1e-3

    # Second call from same origin to different destination: reuses cached tree
    res2 = marnet.get_shortest_path(
        origin,
        dest2,
        algorithm_fn="cached_shortest_path",
        destination_node_addition_type="quadrant",
    )
    dijk2 = marnet.get_shortest_path(
        origin,
        dest2,
        algorithm_fn="dijkstra",
        destination_node_addition_type="quadrant",
    )
    assert abs(res2["length"] - dijk2["length"]) < 1e-3
