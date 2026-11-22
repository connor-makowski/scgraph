"""Tests of a multimodal network on a GeoGraph: its nodes, its edges, their
classes and its metrics."""

import math
import random
from array import array
from itertools import accumulate

import pytest

from scgraph import GeoGraph, PathNotFoundError, network_file
from scgraph.utils import haversine

# The network of these tests joins two towns on the equator, 0.7 degree of
# longitude apart. A line of the drawing is one edge each way, with its km.
#
#   8 TERMINAL ..1.. 3 STATION ====== 90 ====== 4 STATION ..1.. 9 TERMINAL
#         :                                                         :
#         2                                                         2
#         :                                                         :
#   0 WEST_TOWN ---- 40 ---- 1 JUNCTION ---- 40 ---- 2 EAST_TOWN ....
#          \                                         /   :
#           '------------------ 100 ----------------'    3
#                                                        :
#       6 OPEN_SEA ------- 200 ------- 5 COAST ..5.. 7 PORT
#
# The primary road through the junction is the shortest way between the towns:
# 80 km. The motorway is longer and faster: 100 km. The railway needs the two
# terminals: 2 + 1 + 90 + 1 + 2 = 96 km. The sea lane starts at the port of
# the east town.
#
# The nodes are listed mode by mode, as in a network file: (mode, latitude,
# longitude). The id of a node is its position. No edge is shorter than the
# straight line between its two nodes.
WEST_TOWN, JUNCTION, EAST_TOWN = 0, 1, 2
WEST_STATION, EAST_STATION = 3, 4
COAST, OPEN_SEA = 5, 6
PORT = 7
WEST_TERMINAL, EAST_TERMINAL = 8, 9
NODES = [
    ("road", 0.0, 0.0),
    ("road", 0.0, 0.35),
    ("road", 0.0, 0.7),
    ("rail", 0.02, 0.0),
    ("rail", 0.02, 0.7),
    ("sea", -0.065, 0.7),
    ("sea", -0.065, 2.45),
    ("port", -0.025, 0.7),
    ("rail_terminal", 0.015, 0.0),
    ("rail_terminal", 0.015, 0.7),
]
# The mode of the edges of each class. A hub joins a network by connectors.
CLASSES = {
    "primary": "road",
    "motorway": "road",
    "road_connector": "road",
    "rail_main": "rail",
    "rail_connector": "rail",
    "open_sea": "sea",
    "sea_connector": "sea",
}
# (a node, another node, km, class). A node lists its edges in this order.
TWO_WAY_EDGES = [
    (WEST_TOWN, JUNCTION, 40.0, "primary"),
    (JUNCTION, EAST_TOWN, 40.0, "primary"),
    (WEST_TOWN, EAST_TOWN, 100.0, "motorway"),
    (WEST_TOWN, WEST_TERMINAL, 2.0, "road_connector"),
    (WEST_TERMINAL, WEST_STATION, 1.0, "rail_connector"),
    (WEST_STATION, EAST_STATION, 90.0, "rail_main"),
    (EAST_STATION, EAST_TERMINAL, 1.0, "rail_connector"),
    (EAST_TERMINAL, EAST_TOWN, 2.0, "road_connector"),
    (EAST_TOWN, PORT, 3.0, "road_connector"),
    (PORT, COAST, 5.0, "sea_connector"),
    (COAST, OPEN_SEA, 200.0, "open_sea"),
]
# The class of each edge, by (origin, destination)
CLASS_OF_EACH_EDGE = {
    nodes: edge_class
    for a, b, _, edge_class in TWO_WAY_EDGES
    for nodes in ((a, b), (b, a))
}
KM_OF_EACH_EDGE = {
    nodes: km for a, b, km, _ in TWO_WAY_EDGES for nodes in ((a, b), (b, a))
}

# The tables of the metric `minutes`: the minutes that 1 km takes. A lorry
# drives at 40 km/h on a primary road, at 120 km/h on the motorway and at
# 30 km/h on the other roads, which are the connectors. A train runs at
# 240 km/h and a ship sails at 30 km/h. A lorry needs 4 minutes for 1 km of
# the straight line between a query point and its node. Each rate is exact in
# binary, so that an expected weight is exact.
MINUTES_PER_KM = {
    "road": 2.0,
    "primary": 1.5,
    "motorway": 0.5,
    "rail": 0.25,
    "sea": 2.0,
    "off_graph": 4.0,
}
# The rate of each class in these tables: the name of a class wins over the
# mode of its edges.
MINUTES_PER_KM_OF_EACH_CLASS = {
    "primary": 1.5,
    "motorway": 0.5,
    "road_connector": 2.0,
    "rail_main": 0.25,
    "rail_connector": 0.25,
    "open_sea": 2.0,
    "sea_connector": 2.0,
}
MINUTES_OF_EACH_EDGE = {
    nodes: MINUTES_PER_KM_OF_EACH_CLASS[edge_class] * KM_OF_EACH_EDGE[nodes]
    for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
}
# Between the two towns, the railway is the fastest route: 2 × 2 + 1 × 0.25 +
# 90 × 0.25 + 1 × 0.25 + 2 × 2 = 31 minutes, for 96 km. The motorway takes 50
# minutes, and the primary road, the shortest route, 120 minutes.
RAILWAY_PATH = [
    WEST_TOWN,
    WEST_TERMINAL,
    WEST_STATION,
    EAST_STATION,
    EAST_TERMINAL,
    EAST_TOWN,
]
# The two points of a query from the west to the east. Each point is on the
# equator, 0.1 degree of longitude beyond its town, which is its closest node.
# An access leg is 6371 km × 0.1 degree in radians = 11.12 km.
WEST_POINT = {"latitude": 0.0, "longitude": -0.1}
EAST_POINT = {"latitude": 0.0, "longitude": 0.8}
ACCESS_LEG_KM = 6371 * math.radians(0.1)


def _write_network(path, nodes, two_way_edges, classes):
    """Write the network file of `nodes` and `two_way_edges`, which have the
    form of NODES and TWO_WAY_EDGES. `classes` gives the mode of the edges of
    each class. A query point snaps to a road node by default."""
    # The edges of each node: (destination, km, row of the class)
    rows = [[] for _ in nodes]
    for a, b, km, edge_class in two_way_edges:
        rows[a].append((b, km, list(classes).index(edge_class)))
        rows[b].append((a, km, list(classes).index(edge_class)))
    heads, lengths, edge_classes = zip(*(edge for row in rows for edge in row))
    modes = list(dict.fromkeys(mode for mode, _, _ in nodes))
    arrays = {
        "offsets": array("i", accumulate(map(len, rows), initial=0)),
        "heads": array("i", heads),
        "weights_length": array("d", lengths),
        "edge_classes": array("B", edge_classes),
        "node_points": array("d", [x for _, *point in nodes for x in point]),
        "node_modes": array("B", [modes.index(mode) for mode, _, _ in nodes]),
    }
    metadata = {
        "metrics": [{"name": "length", "unit": "km"}],
        "modes": [{"name": name} for name in modes],
        "classes": [{"name": n, "mode": mode} for n, mode in classes.items()],
        "node_addition_modes": ["road"],
    }
    network_file.write(path, arrays, metadata)


@pytest.fixture(scope="module")
def network_path(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("network") / "two_towns.scgraph")
    _write_network(path, NODES, TWO_WAY_EDGES, CLASSES)
    return path


@pytest.fixture
def network(network_path):
    """The network of the two towns. A test may edit it: each test loads it."""
    return GeoGraph.load_from_scgraph(network_path)


@pytest.fixture
def loaded_network(network, tmp_path):
    """The network of the two towns, saved with the metric `minutes` and loaded
    again: the geograph has the weights of the metric, and not the tables that
    made them. The save lists the open sea before the coast: only these two
    nodes change their ids."""
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    path = str(tmp_path / "with_minutes.scgraph")
    network.save_as_scgraph(path)
    return GeoGraph.load_from_scgraph(path)


def _get_class_of_each_edge(geograph):
    return {
        (edge["origin_id"], edge["destination_id"]): edge["class"]
        for edge in geograph.get_edges()
    }


def _get_weight_of_each_edge(geograph, metric):
    return {
        (edge["origin_id"], edge["destination_id"]): edge["metrics"][metric]
        for edge in geograph.get_edges()
    }


def test_get_nodes_gives_the_nodes_of_one_mode(network):
    assert network.get_nodes(mode="port") == [
        {"node_id": PORT, "latitude": -0.025, "longitude": 0.7, "mode": "port"}
    ]


def test_get_nodes_gives_the_nodes_inside_a_bounding_box(network):
    # The box goes from the equator to 0.1 N and from 0.5 E to 1 E. The east
    # town is on its south side. The port is south of the equator.
    nodes = network.get_nodes(bbox=(0.0, 0.5, 0.1, 1.0))

    node_ids = [node["node_id"] for node in nodes]
    assert node_ids == [EAST_TOWN, EAST_STATION, EAST_TERMINAL]


def test_get_edges_gives_the_edges_that_leave_one_node(network):
    assert network.get_edges(origin_id=JUNCTION) == [
        {
            "origin_id": JUNCTION,
            "destination_id": destination_id,
            "length": 40.0,
            "class": "primary",
            "mode": "road",
            "metrics": {},
        }
        for destination_id in (WEST_TOWN, EAST_TOWN)
    ]


def test_get_edges_gives_the_edges_of_one_class(network):
    edges = network.get_edges(edge_class="motorway")

    nodes = [(edge["origin_id"], edge["destination_id"]) for edge in edges]
    assert nodes == [(WEST_TOWN, EAST_TOWN), (EAST_TOWN, WEST_TOWN)]


def test_get_path_edges_gives_the_edges_of_a_path_in_its_order(network):
    # From the west town to the east station, by the railway
    path = [WEST_TOWN, WEST_TERMINAL, WEST_STATION, EAST_STATION]

    edges = network.get_path_edges(path)

    assert [
        (edge["class"], edge["mode"], edge["length"]) for edge in edges
    ] == [
        ("road_connector", "road", 2.0),
        ("rail_connector", "rail", 1.0),
        ("rail_main", "rail", 90.0),
    ]


# The network has no mode `air`, no class `canal`, no node 10 and no edge from
# the junction to the port.
@pytest.mark.parametrize(
    "method, argument",
    [
        ("get_nodes", {"mode": "air"}),
        ("get_edges", {"edge_class": "canal"}),
        ("get_edges", {"origin_id": 10}),
        ("get_path_edges", {"path": [WEST_TOWN, JUNCTION, PORT]}),
        ("get_path_edges", {"path": [10, WEST_TOWN]}),
    ],
)
def test_a_read_of_what_the_network_lacks_is_refused(network, method, argument):
    with pytest.raises(ValueError):
        getattr(network, method)(**argument)


def test_a_geograph_made_from_a_graph_has_edges_without_a_class():
    geograph = GeoGraph(graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]])

    assert _get_class_of_each_edge(geograph) == {(0, 1): None}


# Each call adds an edge both ways between the west town and the port.
ADDITIONS_OF_AN_EDGE = [
    ("add_edge", (WEST_TOWN, PORT, 85.0, True)),
    ("add_haversine_edge", (WEST_TOWN, PORT)),
    (
        "add_coord_edge",
        (
            {"latitude": 0.0, "longitude": 0.0},
            {"latitude": -0.025, "longitude": 0.7},
        ),
    ),
]


@pytest.mark.parametrize("method, arguments", ADDITIONS_OF_AN_EDGE)
def test_an_added_edge_has_its_class_and_the_other_edges_keep_theirs(
    network, method, arguments
):
    getattr(network, method)(*arguments, edge_class="primary")

    assert _get_class_of_each_edge(network) == {
        **CLASS_OF_EACH_EDGE,
        (WEST_TOWN, PORT): "primary",
        (PORT, WEST_TOWN): "primary",
    }


def test_a_node_added_with_a_class_gives_this_class_to_its_edges(network):
    # The west town is the closest node: 0.01 degree north of the new node.
    node_id = network.add_coord_node(
        {"latitude": -0.01, "longitude": 0.0},
        node_addition_type="closest",
        edge_class="road_connector",
    )

    assert _get_class_of_each_edge(network) == {
        **CLASS_OF_EACH_EDGE,
        (node_id, WEST_TOWN): "road_connector",
        (WEST_TOWN, node_id): "road_connector",
    }


def test_an_edit_made_on_the_graph_object_keeps_the_classes_lined_up(network):
    # The motorway is the second edge of each town: the edges after it move.
    network.graph_object.remove_edge(WEST_TOWN, EAST_TOWN, symmetric=True)

    assert _get_class_of_each_edge(network) == {
        nodes: edge_class
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
        if edge_class != "motorway"
    }


def test_a_removed_node_leaves_the_classes_of_the_other_edges(network):
    # The last node is the east terminal.
    network.remove_node()

    assert _get_class_of_each_edge(network) == {
        nodes: edge_class
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
        if EAST_TERMINAL not in nodes
    }


# A ferry line of 30 km, one degree north of the two towns. Its class is not a
# class of their network.
FERRY_NODES = [("road", 1.0, 0.0), ("road", 1.0, 0.3)]
FERRY_EDGES = [(0, 1, 30.0, "ferry")]


def test_a_merge_keeps_the_classes_of_both_geographs(network, tmp_path):
    ferry_path = str(tmp_path / "ferry.scgraph")
    _write_network(ferry_path, FERRY_NODES, FERRY_EDGES, {"ferry": "road"})
    ferry = GeoGraph.load_from_scgraph(ferry_path)

    # The connection node is the node 10. It joins the closest node of each
    # geograph: the west station and the first node of the ferry. The two
    # nodes of the ferry become the nodes 11 and 12.
    network.merge_with_other_geograph(ferry, connection_nodes=[[0.5, 0.0]])

    assert _get_class_of_each_edge(network) == {
        **CLASS_OF_EACH_EDGE,
        (10, WEST_STATION): None,
        (WEST_STATION, 10): None,
        (10, 11): None,
        (11, 10): None,
        (11, 12): "ferry",
        (12, 11): "ferry",
    }


def test_a_save_keeps_the_default_node_addition_modes(network, tmp_path):
    saved_path = str(tmp_path / "saved.scgraph")

    network.save_as_scgraph(saved_path)

    saved = GeoGraph.load_from_scgraph(saved_path)
    assert saved.default_node_addition_modes == ["road"]


def test_tables_give_each_edge_the_rate_of_its_class_times_its_km(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    assert _get_weight_of_each_edge(network, "minutes") == MINUTES_OF_EACH_EDGE


# A train waits at a rail terminal. One number is the wait on the way into
# the terminal and on the way out. A pair is (into the hub, out of the hub).
@pytest.mark.parametrize(
    "wait, minutes_into_the_hub, minutes_out_of_the_hub",
    [(15.0, 15.0, 15.0), ((10.0, 20.0), 10.0, 20.0)],
)
def test_an_edge_pays_the_weight_of_a_hub_that_it_enters_or_leaves(
    network, wait, minutes_into_the_hub, minutes_out_of_the_hub
):
    network.create_metric(
        "minutes",
        per_km=MINUTES_PER_KM,
        at_hub={"rail_terminal": {"rail": wait}},
    )

    # The rail connector of 1 km between the west station and its terminal
    # takes 0.25 minute. The road connector of 2 km between the terminal and
    # the town takes 4 minutes: the table names no class of the mode `road`.
    weights = _get_weight_of_each_edge(network, "minutes")
    assert (
        weights[WEST_STATION, WEST_TERMINAL],
        weights[WEST_TERMINAL, WEST_STATION],
        weights[WEST_TERMINAL, WEST_TOWN],
    ) == (0.25 + minutes_into_the_hub, 0.25 + minutes_out_of_the_hub, 4.0)


def _get_toll(edge):
    """A toll of 7 on the motorway, and 0.25 for 1 km of access leg."""
    if edge["mode"] == "off_graph":
        return 0.25 * edge["length"]
    return 7.0 if edge["class"] == "motorway" else 0.0


def test_a_function_gives_its_result_to_each_edge(network):
    network.create_metric("toll", edge_weight_fn=_get_toll)

    assert _get_weight_of_each_edge(network, "toll") == {
        nodes: 7.0 if edge_class == "motorway" else 0.0
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
    }


def test_edge_weights_set_the_weight_of_an_edge_and_none_closes_it(network):
    network.create_metric(
        "minutes",
        per_km=MINUTES_PER_KM,
        edge_weights={
            (WEST_TOWN, EAST_TOWN): 75.0,
            (EAST_TOWN, WEST_TOWN): None,
        },
    )

    assert _get_weight_of_each_edge(network, "minutes") == {
        **MINUTES_OF_EACH_EDGE,
        (WEST_TOWN, EAST_TOWN): 75.0,
        (EAST_TOWN, WEST_TOWN): math.inf,
    }


def test_metrics_lists_the_row_of_each_metric_after_the_length(network):
    network.create_metric(
        "minutes", per_km=3.0, unit="min", description="Three minutes per km."
    )
    network.create_metric("cost", weighted_sum_of={"minutes": 2, "length": 0.5})
    network.create_metric("toll", edge_weight_fn=_get_toll)

    # `off_graph_per_km` is the weight of 1 km of access leg. For the cost, it
    # is 2 × 3 minutes + 0.5 × 1 km. A metric without a description gets the
    # text of its call.
    minutes, cost, toll = (
        {"unit": "min", "description": "Three minutes per km."},
        "create_metric(weighted_sum_of={'minutes': 2, 'length': 0.5})",
        "create_metric(edge_weight_fn=_get_toll)",
    )
    assert network.metrics == [
        {"name": "length", "unit": "km"},
        {"name": "minutes", **minutes, "off_graph_per_km": 3.0},
        {"name": "cost", "description": cost, "off_graph_per_km": 6.5},
        {"name": "toll", "description": toll, "off_graph_per_km": 0.25},
    ]


def _get_cost(edge):
    """The cost of an edge, or of 1 km of access leg: 2 for each of its
    minutes, and 0.5 for each of its km."""
    return 2 * edge["metrics"]["minutes"] + 0.5 * edge["length"]


# The metric `cost` uses the metric `minutes`: as a weighted sum, then as a
# function that reads the minutes of each edge.
@pytest.mark.parametrize(
    "cost",
    [
        {"weighted_sum_of": {"minutes": 2, "length": 0.5}},
        {"edge_weight_fn": _get_cost},
    ],
    ids=["a weighted sum", "a function"],
)
def test_a_metric_that_uses_another_follows_it_when_it_is_created_again(
    network, cost
):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    network.create_metric("cost", **cost)
    network.create_metric("fare", weighted_sum_of={"cost": 3})

    network.create_metric("minutes", per_km=1.0)

    # At 1 minute per km, the cost of an edge is 2 × 1 + 0.5 = 2.5 times its
    # km. The fare is 3 times the cost.
    assert _get_weight_of_each_edge(network, "fare") == {
        nodes: 7.5 * km for nodes, km in KM_OF_EACH_EDGE.items()
    }


def test_a_geograph_without_classes_takes_one_rate_for_every_edge():
    geograph = GeoGraph(graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]])

    geograph.create_metric("minutes", per_km=2.0)

    assert _get_weight_of_each_edge(geograph, "minutes") == {(0, 1): 5.0}


# Each call names something that the network lacks, or leaves out a rate that
# the network needs: the call, and the name that the error gives. The network
# has no class and no mode `canal`, no node of a mode `airport`, and no edge
# from the junction to the port.
@pytest.mark.parametrize(
    "arguments, cause",
    [
        ({"per_km": {"road": 2.0, "rail": 0.25, "sea": 2.0}}, "off_graph"),
        ({"per_km": {"road": 2.0, "rail": 0.25, "off_graph": 4.0}}, "open_sea"),
        ({"per_km": {**MINUTES_PER_KM, "canal": 2.0}}, "canal"),
        ({"per_km": 2.0, "at_hub": {"airport": {"road": 30.0}}}, "airport"),
        ({"per_km": 2.0, "at_hub": {"port": {"canal": 30.0}}}, "canal"),
        ({"per_km": 2.0, "at_hub": {"port": {"sea": None}}}, "None"),
        ({"per_km": 2.0, "edge_weights": {(1, 7): 5.0}}, "node 1 to node 7"),
    ],
)
def test_a_metric_that_does_not_fit_the_network_is_refused(
    network, arguments, cause
):
    with pytest.raises(ValueError, match=cause):
        network.create_metric("minutes", **arguments)


def test_a_rate_per_km_is_refused_on_a_geograph_in_miles():
    geograph = GeoGraph(
        graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]], geograph_units="mi"
    )

    with pytest.raises(ValueError, match="km"):
        geograph.create_metric("minutes", per_km=2.0)


# `length` is the metric of the lengths. A name has small letters, digits and
# `_`, and starts with a letter.
@pytest.mark.parametrize("name", ["length", "Minutes", "2nd_class"])
def test_a_metric_with_a_name_that_is_not_allowed_is_refused(network, name):
    with pytest.raises(ValueError, match=name):
        network.create_metric(name, per_km=2.0)


# A call gives one of `per_km`, `weighted_sum_of` and `edge_weight_fn`, and
# `at_hub` goes with `per_km`.
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"per_km": 2.0, "weighted_sum_of": {"length": 2}},
        {"weighted_sum_of": {"length": 2}, "at_hub": {"port": {"sea": 30.0}}},
    ],
)
def test_a_call_without_exactly_one_way_to_compute_is_refused(
    network, arguments
):
    with pytest.raises(ValueError):
        network.create_metric("minutes", **arguments)


# The geograph has the metric `minutes` and its sum `cost`. Each call asks
# for a sum of a metric that does not exist, of a metric times zero, of
# itself, or of a sum that uses it.
@pytest.mark.parametrize(
    "name, weighted_sum_of",
    [
        ("fare", {"speed": 2}),
        ("fare", {"minutes": 0}),
        ("cost", {"cost": 2}),
        ("minutes", {"cost": 2}),
    ],
)
def test_a_sum_that_cannot_be_computed_is_refused(
    network, name, weighted_sum_of
):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    network.create_metric("cost", weighted_sum_of={"minutes": 2})

    with pytest.raises(ValueError):
        network.create_metric(name, weighted_sum_of=weighted_sum_of)


def _get_negative_toll(edge):
    return -7.0 if edge["class"] == "motorway" else 0.0


# Each call gives a weight below zero or not a number: to every edge, to the
# motorway, to the edge from the junction to the east town. The error names
# the first such edge.
@pytest.mark.parametrize(
    "arguments, edge",
    [
        ({"per_km": -2.0}, "node 0 to node 1"),
        ({"edge_weight_fn": _get_negative_toll}, "node 0 to node 2"),
        (
            {"per_km": 2.0, "edge_weights": {(1, 2): math.nan}},
            "node 1 to node 2",
        ),
    ],
)
def test_a_weight_below_zero_or_not_a_number_is_refused_with_its_edge(
    network, arguments, edge
):
    with pytest.raises(ValueError, match=edge):
        network.create_metric("toll", **arguments)


def test_a_function_that_closes_the_access_legs_is_refused(network):
    with pytest.raises(ValueError, match="access leg"):
        network.create_metric("toll", edge_weight_fn=lambda edge: None)


def test_a_route_by_a_metric_has_the_smallest_total_of_this_metric(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    network.create_metric("cost", weighted_sum_of={"minutes": 2, "length": 0.5})

    route = network.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        off_graph_circuity=2,
        output_path=True,
    )

    # The railway: 31 minutes and 96 km, so a cost of 2 × 31 + 0.5 × 96 = 110.
    # An access leg counts its km times the off-graph circuity, and not times
    # the node addition circuity of the search, which is 4. 1 km of it takes
    # 4 minutes and costs 2 × 4 + 0.5 = 8.5.
    access_km = 2 * ACCESS_LEG_KM * 2
    assert route["path"] == RAILWAY_PATH
    assert route["length"] == pytest.approx(96 + access_km)
    assert route["metrics"] == {
        "minutes": pytest.approx(31 + access_km * 4.0),
        "cost": pytest.approx(110 + access_km * 8.5),
    }


def test_access_legs_that_weigh_nothing_do_not_make_a_route_direct(network):
    network.create_metric(
        "minutes", per_km={**MINUTES_PER_KM, "off_graph": 0.0}
    )

    route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", output_path=True
    )

    assert route["path"] == RAILWAY_PATH


SEARCHES = (
    "dijkstra bidirectional_dijkstra dijkstra_buckets bidirectional_buckets "
    "dijkstra_negative a_star bellman_ford bmssp cached_shortest_path "
    "contraction_hierarchy tnr"
).split()


@pytest.mark.parametrize("algorithm_fn", SEARCHES)
def test_every_search_finds_the_best_route_by_a_metric(network, algorithm_fn):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", algorithm_fn=algorithm_fn
    )

    assert route["metrics"]["minutes"] == pytest.approx(
        31 + 2 * ACCESS_LEG_KM * 4.0
    )


def test_a_star_with_the_great_circle_bound_finds_the_best_route(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    # The motorway reaches the east town in one edge and 50 minutes. The
    # railway, the best route, has five edges. The bound of a node is its
    # great-circle km to the destination times 0.25, the fewest minutes that
    # 1 km of an edge takes. A bound in km would be above the 31 minutes of
    # the railway, and the search would stop at the motorway.
    route = network.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": network.haversine},
        output_path=True,
    )

    assert route["path"] == RAILWAY_PATH


def test_length_only_with_a_metric_gives_the_total_of_this_metric_alone(
    network,
):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    result = network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", length_only=True
    )

    assert result == {
        "metrics": {"minutes": pytest.approx(31 + 2 * ACCESS_LEG_KM * 4.0)}
    }


def test_get_path_weight_gives_the_total_of_a_metric_along_a_route(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    shortest_route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, output_path=True
    )

    minutes = network.get_path_weight(shortest_route, metric="minutes")

    # The shortest route takes the primary road: 80 km at 1.5 minutes per km.
    assert minutes == pytest.approx(120 + 2 * ACCESS_LEG_KM * 4.0)


# The geograph has no metric `speed`.
@pytest.mark.parametrize(
    "method, arguments",
    [
        ("get_shortest_path", (WEST_POINT, EAST_POINT)),
        ("get_path_weight", ({"path": [0], "coordinate_path": [[0, 0]]},)),
    ],
)
def test_a_query_by_a_metric_that_the_geograph_lacks_is_refused(
    network, method, arguments
):
    with pytest.raises(ValueError, match="speed"):
        getattr(network, method)(*arguments, metric="speed")


def test_a_route_by_a_metric_avoids_a_class_that_the_metric_closes(network):
    network.create_metric("minutes", per_km={**MINUTES_PER_KM, "rail": None})

    route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", output_path=True
    )

    # Without the railway, the motorway is the fastest route.
    assert route["path"] == [WEST_TOWN, EAST_TOWN]


def test_a_closed_class_closes_an_edge_of_zero_km(network):
    network.add_edge(WEST_TOWN, PORT, 0.0, edge_class="open_sea")

    network.create_metric("minutes", per_km={**MINUTES_PER_KM, "sea": None})

    # Infinity times 0 km is not a number: the edge weighs infinity.
    weights = _get_weight_of_each_edge(network, "minutes")
    assert weights[WEST_TOWN, PORT] == math.inf


def test_a_route_that_needs_a_closed_edge_is_not_found(network):
    network.create_metric("minutes", per_km={**MINUTES_PER_KM, "sea": None})

    # The destination snaps to the open sea node, which only sea lanes reach.
    with pytest.raises(PathNotFoundError):
        network.get_shortest_path(
            WEST_POINT,
            {"latitude": -0.065, "longitude": 2.5},
            metric="minutes",
            node_addition_modes=["road", "sea"],
        )


# Two points on the equator, each with a road node as its closest node. The
# first one is 0.01 degree west of the east town. Its closest rail node is the
# east station, 0.022 degree away. The second one is 0.05 degree west of the
# junction. Its closest rail node is the west station, 0.3 degree away: the
# east station is 0.4 degree away.
POINT_NEAR_THE_EAST_TOWN = {"latitude": 0.0, "longitude": 0.69}
POINT_NEAR_THE_JUNCTION = {"latitude": 0.0, "longitude": 0.3}


# The other tests snap with the default type, 'closest'.
@pytest.mark.parametrize("node_addition_type", ["quadrant", "all"])
def test_a_query_point_snaps_only_to_nodes_of_the_modes_of_the_query(
    network, node_addition_type
):
    route = network.get_shortest_path(
        POINT_NEAR_THE_EAST_TOWN,
        POINT_NEAR_THE_JUNCTION,
        node_addition_modes=["rail"],
        node_addition_type=node_addition_type,
        output_path=True,
    )

    # A route that may start at any node starts at the east town.
    path = route["path"]
    assert (path[0], path[-1]) == (EAST_STATION, WEST_STATION)


def test_a_query_point_snaps_to_the_modes_that_the_network_file_names(network):
    # The file names the mode `road` (`_write_network`). The point is 0.01
    # degree north of the east station and 0.03 degree north of the east town.
    route = network.get_shortest_path(
        WEST_POINT, {"latitude": 0.03, "longitude": 0.7}, output_path=True
    )

    assert route["path"][-1] == EAST_TOWN


def test_a_query_point_snaps_to_a_node_that_the_user_added(network):
    # The file names the mode `road` for the query points. The new node has
    # no mode of the file. It is at the origin of the query, 0.1 degree west
    # of the west town.
    node_id = network.add_coord_node(WEST_POINT)

    route = network.get_shortest_path(WEST_POINT, EAST_POINT, output_path=True)

    assert route["path"][0] == node_id


def test_a_query_point_snaps_to_a_node_added_after_an_earlier_query(network):
    # This query builds the snapping index of the rail nodes.
    network.get_shortest_path(
        WEST_POINT, EAST_POINT, node_addition_modes=["rail"]
    )

    # The new rail node is at the origin of the next query.
    node_id = network.add_coord_node(WEST_POINT, mode="rail")

    route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, node_addition_modes=["rail"], output_path=True
    )
    assert route["path"][0] == node_id


def test_a_query_point_snaps_to_its_modes_among_nodes_in_any_order():
    # 2,000 nodes at random places, a road node and a rail node in turn. A
    # snapping index needs nearby nodes to follow each other: the geograph
    # sorts the rail nodes for theirs. Each node has an edge to the node 0 and
    # back, so that every route exists.
    rng = random.Random(62)
    nodes = [[rng.uniform(-10, 10), rng.uniform(-10, 10)] for _ in range(2000)]
    geograph = GeoGraph(
        graph=[{i: 1.0 for i in range(1, 2000)}]
        + [{0: 1.0} for _ in nodes[1:]],
        nodes=nodes,
        node_modes=[i % 2 for i in range(2000)],
        modes=[{"name": "road"}, {"name": "rail"}],
    )
    origin, destination = [-5.0, -5.0], [5.0, 5.0]

    route = geograph.get_shortest_path(
        {"latitude": origin[0], "longitude": origin[1]},
        {"latitude": destination[0], "longitude": destination[1]},
        node_addition_modes=["rail"],
        output_path=True,
    )

    # The rail nodes have the odd ids.
    assert [route["path"][0], route["path"][-1]] == [
        min(range(1, 2000, 2), key=lambda i: haversine(point, nodes[i]))
        for point in (origin, destination)
    ]


@pytest.fixture
def sea_network(network_path):
    """The sea lanes and the port of the network, read alone. The file names
    the mode `road` for the query points, and this geograph has no road node.
    """
    return GeoGraph.load_from_scgraph(network_path, modes=["sea", "port"])


def test_a_query_point_snaps_to_any_node_when_no_node_has_a_default_mode(
    sea_network,
):
    # The origin is 0.01 degree west of the port, and the destination is 0.05
    # degree east of the open sea node.
    route = sea_network.get_shortest_path(
        {"latitude": -0.025, "longitude": 0.69},
        {"latitude": -0.065, "longitude": 2.5},
    )

    # The points of the port, of the coast and of the open sea
    assert route["coordinate_path"][1:-1] == [
        [-0.025, 0.7],
        [-0.065, 0.7],
        [-0.065, 2.45],
    ]


# No node of the geograph has the mode `road`. Its file has no mode `canal`.
@pytest.mark.parametrize(
    "node_addition_modes", [["road"], ["sea", "canal"], []]
)
def test_a_query_refuses_modes_that_its_points_cannot_snap_to(
    sea_network, node_addition_modes
):
    with pytest.raises(ValueError, match="node_addition_modes"):
        sea_network.get_shortest_path(
            {"latitude": -0.025, "longitude": 0.69},
            {"latitude": -0.065, "longitude": 2.5},
            node_addition_modes=node_addition_modes,
        )


def test_a_query_refuses_modes_on_a_geograph_without_modes():
    geograph = GeoGraph(graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]])

    # The one mode of this geograph has no name: a query cannot name it.
    with pytest.raises(ValueError, match="node_addition_modes"):
        geograph.get_shortest_path(
            {"latitude": 0, "longitude": 0},
            {"latitude": 0, "longitude": 1},
            node_addition_modes=[None],
        )


def test_the_legs_of_a_route_are_its_parts_on_one_mode(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    route = network.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        output_units="m",
        output_legs=True,
    )

    # The fastest route: a road connector from the west town to its terminal,
    # the railway between the two terminals, and a road connector to the east
    # town. An access leg joins each point of the query to its town. The
    # lengths are in metres, the unit of the query.
    access_leg = ("off_graph", pytest.approx(1000 * ACCESS_LEG_KM), {})
    road_leg = ("road", 2000.0, {"road_connector": 2000.0})
    rail_leg = (
        "rail",
        92000.0,
        {"rail_connector": 2000.0, "rail_main": 90000.0},
    )
    assert [
        (leg["mode"], leg["length"], leg["class_lengths"])
        for leg in route["legs"]
    ] == [access_leg, road_leg, rail_leg, road_leg, access_leg]
    assert route["hubs"] == [
        {"node_id": WEST_TERMINAL, "mode": "rail_terminal"},
        {"node_id": EAST_TERMINAL, "mode": "rail_terminal"},
    ]


def test_the_legs_of_a_route_add_up_to_its_length_and_to_its_totals(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    network.create_metric("cost", weighted_sum_of={"minutes": 2, "length": 0.5})

    route = network.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        off_graph_circuity=2,
        output_legs=True,
    )

    legs = route["legs"]
    assert sum(leg["length"] for leg in legs) == pytest.approx(route["length"])
    assert {
        name: sum(leg["metrics"][name] for leg in legs)
        for name in ("minutes", "cost")
    } == pytest.approx(route["metrics"])


# Each destination gives a route without an edge, with its points. The first
# one is 0.05 degree east of the west town: both points of the query snap to
# this town. The second one is 0.01 degree from the origin: the straight line
# is shorter than the way to the town.
@pytest.mark.parametrize(
    "destination, coordinate_path",
    [
        ([0.0, 0.05], [[0.0, -0.1], [0.0, 0.0], [0.0, 0.05]]),
        ([0.0, -0.11], [[0.0, -0.1], [0.0, -0.11]]),
    ],
)
def test_a_route_without_an_edge_is_one_leg_off_the_graph(
    network, destination, coordinate_path
):
    route = network.get_shortest_path(
        WEST_POINT,
        {"latitude": destination[0], "longitude": destination[1]},
        output_legs=True,
    )

    assert route["legs"] == [
        {
            "mode": "off_graph",
            "length": pytest.approx(route["length"]),
            "class_lengths": {},
            "coordinate_path": coordinate_path,
        }
    ]


def test_the_edges_of_a_geograph_without_classes_make_one_leg_of_no_mode():
    geograph = GeoGraph(graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]])

    route = geograph.get_shortest_path(
        {"latitude": 0, "longitude": -0.1},
        {"latitude": 0, "longitude": 1.1},
        output_legs=True,
    )

    assert [(leg["mode"], leg["class_lengths"]) for leg in route["legs"]] == [
        ("off_graph", {}),
        (None, {None: 2.5}),
        ("off_graph", {}),
    ]


def test_the_coordinate_paths_of_the_legs_follow_the_one_of_the_route():
    # A road of two edges. The first edge has a bend: one point of its shape.
    road_with_a_bend = GeoGraph(
        graph=[{1: 60.0}, {2: 60.0}, {}],
        nodes=[[0.0, 0.0], [0.0, 0.5], [0.0, 1.0]],
        intermediate_nodes=[{1: [[0.1, 0.25]]}, {}, {}],
    )

    route = road_with_a_bend.get_shortest_path(
        {"latitude": 0.0, "longitude": -0.1},
        {"latitude": 0.0, "longitude": 1.1},
        output_coordinate_path="list_of_dicts",
        output_legs=True,
    )

    # A leg starts at the point where the leg before it ends.
    access_leg, road_leg, last_access_leg = (
        leg["coordinate_path"] for leg in route["legs"]
    )
    assert (
        access_leg + road_leg[1:] + last_access_leg[1:]
        == route["coordinate_path"]
    )


def test_distance_matrix_by_a_metric_gives_the_total_of_this_metric(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    points = [WEST_POINT, EAST_POINT]

    matrix = network.distance_matrix(points, metric="minutes")

    assert matrix == [
        pytest.approx(
            [
                network.get_shortest_path(
                    origin, destination, metric="minutes"
                )["metrics"]["minutes"]
                for destination in points
            ]
        )
        for origin in points
    ]


# The lengths of the fastest routes, and the minutes of the shortest routes
@pytest.mark.parametrize(
    "metric, output_metric", [("minutes", "length"), ("length", "minutes")]
)
def test_distance_matrix_gives_the_totals_of_another_metric_than_its_routes(
    network, metric, output_metric
):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    points = [WEST_POINT, EAST_POINT]

    matrix = network.distance_matrix(
        points, metric=metric, output_metric=output_metric
    )

    routes = [
        [
            network.get_shortest_path(origin, destination, metric=metric)
            for destination in points
        ]
        for origin in points
    ]
    assert matrix == [
        pytest.approx(
            [
                {"length": route["length"], **route["metrics"]}[output_metric]
                for route in row
            ]
        )
        for row in routes
    ]


def test_distance_matrix_by_an_output_metric_follows_an_edit_of_the_network(
    network,
):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    points = [WEST_POINT, EAST_POINT]

    # The west town lists the new road after its other edges. So each edge of
    # the nodes after the west town gets a new index.
    network.add_edge(
        WEST_TOWN, PORT, 80.0, symmetric=True, edge_class="primary"
    )

    matrix = network.distance_matrix(points, output_metric="minutes")

    # The shortest route between the two towns is still the primary road
    # through the junction: the new road ends at the port, 3 km further.
    assert matrix == [
        pytest.approx(
            [
                network.get_shortest_path(origin, destination)["metrics"][
                    "minutes"
                ]
                for destination in points
            ]
        )
        for origin in points
    ]


def test_distance_matrix_snaps_its_points_to_the_modes_of_the_call(network):
    matrix = network.distance_matrix(
        [WEST_POINT, EAST_POINT], node_addition_modes=["rail"]
    )

    # Each point snaps to the station of its town, 0.02 degree north of the
    # equator and 0.1 degree of longitude away. The shortest route between the
    # two stations takes the primary road: 1 + 2 + 80 + 2 + 1 = 86 km.
    access_leg_km = 6371 * math.radians(math.hypot(0.02, 0.1))
    km = pytest.approx(86 + 2 * access_leg_km)
    assert matrix == [[0.0, km], [km, 0.0]]


def test_a_removed_metric_leaves_the_results_of_the_geograph(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    network.remove_metric("minutes")

    assert "metrics" not in network.get_shortest_path(WEST_POINT, EAST_POINT)


# The sum `cost` uses the metric `minutes`. The geograph has no metric `speed`.
@pytest.mark.parametrize("name", ["minutes", "speed"])
def test_remove_metric_refuses_a_metric_that_it_cannot_remove(network, name):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    network.create_metric("cost", weighted_sum_of={"minutes": 2})

    with pytest.raises(ValueError, match=name):
        network.remove_metric(name)


def test_reduce_reduces_the_graph_of_each_metric_and_keeps_its_routes(network):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)
    network.create_metric("cost", weighted_sum_of={"minutes": 2, "length": 0.5})
    # This query builds the graph of the minutes. The graph of the cost is
    # built after the reduction.
    route = network.get_shortest_path(WEST_POINT, EAST_POINT, metric="minutes")

    network.reduce()

    assert network.get_graph_object("minutes").reduced_graph is not None
    assert network.get_graph_object("cost").reduced_graph is not None
    assert (
        network.get_shortest_path(WEST_POINT, EAST_POINT, metric="minutes")
        == route
    )


def test_a_saved_and_loaded_geograph_keeps_its_metrics_and_their_routes(
    network, loaded_network
):
    # The fixture created the metric `minutes` on `network` and saved it.
    assert loaded_network.metrics == network.metrics
    assert loaded_network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes"
    ) == network.get_shortest_path(WEST_POINT, EAST_POINT, metric="minutes")


def test_an_edit_computes_again_a_metric_that_create_metric_made(network):
    network.create_metric(
        "minutes",
        per_km=MINUTES_PER_KM,
        edge_weights={
            (WEST_TOWN, EAST_TOWN): 75.0,
            (EAST_TOWN, WEST_TOWN): 75.0,
        },
    )

    network.remove_edge(WEST_TOWN, EAST_TOWN, symmetric=True)
    network.add_edge(
        WEST_TOWN, PORT, 80.0, symmetric=True, edge_class="primary"
    )

    # The new primary road of 80 km takes 120 minutes. The motorway is gone,
    # with the weights that `edge_weights` gave it.
    assert _get_weight_of_each_edge(network, "minutes") == {
        **{
            nodes: minutes
            for nodes, minutes in MINUTES_OF_EACH_EDGE.items()
            if CLASS_OF_EACH_EDGE[nodes] != "motorway"
        },
        (WEST_TOWN, PORT): 120.0,
        (PORT, WEST_TOWN): 120.0,
    }


@pytest.mark.parametrize("method, arguments", ADDITIONS_OF_AN_EDGE)
def test_an_added_edge_takes_its_weight_in_a_metric_that_was_read(
    loaded_network, method, arguments
):
    getattr(loaded_network, method)(*arguments, metrics={"minutes": 90.0})

    # The geograph cannot compute the minutes of the new edge. The edges that
    # were there keep their minutes: the new edge of the west town moves the
    # edges of every node after it.
    weights = _get_weight_of_each_edge(loaded_network, "minutes")
    assert (
        weights[WEST_TOWN, PORT],
        weights[PORT, WEST_TOWN],
        weights[WEST_STATION, EAST_STATION],
    ) == (90.0, 90.0, 22.5)


def test_a_node_added_with_a_weight_gives_this_weight_to_its_edges(
    loaded_network,
):
    # The west town is the closest node: 0.01 degree north of the new node.
    node_id = loaded_network.add_coord_node(
        {"latitude": -0.01, "longitude": 0.0},
        node_addition_type="closest",
        metrics={"minutes": 3.0},
    )

    weights = _get_weight_of_each_edge(loaded_network, "minutes")
    assert (weights[node_id, WEST_TOWN], weights[WEST_TOWN, node_id]) == (3, 3)


def test_an_edge_added_without_a_weight_is_closed_in_a_read_metric(
    loaded_network,
):
    loaded_network.add_edge(WEST_TOWN, PORT, 85.0)
    # An edit made on the graph object gives no weight to its edge.
    loaded_network.graph_object.add_edge(PORT, WEST_TOWN, 85.0)

    weights = _get_weight_of_each_edge(loaded_network, "minutes")
    assert (weights[WEST_TOWN, PORT], weights[PORT, WEST_TOWN]) == (
        math.inf,
        math.inf,
    )


def test_an_added_edge_with_a_weight_below_zero_is_refused(loaded_network):
    with pytest.raises(ValueError, match="minutes"):
        loaded_network.add_edge(WEST_TOWN, PORT, 85.0, metrics={"minutes": -1})


def test_a_route_by_a_read_metric_follows_an_edit_of_the_network(
    loaded_network,
):
    # This query builds the graph of the minutes, with the railway.
    loaded_network.get_shortest_path(WEST_POINT, EAST_POINT, metric="minutes")

    loaded_network.remove_edge(WEST_STATION, EAST_STATION, symmetric=True)

    # Without the railway, the motorway is the fastest route.
    route = loaded_network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", output_path=True
    )
    assert route["path"] == [WEST_TOWN, EAST_TOWN]


# An `add_` call gives a weight only in a metric that the geograph read from a
# file. It computes the metric `minutes` itself, and it has no metric `speed`.
@pytest.mark.parametrize("name", ["minutes", "speed"])
def test_an_added_edge_takes_no_weight_in_a_metric_that_was_not_read(
    network, name
):
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    with pytest.raises(ValueError, match=name):
        network.add_edge(WEST_TOWN, PORT, 85.0, metrics={name: 90.0})


def test_a_merge_removes_the_metrics_other_than_the_length(network, tmp_path):
    ferry_path = str(tmp_path / "ferry.scgraph")
    _write_network(ferry_path, FERRY_NODES, FERRY_EDGES, {"ferry": "road"})
    ferry = GeoGraph.load_from_scgraph(ferry_path)
    network.create_metric("minutes", per_km=MINUTES_PER_KM)

    network.merge_with_other_geograph(ferry, connection_nodes=[[0.5, 0.0]])

    assert network.metrics == [{"name": "length", "unit": "km"}]
