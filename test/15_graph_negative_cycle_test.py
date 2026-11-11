import pytest
from scgraph import NegativeCycleError

# Two algorithms accept negative weights: dijkstra_negative and bellman_ford.


def test_dijkstra_negative_finds_a_path_over_a_negative_link(Graph):
    # A one-way triangle 0 -> 1 -> 2 -> 0 of weights -1, 2 and 2: the cycle
    # weighs 3, so it is not a negative cycle
    graph = Graph([{1: -1}, {2: 2}, {0: 2}])

    found = graph.dijkstra_negative(
        origin_id=0, destination_id=1, cycle_check_iterations=10
    )

    assert found == {"path": [0, 1], "length": -1}


def test_bellman_ford_finds_the_shortest_path_through_a_negative_link(Graph):
    # From 0 to 3: 0 -> 1 -> 3 weighs 4 + 1 = 5, and the detour by the negative
    # link 2 -> 1 weighs 1 - 2 + 1 = 0
    graph = Graph([{1: 4, 2: 1}, {3: 1}, {1: -2}, {}])

    found = graph.bellman_ford(origin_id=0, destination_id=3)

    assert found == {"path": [0, 2, 1, 3], "length": 0}


def test_bellman_ford_goes_on_until_no_distance_changes(Graph):
    # A chain of 30 nodes whose links of weight 1 point from each node to the
    # one before: 29 -> 28 -> ... -> 0. A pass over the nodes in the order of
    # their ids settles only one more node, so the search needs 29 passes.
    chain = [{}] + [{node_id - 1: 1} for node_id in range(1, 30)]
    graph = Graph(chain)

    found = graph.bellman_ford(origin_id=29, destination_id=0)

    assert found == {"path": list(range(29, -1, -1)), "length": 29}


def test_dijkstra_negative_reports_a_negative_cycle_on_the_path(Graph):
    # A one-way triangle 0 -> 1 -> 2 -> 0 of weights -5, 2 and 2: each turn of
    # the cycle makes the path from 0 to 1 shorter by 1
    graph = Graph([{1: -5}, {2: 2}, {0: 2}])

    with pytest.raises(NegativeCycleError):
        graph.dijkstra_negative(
            origin_id=0, destination_id=1, cycle_check_iterations=10
        )


def test_bellman_ford_reports_a_negative_cycle_off_the_path(Graph):
    # The path from 0 to 3 is one link. The origin also reaches the cycle
    # 1 -> 2 -> 1, of weight 1 - 3 = -2, which does not lead to node 3.
    graph = Graph([{1: 1, 3: 1}, {2: 1}, {1: -3}, {}])

    with pytest.raises(NegativeCycleError):
        graph.bellman_ford(origin_id=0, destination_id=3)
