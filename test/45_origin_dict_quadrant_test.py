import pytest
from scgraph.graph import Graph as PyGraph
from scgraph.contraction_hierarchies import CHGraph as PyCHGraph
from scgraph.transit_node_routing import TNRGraph as PyTNRGraph
from scgraph.geograph import GeoGraph
from helpers import assert_result

try:
    from scgraph.cpp import (
        Graph as CppGraph,
        CHGraph as CppCHGraph,
        TNRGraph as CppTNRGraph,
    )

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

GRAPH_CLASSES = [PyGraph] + ([CppGraph] if HAS_CPP else [])
CH_CLASSES = [PyCHGraph] + ([CppCHGraph] if HAS_CPP else [])
TNR_CLASSES = [PyTNRGraph] + ([CppTNRGraph] if HAS_CPP else [])


# Simple test graph:
# 0 --(2)--> 1 --(3)--> 2 --(4)--> 3
# 4 --(1)--> 1
# 2 --(2)--> 5
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
def test_all_algorithms_with_origin_dict(sample_graph, GraphClass):
    g = GraphClass(sample_graph)

    # Origin 0 with dist 10, Origin 4 with dist 5 -> path from 4: 5 + 1 + 3 + 4 = 13 (vs from 0: 10 + 2 + 3 + 4 = 19)
    origin_dict = {0: 10.0, 4: 5.0}
    destination_dict = {3: 0.0}

    alg_names = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "a_star",
        "bellman_ford",
        "bmssp",
    ]

    for name in alg_names:
        fn = getattr(g, name)
        res = fn(origin_id=origin_dict, destination_id=destination_dict)
        assert res["path"] == [4, 1, 2, 3], f"{name} failed path check"
        assert abs(res["length"] - 13.0) < 1e-6, f"{name} failed length check"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_all_algorithms_with_destination_dict(sample_graph, GraphClass):
    g = GraphClass(sample_graph)

    # Destination 3 with exit cost 10, Destination 5 with exit cost 1 -> from 0: to 3 = 2+3+4+10=19, to 5 = 2+3+2+1=8
    origin_dict = {0: 0.0}
    destination_dict = {3: 10.0, 5: 1.0}

    alg_names = [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "a_star",
        "bellman_ford",
        "bmssp",
    ]

    for name in alg_names:
        fn = getattr(g, name)
        res = fn(origin_id=origin_dict, destination_id=destination_dict)
        assert res["path"] == [0, 1, 2, 5], f"{name} failed path check"
        assert abs(res["length"] - 8.0) < 1e-6, f"{name} failed length check"


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_tree_algorithms_with_dicts(sample_graph, GraphClass):
    g = GraphClass(sample_graph)
    tree = g.get_shortest_path_tree(origin_id={0: 10.0, 4: 5.0})
    res = g.get_tree_path(
        origin_id={0: 10.0, 4: 5.0},
        destination_id={3: 10.0, 5: 1.0},
        tree_data=tree,
    )
    assert res["path"] == [4, 1, 2, 5]
    assert abs(res["length"] - 12.0) < 1e-6


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_graph_reducer_with_origin_destination_dicts(GraphClass):
    # 0 -> 1 -> 2 -> 3 (chain: 1, 2)
    raw = [
        {1: 2.0},
        {2: 3.0},
        {3: 4.0},
        {},
    ]
    g = GraphClass(raw)
    g.reduce(iterations=1)
    assert g.is_same_chain({1: 0.0}, {2: 0.0}) is True
    assert g.is_same_chain({0: 0.0}, {3: 0.0}) is False

    # Route through reduced graph with dict
    res = g.dijkstra(origin_id={1: 5.0}, destination_id={3: 2.0})
    assert res["path"] == [1, 2, 3]
    assert abs(res["length"] - 14.0) < 1e-6  # 5 + 3 + 4 + 2 = 14


@pytest.mark.parametrize("CHClass", CH_CLASSES)
def test_contraction_hierarchies_with_dicts(sample_graph, CHClass):
    ch = CHClass(sample_graph)
    res = ch.search(
        origin_id={0: 10.0, 4: 5.0}, destination_id={3: 10.0, 5: 1.0}
    )
    assert res["path"] == [4, 1, 2, 5]
    assert abs(res["length"] - 12.0) < 1e-6

    res_len = ch.search(
        origin_id={0: 10.0, 4: 5.0},
        destination_id={3: 10.0, 5: 1.0},
        length_only=True,
    )
    assert res_len["path"] == []
    assert abs(res_len["length"] - 12.0) < 1e-6


@pytest.mark.parametrize("TNRClass", TNR_CLASSES)
def test_transit_node_routing_with_dicts(sample_graph, TNRClass):
    tnr = TNRClass(sample_graph, num_transit_nodes=2)
    res = tnr.search(
        origin_id={0: 10.0, 4: 5.0}, destination_id={3: 10.0, 5: 1.0}
    )
    assert res["path"] == [4, 1, 2, 5]
    assert abs(res["length"] - 12.0) < 1e-6

    res_len = tnr.search(
        origin_id={0: 10.0, 4: 5.0},
        destination_id={3: 10.0, 5: 1.0},
        length_only=True,
    )
    assert res_len["path"] == []
    assert abs(res_len["length"] - 12.0) < 1e-6


def test_geograph_static_graph_immutability(marnet):
    """Test that kdquadrant, quadrant, kdclosest, and closest do not mutate the underlying graph."""
    orig_len = len(marnet.graph_object.graph)
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    for add_type in ["kdquadrant", "quadrant", "kdclosest", "closest"]:
        res = marnet.get_shortest_path(
            origin,
            dest,
            node_addition_type=add_type,
            destination_node_addition_type=add_type,
            output_path=True,
        )
        assert (
            len(marnet.graph_object.graph) == orig_len
        ), f"Graph mutated with {add_type}!"
        assert "path" in res
        assert "coordinate_path" in res
        assert res["length"] > 0


def test_geograph_quadrant_aliases(marnet):
    """Test that 'closest' is an alias for 'kdclosest' and 'quadrant' is an alias for 'kdquadrant'."""
    origin = {"latitude": 30.0, "longitude": 160.0}
    dest = {"latitude": 30.0, "longitude": -160.0}

    res_kdclosest = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="kdclosest",
        destination_node_addition_type="kdclosest",
    )
    res_closest = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )
    assert abs(res_kdclosest["length"] - res_closest["length"]) < 1e-5
    assert res_kdclosest["coordinate_path"] == res_closest["coordinate_path"]

    res_kdquadrant = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
    )
    res_quadrant = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="quadrant",
        destination_node_addition_type="quadrant",
    )
    assert abs(res_kdquadrant["length"] - res_quadrant["length"]) < 1e-5
    assert res_kdquadrant["coordinate_path"] == res_quadrant["coordinate_path"]


def test_geograph_quadrant_all_algorithms(us_freeway):
    """Test GeoGraph with kdquadrant across different algorithms."""
    origin = {"latitude": 42.36, "longitude": -71.06}  # Boston
    dest = {"latitude": 40.71, "longitude": -74.01}  # NYC

    us_freeway.graph_object.create_contraction_hierarchy()
    us_freeway.graph_object.create_tnr_hierarchy(num_transit_nodes=100)

    dijkstra_res = us_freeway.get_shortest_path(
        origin,
        dest,
        algorithm_fn="dijkstra",
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
    )
    bidir_res = us_freeway.get_shortest_path(
        origin,
        dest,
        algorithm_fn="bidirectional_dijkstra",
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
    )
    ch_res = us_freeway.get_shortest_path(
        origin,
        dest,
        algorithm_fn="contraction_hierarchy",
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
    )
    tnr_res = us_freeway.get_shortest_path(
        origin,
        dest,
        algorithm_fn="tnr",
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
    )

    assert abs(dijkstra_res["length"] - bidir_res["length"]) < 1e-3
    assert abs(dijkstra_res["length"] - ch_res["length"]) < 1e-3
    assert abs(dijkstra_res["length"] - tnr_res["length"]) < 1e-3


def test_geograph_quadrant_circuity_adjustment(marnet):
    """Test that off_graph_circuity correctly adjusts the quadrant off-graph segments."""
    origin = {"latitude": 30.5, "longitude": 160.5}
    dest = {"latitude": 30.5, "longitude": -160.5}

    res_c1 = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
        node_addition_circuity=4.0,
        off_graph_circuity=1.0,
    )
    res_c2 = marnet.get_shortest_path(
        origin,
        dest,
        node_addition_type="kdquadrant",
        destination_node_addition_type="kdquadrant",
        node_addition_circuity=4.0,
        off_graph_circuity=2.0,
    )
    # Higher off_graph_circuity should yield greater total length
    assert res_c2["length"] > res_c1["length"]
