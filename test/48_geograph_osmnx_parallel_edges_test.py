import pytest
from types import SimpleNamespace
from scgraph import GeoGraph


class _OSMnxGraph:
    """A stand-in for the graph that OSMnx returns: osmnx is not a dependency.

    `places` maps the id of a node to its (longitude, latitude), which OSMnx
    names x and y. `edges` lists (origin id, destination id, edge data).
    """

    def __init__(self, places, edges):
        self._places, self._edges = places, edges
        # scgraph reads both `graph.nodes` and `graph.nodes(data=True)`.
        self.nodes = self

    def __iter__(self):
        return iter(self._places)

    def __call__(self, data=False):
        return [
            (node, {"x": x, "y": y}) for node, (x, y) in self._places.items()
        ]

    def edges(self, data=False):
        return self._edges


def _drawn_through(*points):
    """The geometry of an OSMnx edge: an object whose `coords` are the
    (longitude, latitude) points of the edge, its two nodes included."""
    return SimpleNamespace(coords=list(points))


# Two nodes on the equator, 0.01 degree of longitude apart: 1.112 km. OSMnx
# gives the length of an edge in meters, and scgraph stores kilometers.
WEST, EAST = 1, 2
PLACES = {WEST: (0.0, 0.0), EAST: (0.01, 0.0)}
# Two edges from WEST to EAST. The straight edge passes the point half way.
# The detour passes a point 0.01 degree north of it, and is longer.
STRAIGHT_EDGE = {
    "length": 1112,
    "geometry": _drawn_through((0.0, 0.0), (0.005, 0.0), (0.01, 0.0)),
}
DETOUR_EDGE = {
    "length": 3000,
    "geometry": _drawn_through((0.0, 0.0), (0.005, 0.01), (0.01, 0.0)),
}


# OSMnx gives no geometry to an edge that is a straight line.
SHORT_EDGE_WITHOUT_GEOMETRY = {"length": 1112}


# OSMnx lists parallel edges in any order. The same edge must be kept
# whether it is listed first or last. A shape is a list of [latitude,
# longitude] points.
@pytest.mark.parametrize(
    "parallel_edges, shapes_kept",
    [
        ([STRAIGHT_EDGE, DETOUR_EDGE], {1: [[0.0, 0.005]]}),
        ([DETOUR_EDGE, STRAIGHT_EDGE], {1: [[0.0, 0.005]]}),
        ([DETOUR_EDGE, SHORT_EDGE_WITHOUT_GEOMETRY], {}),
    ],
    ids=[
        "shortest listed first",
        "shortest listed last",
        "shortest has no geometry",
    ],
)
def test_the_shortest_of_parallel_edges_is_kept_with_its_own_shape(
    parallel_edges, shapes_kept
):
    osmnx_graph = _OSMnxGraph(
        PLACES, [(WEST, EAST, edge) for edge in parallel_edges]
    )

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert geograph.graph_object.graph[0] == {1: 1.112}
    assert geograph.intermediate_nodes[0] == shapes_kept


def test_an_edge_drawn_from_node_to_node_without_a_point_between_has_no_shape():
    edge = {
        "length": 1112,
        "geometry": _drawn_through((0.0, 0.0), (0.01, 0.0)),
    }
    osmnx_graph = _OSMnxGraph(PLACES, [(WEST, EAST, edge)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert geograph.intermediate_nodes[0] == {}


def test_a_geometry_listed_from_destination_to_origin_is_reversed():
    # The edge goes from WEST to EAST. Its geometry starts at EAST.
    edge = {
        "length": 1112,
        "geometry": _drawn_through(
            (0.01, 0.0), (0.007, 0.001), (0.003, 0.002), (0.0, 0.0)
        ),
    }
    osmnx_graph = _OSMnxGraph(PLACES, [(WEST, EAST, edge)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert geograph.intermediate_nodes[0] == {
        1: [[0.002, 0.003], [0.001, 0.007]]
    }


def test_geometry_points_that_round_onto_the_nodes_are_left_out():
    # Coordinates are rounded to 5 decimals. The second point then falls on
    # WEST, and the last but one point falls on EAST.
    edge = {
        "length": 1112,
        "geometry": _drawn_through(
            (0.0, 0.0),
            (0.000001, 0.0),
            (0.005, 0.0),
            (0.009999, 0.0),
            (0.01, 0.0),
        ),
    }
    osmnx_graph = _OSMnxGraph(PLACES, [(WEST, EAST, edge)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert geograph.intermediate_nodes[0] == {1: [[0.0, 0.005]]}


def test_an_edge_between_two_nodes_at_the_same_place_keeps_its_shape():
    # The edge leaves the first node, makes a loop and ends at the second
    # node. Its ends do not tell in which direction its geometry is listed.
    two_nodes_at_one_place = {WEST: (0.0, 0.0), EAST: (0.0, 0.0)}
    loop = {
        "length": 1112,
        "geometry": _drawn_through(
            (0.0, 0.0), (0.003, 0.002), (0.007, 0.001), (0.0, 0.0)
        ),
    }
    osmnx_graph = _OSMnxGraph(two_nodes_at_one_place, [(WEST, EAST, loop)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert geograph.intermediate_nodes[0] == {
        1: [[0.002, 0.003], [0.001, 0.007]]
    }


def test_osmnx_nodes_keep_their_osm_ids_in_hilbert_order():
    # OSMnx lists EAST first. The Hilbert curve visits WEST first.
    east_listed_first = {EAST: PLACES[EAST], WEST: PLACES[WEST]}
    osmnx_graph = _OSMnxGraph(east_listed_first, [(WEST, EAST, STRAIGHT_EDGE)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert list(geograph.source_node_ids) == [WEST, EAST]
    assert geograph.nodes == [[0.0, 0.0], [0.0, 0.01]]


def test_osmnx_coordinates_rounded_to_7_decimals_or_fewer_are_integers():
    # The default is 5 decimals. A network file then stores each coordinate
    # as an int32, in 1e-7 degree.
    osmnx_graph = _OSMnxGraph(PLACES, [(WEST, EAST, STRAIGHT_EDGE)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

    assert geograph.coordinate_dtype == "int32"


# A town of three nodes, as OSMnx gives it after `add_edge_travel_times`: an
# edge has its length in meters, its travel time in seconds, and the
# `highway` value of its way.
#
#          NORTH
#         /     \        the avenue: 0.8 km + 0.8 km, 60 s + 60 s
#     WEST ----- EAST    the street: 1.112 km, 200 s
#
# The bypass and the alley also go from WEST to EAST. Both are longer than
# the street. A load by length keeps the street, and drops the two others
# with their classes and their travel times. From WEST to EAST, the street is
# then the shortest way and the avenue is the fastest.
NORTH = 3
BYPASS = {"length": 3000, "travel_time": 100.0, "highway": "trunk"}
STREET = {"length": 1112, "travel_time": 200.0, "highway": "residential"}
ALLEY = {"length": 2000, "travel_time": 400.0, "highway": "service"}
# The loader rounds a travel time to 3 decimals, as a length: 60 s.
AVENUE_FROM_WEST = {"length": 800, "travel_time": 60.0004, "highway": "primary"}
# OSMnx gives a list to an edge that it made from ways of several values.
AVENUE_TO_EAST = {
    "length": 800,
    "travel_time": 60.0,
    "highway": ["primary", "secondary"],
}
STREET_BACK_WITHOUT_HIGHWAY = {"length": 1112, "travel_time": 200.0}
TOWN = _OSMnxGraph(
    {**PLACES, NORTH: (0.005, 0.005)},
    [
        (WEST, EAST, BYPASS),
        (WEST, EAST, STREET),
        (WEST, EAST, ALLEY),
        (WEST, NORTH, AVENUE_FROM_WEST),
        (NORTH, EAST, AVENUE_TO_EAST),
        (EAST, WEST, STREET_BACK_WITHOUT_HIGHWAY),
    ],
)
# The points of a query from WEST to EAST. Each point is at its node: the
# route has no off-graph leg.
POINT_OF_WEST = {"latitude": 0.0, "longitude": 0.0}
POINT_OF_EAST = {"latitude": 0.0, "longitude": 0.01}


# 1 km of an off-graph leg takes 3600 s / the off-graph travel speed in km/h.
# Without a speed, it takes 240 s: 15 km/h.
@pytest.mark.parametrize(
    "off_graph_travel_speed, off_graph_seconds_per_km",
    [(None, 240.0), (30, 120.0)],
)
def test_the_travel_times_of_an_osmnx_graph_are_the_metric_travel_time(
    off_graph_travel_speed, off_graph_seconds_per_km
):
    town = GeoGraph.load_from_osmnx_graph(
        TOWN, off_graph_travel_speed=off_graph_travel_speed
    )

    assert town.metrics == [
        {"name": "length", "unit": "km"},
        {
            "name": "travel_time",
            "unit": "s",
            "description": "Attribute travel_time of the OSMnx graph.",
            "off_graph_weight_per_km": off_graph_seconds_per_km,
        },
    ]


def test_a_route_by_travel_time_is_the_fastest_and_has_its_km_as_length():
    town = GeoGraph.load_from_osmnx_graph(TOWN)

    route = town.get_shortest_path(
        POINT_OF_WEST, POINT_OF_EAST, metric="travel_time"
    )

    # The avenue: 0.8 km + 0.8 km, in 60 s + 60 s.
    assert route["length"] == pytest.approx(1.6)
    assert route["metric_totals"] == {"travel_time": 120.0}


def test_an_osmnx_edge_has_the_class_of_its_highway_value():
    town = GeoGraph.load_from_osmnx_graph(TOWN)

    osm_id = list(town.source_node_ids)
    classes_and_modes = {
        (osm_id[edge["origin_id"]], osm_id[edge["destination_id"]]): (
            edge["edge_class"],
            edge["edge_mode"],
        )
        for edge in town.get_edges()
    }
    assert classes_and_modes == {
        (WEST, EAST): ("residential", "road"),
        (WEST, NORTH): ("primary", "road"),
        (NORTH, EAST): ("primary", "road"),
        (EAST, WEST): (None, None),
    }


# With `weight_key="travel_time"`, the lengths of the geograph are seconds.
# From WEST to EAST, the loader then keeps the bypass, which is the fastest
# of the three edges.
@pytest.fixture
def town_in_seconds():
    return GeoGraph.load_from_osmnx_graph(
        TOWN, weight_key="travel_time", off_graph_travel_speed=30
    )


# The lengths of this geograph are seconds. A weight of `weight_per_km` is for
# 1 km, so the call is refused.
def test_a_weight_per_km_is_refused_on_a_geograph_in_seconds(town_in_seconds):
    with pytest.raises(ValueError, match="in 's'"):
        town_in_seconds.create_metric("cost", weight_per_km=2.0)


def test_a_geograph_in_seconds_read_from_a_file_keeps_its_unit_and_its_routes(
    town_in_seconds, tmp_path
):
    path = str(tmp_path / "town.scgraph")
    town_in_seconds.save_as_scgraph(path)

    loaded = GeoGraph.load_from_scgraph(path)

    assert loaded.metrics == [{"name": "length", "unit": "s"}]
    # The bypass takes 100 s, and the avenue 60 s + 60 s.
    route = loaded.get_shortest_path(POINT_OF_WEST, POINT_OF_EAST)
    assert route["length"] == 100.0
