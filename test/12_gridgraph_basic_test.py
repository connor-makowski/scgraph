import pytest

from scgraph import GridGraph
from scgraph.utils import hard_round


# A grid 11 wide and 10 high, with a wall on the column x = 5 from y = 3 to the
# top: a route from one side to the other goes down to y <= 2 to pass it.
@pytest.fixture
def grid_with_a_wall():
    return GridGraph(
        x_size=11,
        y_size=10,
        blocks=[(5, y) for y in range(3, 10)],
        shape=[(0, 0), (0, 1), (1, 0), (1, 1)],
        add_exterior_walls=True,
    )


# From (1, 8) to (8, 8), the shortest way round the wall goes 6 rows down to
# y = 2 and 6 up, and 7 columns across. The two moves past the end of the wall
# cannot be diagonal, so 5 moves are diagonal and 9 straight.
LENGTH_ROUND_THE_WALL = 9 + 5 * 2**0.5


@pytest.mark.parametrize(
    "algorithm", ["dijkstra", "dijkstra_buckets", "cached_shortest_path"]
)
def test_algorithm_finds_the_shortest_way_round_the_wall(
    grid_with_a_wall, algorithm
):
    route = grid_with_a_wall.get_shortest_path(
        origin_node={"x": 1, "y": 8},
        destination_node={"x": 8, "y": 8},
        algorithm_fn=algorithm,
    )

    assert route["length"] == pytest.approx(LENGTH_ROUND_THE_WALL, abs=0.001)


def test_a_star_finds_the_shortest_way_round_the_wall(grid_with_a_wall):
    route = grid_with_a_wall.get_shortest_path(
        origin_node={"x": 1, "y": 8},
        destination_node={"x": 8, "y": 8},
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": grid_with_a_wall.euclidean_heuristic},
    )

    assert route["length"] == pytest.approx(LENGTH_ROUND_THE_WALL, abs=0.001)


# The two tests below ask for a route between two points that are not grid
# nodes, in each output format. The route goes from (1, 1.1) to the node
# (1, 1), to the node (1, 2) and to (1, 2.3): 0.1 + 1 + 0.3.


def test_route_between_points_off_the_grid_nodes_as_lists(grid_with_a_wall):
    route = grid_with_a_wall.get_shortest_path(
        origin_node={"x": 1, "y": 1.1},
        destination_node={"x": 1, "y": 2.3},
        output_coordinate_path="list_of_lists",
    )

    assert hard_round(4, route["length"]) == 1.4
    assert route["coordinate_path"] == [[1, 1.1], [1, 1], [1, 2], [1, 2.3]]


def test_route_between_points_off_the_grid_nodes_as_dicts(grid_with_a_wall):
    route = grid_with_a_wall.get_shortest_path(
        origin_node={"x": 1, "y": 1.1},
        destination_node={"x": 1, "y": 2.3},
        output_coordinate_path="list_of_dicts",
    )

    assert hard_round(4, route["length"]) == 1.4
    assert route["coordinate_path"] == [
        {"x": 1, "y": 1.1},
        {"x": 1, "y": 1},
        {"x": 1, "y": 2},
        {"x": 1, "y": 2.3},
    ]
