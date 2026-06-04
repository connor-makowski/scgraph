import pytest
from scgraph import Graph


def test_no_negative_cycle():
    graph = Graph([{1: -1}, {2: 2}, {0: 2}])
    graph.dijkstra_negative(
        origin_id=0, destination_id=1, cycle_check_iterations=10
    )


def test_negative_cycle_raises():
    graph = Graph([{1: -5}, {2: 2}, {0: 2}])
    with pytest.raises(Exception):
        graph.dijkstra_negative(
            origin_id=0, destination_id=1, cycle_check_iterations=10
        )
