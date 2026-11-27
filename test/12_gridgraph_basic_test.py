import pytest

from scgraph import GridGraph
from scgraph.utils import hard_round

_X_SIZE = 11
_Y_SIZE = 10
_BLOCKS = [(5, i) for i in range(3, _Y_SIZE)]
_SHAPE = [(0, 0), (0, 1), (1, 0), (1, 1)]
_EXPECTED_LENGTH = 16.071
_EXPECTED_OFF_GRAPH = {
    "length": 1.4,
    "coordinate_path": [[1, 1.1], [1, 1], [1, 2], [1, 2.3]],
}


def test_basic_gridgraph():
    grid = GridGraph(
        x_size=_X_SIZE,
        y_size=_Y_SIZE,
        blocks=_BLOCKS,
        shape=_SHAPE,
        add_exterior_walls=True,
    )
    output = grid.get_shortest_path(
        origin_node={"x": 1, "y": 8},
        destination_node={"x": 8, "y": 8},
        output_coordinate_path="list_of_lists",
    )
    assert hard_round(4, output["length"]) == _EXPECTED_LENGTH


def test_basic_gridgraph_a_star():
    grid = GridGraph(
        x_size=_X_SIZE,
        y_size=_Y_SIZE,
        blocks=_BLOCKS,
        shape=_SHAPE,
        add_exterior_walls=True,
    )
    output = grid.get_shortest_path(
        origin_node={"x": 1, "y": 8},
        destination_node={"x": 8, "y": 8},
        output_coordinate_path="list_of_lists",
        heuristic_fn="euclidean",
    )
    assert hard_round(4, output["length"]) == _EXPECTED_LENGTH


def test_tie_between_two_paths_returns_the_path_of_release_3_6():
    # Two paths of this query have the same length. Release 3.6.0 returned this one
    # with the C++ extension.
    grid = GridGraph(x_size=8, y_size=8, blocks=[], add_exterior_walls=True)
    output = grid.get_shortest_path(
        origin_node={"x": 1, "y": 1},
        destination_node={"x": 6, "y": 3},
        output_coordinate_path="list_of_lists",
        algorithm_fn="bidirectional_dijkstra",
    )
    assert output["coordinate_path"] == [
        [1, 1],
        [2, 1],
        [3, 1],
        [4, 2],
        [5, 3],
        [6, 3],
    ]


@pytest.mark.parametrize(
    "output_coordinate_path, as_point",
    [
        ("list_of_lists", list),
        ("list_of_dicts", lambda point: {"x": point[0], "y": point[1]}),
    ],
)
def test_off_graph_nodes(output_coordinate_path, as_point):
    grid = GridGraph(
        x_size=_X_SIZE,
        y_size=_Y_SIZE,
        blocks=_BLOCKS,
        shape=_SHAPE,
        add_exterior_walls=True,
    )
    output = grid.get_shortest_path(
        origin_node={"x": 1, "y": 1.1},
        destination_node={"x": 1, "y": 2.3},
        output_coordinate_path=output_coordinate_path,
    )
    assert hard_round(4, output["length"]) == _EXPECTED_OFF_GRAPH["length"]
    assert output["coordinate_path"] == [
        as_point(point) for point in _EXPECTED_OFF_GRAPH["coordinate_path"]
    ]
