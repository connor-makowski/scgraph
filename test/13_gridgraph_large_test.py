import pytest
from scgraph.grid import GridGraph
from scgraph.utils import hard_round

_X_SIZE = 300
_Y_SIZE = 300
_BLOCKS = [(150, i) for i in range(5, _Y_SIZE)]
_SHAPE = [(0, 0), (0, 1), (1, 0), (1, 1)]
_ORIGIN = {"x": 10, "y": _Y_SIZE - 10}
_DEST = {"x": _X_SIZE - 10, "y": _Y_SIZE - 10}


@pytest.fixture(scope="module")
def large_grid():
    return GridGraph(
        x_size=_X_SIZE,
        y_size=_Y_SIZE,
        blocks=_BLOCKS,
        shape=_SHAPE,
        add_exterior_walls=True,
    )


def test_dijkstra_a_star_agree(large_grid):
    dijkstra = large_grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        cache=False,
        algorithm_fn="dijkstra",
    )
    a_star = large_grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        algorithm_fn="a_star",
        heuristic_fn="euclidean",
    )
    assert hard_round(4, dijkstra["length"]) == hard_round(4, a_star["length"])


def test_cached_shortest_path_agrees(large_grid):
    direct = large_grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        algorithm_fn="a_star",
        heuristic_fn="euclidean",
    )
    cached = large_grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        algorithm_fn="cached_shortest_path",
    )
    assert hard_round(4, direct["length"]) == hard_round(4, cached["length"])
