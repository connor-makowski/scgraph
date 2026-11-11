import pytest
from scgraph import PathNotFoundError
from helpers import assert_result

# Six nodes, every link in both directions with the same weight
GRAPH_IN_ONE_PART = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
# The same graph, plus three nodes (6 -> 7 -> 8 -> 6) that no link joins to the
# first six: a search from node 0 never reaches them
GRAPH_WITH_A_PART_OUT_OF_REACH = [*GRAPH_IN_ONE_PART, {7: 1}, {8: 1}, {6: 1}]

# Found by hand: node 5 is only reached from node 3 (weight 6), and the
# cheapest way to node 3 is 0 -> 2 -> 1 -> 3 (1 + 2 + 1 = 4, against 5 by
# 0 -> 2 -> 3 and 6 by 0 -> 1 -> 3)
SHORTEST_PATH_FROM_0_TO_5 = {"path": [0, 2, 1, 3, 5], "length": 10}

on_the_two_graphs = pytest.mark.parametrize(
    "graph_data",
    [GRAPH_IN_ONE_PART, GRAPH_WITH_A_PART_OUT_OF_REACH],
    ids=["in_one_part", "with_a_part_out_of_reach"],
)


@pytest.mark.parametrize(
    "algorithm",
    [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bellman_ford",
        "bmssp",
        "contraction_hierarchy",
        "tnr",
    ],
)
@on_the_two_graphs
def test_every_algorithm_finds_the_shortest_path(Graph, graph_data, algorithm):
    graph = Graph(graph_data)

    found = getattr(graph, algorithm)(origin_id=0, destination_id=5)

    assert_result(found, SHORTEST_PATH_FROM_0_TO_5)


@on_the_two_graphs
def test_a_star_finds_the_shortest_path(Graph, graph_data):
    graph = Graph(graph_data)

    # a_star searches by itself only with a heuristic (without one it calls
    # dijkstra); this one estimates every remaining distance as zero
    found = graph.a_star(
        origin_id=0,
        destination_id=5,
        heuristic_fn=lambda node_id, destination_id: 0,
    )

    assert_result(found, SHORTEST_PATH_FROM_0_TO_5)


@on_the_two_graphs
def test_shortest_path_tree_of_the_origin_holds_the_shortest_path(
    Graph, graph_data
):
    graph = Graph(graph_data)

    tree = graph.get_shortest_path_tree(origin_id=0)
    found = graph.get_tree_path(origin_id=0, destination_id=5, tree_data=tree)

    assert_result(found, SHORTEST_PATH_FROM_0_TO_5)


def test_link_to_a_node_outside_the_graph_raises(Graph):
    # One node, with a link to a node 5 that does not exist. The C++ class
    # refuses the graph when it is built, the Python class when reduce() reads
    # the link (no validation was asked for).
    with pytest.raises(IndexError):
        Graph([{5: 1}]).reduce(1)


def test_search_between_two_nodes_that_no_path_joins_raises(Graph):
    # Nodes 0 and 1 are linked, nodes 2 and 3 are linked, nothing joins the
    # two pairs
    graph = Graph([{1: 1.0}, {0: 1.0}, {3: 1.0}, {2: 1.0}])

    with pytest.raises(PathNotFoundError):
        graph.dijkstra(0, 3)
