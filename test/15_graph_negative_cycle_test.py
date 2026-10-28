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


def test_bellman_ford_negative_weights():
    # No cycle: the shortest path goes through the negative edge 2 -> 1
    graph = Graph([{1: 4, 2: 1}, {3: 1}, {1: -2}, {}])
    assert graph.bellman_ford(origin_id=0, destination_id=3) == {
        "path": [0, 2, 1, 3],
        "length": 0.0,
    }


def test_bellman_ford_needs_many_passes():
    # Links point from higher to lower node ids, so each pass in id order only
    # settles one more node: Bellman-Ford must not stop before the 29th pass
    graph = Graph([{}] + [{i - 1: 1} for i in range(1, 30)])
    assert graph.bellman_ford(origin_id=29, destination_id=0) == {
        "path": list(range(29, -1, -1)),
        "length": 29.0,
    }


def test_bellman_ford_negative_cycle_off_path():
    # The cycle 1 <-> 2 (weight -2) is reachable from 0, but the destination 3 is
    # reached directly: the cycle must be reported, and a broken detection would
    # return [0, 3] at once instead of looping on the cycle
    graph = Graph([{1: 1, 3: 1}, {2: 1}, {1: -3}, {}])
    with pytest.raises(Exception, match="negative weight cycle"):
        graph.bellman_ford(origin_id=0, destination_id=3)
