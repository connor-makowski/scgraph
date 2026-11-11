import pytest
from scgraph import NegativeCycleError
from helpers import GRAPH_CLASSES


# With negative weights, each of the two algorithms that accept them finds the
# shortest path when no cycle is negative, and reports a negative cycle that
# the origin reaches, also when the destination is reached without it.
@pytest.mark.parametrize(
    "algorithm, graph_data, origin_id, destination_id, expected",
    [
        ("dijkstra_negative", [{1: -1}, {2: 2}, {0: 2}], 0, 1, [0, 1]),
        ("dijkstra_negative", [{1: -5}, {2: 2}, {0: 2}], 0, 1, None),
        # The shortest path goes through the negative edge 2 -> 1
        (
            "bellman_ford",
            [{1: 4, 2: 1}, {3: 1}, {1: -2}, {}],
            0,
            3,
            [0, 2, 1, 3],
        ),
        # Links point from higher to lower node ids, so each pass in id order
        # only settles one more node: no stop before the 29th pass
        (
            "bellman_ford",
            [{}] + [{i - 1: 1} for i in range(1, 30)],
            29,
            0,
            list(range(29, -1, -1)),
        ),
        # The cycle 1 <-> 2 (weight -2) is off the path 0 -> 3
        ("bellman_ford", [{1: 1, 3: 1}, {2: 1}, {1: -3}, {}], 0, 3, None),
    ],
)
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_negative_weights(
    GraphClass, algorithm, graph_data, origin_id, destination_id, expected
):
    search = getattr(GraphClass(graph_data), algorithm)
    if expected is None:
        with pytest.raises(NegativeCycleError):
            search(origin_id=origin_id, destination_id=destination_id)
        return
    assert search(origin_id=origin_id, destination_id=destination_id) == {
        "path": expected,
        "length": sum(graph_data[u][v] for u, v in zip(expected, expected[1:])),
    }
