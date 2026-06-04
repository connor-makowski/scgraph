import pytest
from scgraph import GeoGraph
from helpers import assert_result

_NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
_EXPECTED = {
    "coordinate_path": [[0, 0], [0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 1]],
    "length": 10,
}


@pytest.fixture(scope="module")
def basic_geograph():
    return GeoGraph(nodes=_NODES, graph=_GRAPH)


def test_graph_validation(basic_geograph):
    basic_geograph.validate()


def test_node_validation(basic_geograph):
    basic_geograph.validate_nodes()


def test_shortest_path(basic_geograph):
    assert_result(
        basic_geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 2, "longitude": 1},
        ),
        _EXPECTED,
    )
