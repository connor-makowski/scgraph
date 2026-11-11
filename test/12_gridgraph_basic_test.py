import pytest

from scgraph import GridGraph
from scgraph.utils import hard_round

_OFF_GRAPH = {
    "length": 1.4,
    "coordinate_path": [[1, 1.1], [1, 1], [1, 2], [1, 2.3]],
}


def _walled_grid():
    # A wall on the column x = 5, open for y <= 2
    return GridGraph(
        x_size=11,
        y_size=10,
        blocks=[(5, y) for y in range(3, 10)],
        shape=[(0, 0), (0, 1), (1, 0), (1, 1)],
        add_exterior_walls=True,
    )


# Every algorithm finds the shortest way round a wall. From (1, 8) to (8, 8), it
# goes 6 rows down to y = 2 and 6 up, and 7 columns across; the two moves past
# the end of the wall cannot be diagonal, so 5 moves are diagonal and 9 straight.
@pytest.mark.parametrize(
    "algorithm, heuristic",
    [
        ("dijkstra", None),
        ("dijkstra_buckets", None),
        ("a_star", "euclidean_heuristic"),
        ("cached_shortest_path", None),
    ],
)
def test_shortest_path_round_a_wall(algorithm, heuristic):
    grid = _walled_grid()
    kwargs = {"heuristic_fn": getattr(grid, heuristic)} if heuristic else {}
    output = grid.get_shortest_path(
        origin_node={"x": 1, "y": 8},
        destination_node={"x": 8, "y": 8},
        algorithm_fn=algorithm,
        algorithm_kwargs=kwargs,
    )
    assert output["length"] == pytest.approx(9 + 5 * 2**0.5, abs=0.001)


# A route between two points off the grid nodes adds the legs to the nearest
# nodes (0.1 + 1 + 0.3), in both output formats.
@pytest.mark.parametrize(
    "output_coordinate_path, as_point",
    [
        ("list_of_lists", list),
        ("list_of_dicts", lambda point: {"x": point[0], "y": point[1]}),
    ],
)
def test_off_graph_nodes(output_coordinate_path, as_point):
    output = _walled_grid().get_shortest_path(
        origin_node={"x": 1, "y": 1.1},
        destination_node={"x": 1, "y": 2.3},
        output_coordinate_path=output_coordinate_path,
    )
    assert hard_round(4, output["length"]) == _OFF_GRAPH["length"]
    assert output["coordinate_path"] == [
        as_point(point) for point in _OFF_GRAPH["coordinate_path"]
    ]
