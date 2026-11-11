import pytest
from scgraph import NegativeCycleError
from helpers import GRAPH_CLASSES


def _length(graph_data, path):
    return sum(graph_data[u][v] for u, v in zip(path, path[1:]))


# With negative weights and no negative cycle, each of the two algorithms that
# accept them finds the shortest path, which is found by hand.
@pytest.mark.parametrize(
    "algorithm, options, graph_data, origin_id, destination_id, path",
    [
        (
            "dijkstra_negative",
            {"cycle_check_iterations": 10},
            [{1: -1}, {2: 2}, {0: 2}],
            0,
            1,
            [0, 1],
        ),
        # The shortest path goes through the negative edge 2 -> 1
        (
            "bellman_ford",
            {},
            [{1: 4, 2: 1}, {3: 1}, {1: -2}, {}],
            0,
            3,
            [0, 2, 1, 3],
        ),
        # Links point from higher to lower node ids, so each pass in id order
        # only settles one more node: no stop before the 29th pass
        (
            "bellman_ford",
            {},
            [{}] + [{i - 1: 1} for i in range(1, 30)],
            29,
            0,
            list(range(29, -1, -1)),
        ),
    ],
)
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_shortest_path_with_negative_weights(
    GraphClass, algorithm, options, graph_data, origin_id, destination_id, path
):
    search = getattr(GraphClass(graph_data), algorithm)
    assert search(
        origin_id=origin_id, destination_id=destination_id, **options
    ) == {"path": path, "length": _length(graph_data, path)}


# A negative cycle that the origin reaches is reported, also when the
# destination is reached without it.
@pytest.mark.parametrize(
    "algorithm, options, graph_data, origin_id, destination_id",
    [
        # The cycle 0 -> 1 -> 2 -> 0 has weight -1
        (
            "dijkstra_negative",
            {"cycle_check_iterations": 10},
            [{1: -5}, {2: 2}, {0: 2}],
            0,
            1,
        ),
        # The cycle 1 <-> 2 (weight -2) is off the path 0 -> 3
        ("bellman_ford", {}, [{1: 1, 3: 1}, {2: 1}, {1: -3}, {}], 0, 3),
    ],
)
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_negative_cycle_is_reported(
    GraphClass, algorithm, options, graph_data, origin_id, destination_id
):
    search = getattr(GraphClass(graph_data), algorithm)
    with pytest.raises(NegativeCycleError):
        search(origin_id=origin_id, destination_id=destination_id, **options)
