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


def test_off_graph_nodes():
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
        output_coordinate_path="list_of_lists",
    )
    assert hard_round(4, output["length"]) == _EXPECTED_OFF_GRAPH["length"]
    assert output["coordinate_path"] == _EXPECTED_OFF_GRAPH["coordinate_path"]
