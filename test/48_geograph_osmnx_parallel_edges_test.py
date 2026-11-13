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


# OSMnx lists parallel edges in any order. The same edge must be kept
# whether it is listed first or last.
@pytest.mark.parametrize(
    "parallel_edges",
    [[STRAIGHT_EDGE, DETOUR_EDGE], [DETOUR_EDGE, STRAIGHT_EDGE]],
    ids=["shortest listed first", "shortest listed last"],
)
def test_the_shortest_of_parallel_edges_is_kept_with_its_own_shape(
    parallel_edges,
):
    osmnx_graph = _OSMnxGraph(
        PLACES, [(WEST, EAST, edge) for edge in parallel_edges]
    )

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

    assert geograph.graph_object.graph[0] == {1: 1.112}
    # The shape is the [latitude, longitude] point of the straight edge.
    assert geograph.intermediate_nodes[0] == {1: [[0.0, 0.005]]}


def test_no_shape_is_kept_when_the_shortest_parallel_edge_has_no_geometry():
    # OSMnx gives no geometry to an edge that is a straight line.
    short_edge_without_geometry = {"length": 1112}
    osmnx_graph = _OSMnxGraph(
        PLACES,
        [(WEST, EAST, DETOUR_EDGE), (WEST, EAST, short_edge_without_geometry)],
    )

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

    assert geograph.graph_object.graph[0] == {1: 1.112}
    assert geograph.intermediate_nodes[0] == {}


def test_an_edge_drawn_from_node_to_node_without_a_point_between_has_no_shape():
    edge = {
        "length": 1112,
        "geometry": _drawn_through((0.0, 0.0), (0.01, 0.0)),
    }
    osmnx_graph = _OSMnxGraph(PLACES, [(WEST, EAST, edge)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

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

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

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

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

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

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

    assert geograph.intermediate_nodes[0] == {
        1: [[0.002, 0.003], [0.001, 0.007]]
    }


def test_osmnx_nodes_keep_their_osm_ids_in_hilbert_order():
    # OSMnx lists EAST first. The Hilbert curve visits WEST first.
    east_listed_first = {EAST: PLACES[EAST], WEST: PLACES[WEST]}
    osmnx_graph = _OSMnxGraph(east_listed_first, [(WEST, EAST, STRAIGHT_EDGE)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

    assert list(geograph.node_ids) == [WEST, EAST]
    assert geograph.nodes == [[0.0, 0.0], [0.0, 0.01]]


def test_osmnx_coordinates_rounded_to_7_decimals_or_fewer_are_integers():
    # The default is 5 decimals. A network file then stores each coordinate
    # as an int32, in 1e-7 degree.
    osmnx_graph = _OSMnxGraph(PLACES, [(WEST, EAST, STRAIGHT_EDGE)])

    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)

    assert geograph.coordinate_dtype == "int32"
