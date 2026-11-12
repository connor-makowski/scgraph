import pytest
from scgraph import Graph, NegativeCycleError


def test_no_negative_cycle():
    graph = Graph([{1: -1}, {2: 2}, {0: 2}])
    output = graph.dijkstra_negative(
        origin_id=0, destination_id=1, cycle_check_iterations=10
    )
    assert output == {"path": [0, 1], "length": -1}


def test_negative_cycle_raises():
    graph = Graph([{1: -5}, {2: 2}, {0: 2}])
    with pytest.raises(NegativeCycleError):
        graph.dijkstra_negative(
            origin_id=0, destination_id=1, cycle_check_iterations=10
        )


def test_bellman_ford_finds_the_shortest_path_through_a_negative_link():
    # From node 0 to node 3, the path 0 -> 1 -> 3 weighs 4 + 1 = 5. The path
    # 0 -> 2 -> 1 -> 3 uses the negative link 2 -> 1 and weighs 1 - 2 + 1 = 0.
    graph = Graph([{1: 4, 2: 1}, {3: 1}, {1: -2}, {}])

    found = graph.bellman_ford(origin_id=0, destination_id=3)

    assert found == {"path": [0, 2, 1, 3], "length": 0}


def test_bellman_ford_goes_on_until_no_distance_changes():
    # A chain of 30 nodes: 29 -> 28 -> ... -> 0, each link of weight 1.
    # Bellman-Ford reads the nodes in the order of their ids, so each pass
    # finds the final distance of one more node. The search needs 29 passes.
    chain_from_29_to_0 = [{}] + [{node_id - 1: 1} for node_id in range(1, 30)]
    graph = Graph(chain_from_29_to_0)

    found = graph.bellman_ford(origin_id=29, destination_id=0)

    assert found == {"path": list(range(29, -1, -1)), "length": 29}


def test_bellman_ford_reports_a_negative_cycle_off_the_path():
    # The path from node 0 to node 3 is one link. Node 0 also reaches the
    # cycle 1 -> 2 -> 1, which weighs 1 - 3 = -2 and does not lead to node 3.
    graph = Graph([{1: 1, 3: 1}, {2: 1}, {1: -3}, {}])

    with pytest.raises(NegativeCycleError, match="negative weight cycle"):
        graph.bellman_ford(origin_id=0, destination_id=3)
