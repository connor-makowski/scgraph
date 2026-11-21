import json

import pytest
from helpers import great_circle_km

from scgraph import GeoGraph

# Four lines, as GeoJSON writes them: lists of [longitude, latitude] points.
# The first three lie near the equator. The long line lies one degree north.
STRAIGHT_LINE = [[0, 0], [0.01, 0], [0.02, 0]]
# This line starts at the middle point of the straight line.
BRANCH_LINE = [[0.01, 0], [0.01, 0.01]]
# This line crosses the straight line between two of its points.
CROSSING_LINE = [[0.015, -0.005], [0.015, 0.005]]
# Each of the three segments of this line is about 1.2 km long.
LONG_LINE = [[0, 1], [0.01, 1.005], [0.02, 1], [0.03, 1]]

# The points of the long line as [latitude, longitude], the order of scgraph.
LONG_START, LONG_BEND = (1, 0), (1.005, 0.01)
LONG_CUT, LONG_END = (1, 0.02), (1, 0.03)


@pytest.fixture(scope="module")
def geograph(tmp_path_factory):
    """The network of the four lines, cut where a piece reaches 2 km."""
    path = tmp_path_factory.mktemp("geojson") / "lines.geojson"
    lines = [STRAIGHT_LINE, BRANCH_LINE, CROSSING_LINE, LONG_LINE]
    path.write_text(
        json.dumps(
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "LineString", "coordinates": line}
                    for line in lines
                ],
            }
        )
    )
    return GeoGraph.load_from_geojson(str(path), max_km_between_nodes=2)


def _by_end_points(geograph, rows):
    """The values of `rows`, a list of one dict per node, as one dict. Its
    keys are the pairs (origin point, destination point)."""
    return {
        (tuple(geograph.nodes[u]), tuple(geograph.nodes[v])): value
        for u, row in enumerate(rows)
        for v, value in row.items()
    }


@pytest.fixture(scope="module")
def edges(geograph):
    """The length of each edge, by the points of its two ends."""
    return _by_end_points(geograph, geograph.graph_object.graph)


def test_two_lines_are_joined_at_a_point_that_both_have(edges):
    # The branch line leaves from (0, 0.01), a point of the straight line.
    # The straight line is cut there into two edges.
    edges_at_shared_point = {edge for edge in edges if edge[0] == (0, 0.01)}

    assert edges_at_shared_point == {
        ((0, 0.01), (0, 0)),
        ((0, 0.01), (0, 0.02)),
        ((0, 0.01), (0.01, 0.01)),
    }


def test_two_lines_that_cross_without_a_shared_point_are_not_joined(edges):
    south_end, north_end = (-0.005, 0.015), (0.005, 0.015)
    edges_of_crossing_line = {
        edge for edge in edges if south_end in edge or north_end in edge
    }

    assert edges_of_crossing_line == {
        (south_end, north_end),
        (north_end, south_end),
    }


def test_a_long_line_is_cut_at_the_first_point_max_km_from_its_start(edges):
    # The bend is 1.2 km from the start: no cut. The next point is 2.4 km
    # from the start: the line is cut there. The end is 1.1 km further.
    points_of_long_line = (LONG_START, LONG_BEND, LONG_CUT, LONG_END)
    edges_of_long_line = {
        edge for edge in edges if edge[0] in points_of_long_line
    }

    assert edges_of_long_line == {
        (LONG_START, LONG_CUT),
        (LONG_CUT, LONG_START),
        (LONG_CUT, LONG_END),
        (LONG_END, LONG_CUT),
    }


def test_an_edge_has_the_length_and_the_shape_of_its_line(geograph, edges):
    shapes = _by_end_points(geograph, geograph.intermediate_nodes)

    # The edge from the start of the long line to its cut passes the bend,
    # which lies north of the straight line between them.
    assert edges[(LONG_START, LONG_CUT)] == pytest.approx(
        great_circle_km(LONG_START, LONG_BEND)
        + great_circle_km(LONG_BEND, LONG_CUT)
    )
    assert shapes[(LONG_START, LONG_CUT)] == [list(LONG_BEND)]


def test_coordinates_rounded_to_7_decimals_or_fewer_are_integers(geograph):
    # The default is 5 decimals. A network file then stores each coordinate
    # as an int32, in 1e-7 degree.
    assert geograph.coordinate_dtype == "int32"
