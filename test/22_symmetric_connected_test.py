import pytest

# Six nodes; every link exists in both directions with the same weight, and
# every node can be reached from every other one
SYMMETRIC_CONNECTED_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def test_validate_accepts_a_symmetric_connected_graph(Graph):
    graph = Graph(SYMMETRIC_CONNECTED_GRAPH)

    graph.validate(check_symmetry=True, check_connected=True)


# C++ raises ValueError and pure Python AssertionError for a graph that is not
# symmetric (RuntimeError and AssertionError for one that is not connected),
# hence Exception in the tests below.


def test_validate_refuses_a_link_whose_two_directions_differ_in_weight(Graph):
    # 0 -> 1 weighs 5 and 1 -> 0 weighs 99
    graph = Graph([{1: 5}, {0: 99}])

    with pytest.raises(Exception):  # noqa: B017 (see the comment above)
        graph.validate(check_symmetry=True, check_connected=False)


def test_validate_refuses_a_one_way_link(Graph):
    # 0 -> 1 exists and 1 -> 0 does not
    graph = Graph([{1: 5}, {}])

    with pytest.raises(Exception):  # noqa: B017 (see the comment above)
        graph.validate(check_symmetry=True, check_connected=False)


def test_validate_does_not_look_at_symmetry_unless_asked(Graph):
    # The two directions differ in weight, and every node is reached
    graph = Graph([{1: 5}, {0: 99}])

    graph.validate(check_symmetry=False, check_connected=True)


def test_validate_refuses_a_graph_in_two_parts(Graph):
    # Nodes 0 and 1 are linked, nodes 2 and 3 are linked, nothing joins the pairs
    graph = Graph([{1: 3}, {0: 3}, {3: 3}, {2: 3}])

    with pytest.raises(Exception):  # noqa: B017 (see the comment above)
        graph.validate(check_symmetry=False, check_connected=True)


def test_validate_does_not_look_at_connectivity_unless_asked(Graph):
    # Two separate pairs of nodes, each with a symmetric link
    graph = Graph([{1: 3}, {0: 3}, {3: 3}, {2: 3}])

    graph.validate(check_symmetry=True, check_connected=False)


def test_validate_refuses_a_graph_where_a_node_cannot_be_reached_back(Graph):
    # 0 -> 1 -> 2: node 0 reaches every node, and no node reaches node 0
    graph = Graph([{1: 5}, {2: 2}, {}])

    with pytest.raises(Exception):  # noqa: B017 (see the comment above)
        graph.validate(check_symmetry=False, check_connected=True)


def test_validate_refuses_an_empty_graph(Graph):
    graph = Graph([])

    with pytest.raises(ValueError):
        graph.validate(check_symmetry=True, check_connected=True)
