from scgraph import Graph
from scgraph.utils import validate


print("\n===============\nBasic Graph Tests:\n===============")

graph = Graph([
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
])

expected = {"path": [0, 2, 1, 3, 5], "length": 10}

validate(
    name="Graph Validation",
    realized=graph.validate(),
    expected=None,
)

validate(
    name="Dijkstra",
    realized=graph.dijkstra(origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="Bellman-Ford",
    realized=graph.bellman_ford(origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="A*",
    realized=graph.a_star(
        origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=graph.bmssp(0, 5),
    expected=expected,
)

validate(
    name="Shortest Path Tree",
    realized=graph.get_tree_path(
        origin_id=0, 
        destination_id=5, 
        tree_data=graph.get_shortest_path_tree(origin_id=0)
    ),
    expected=expected,
)


print("\n===============\nDisconnected Graph Tests:\n===============")

graph = Graph([
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
    # Make a disconnected graph
    {7: 1},
    {8: 1},
    {6: 1},
])

expected = {"path": [0, 2, 1, 3, 5], "length": 10}

# This is not a connected or symmetric graph, both should raise errors
try:
    graph.validate(
        check_connected=True, check_symmetry=False
    )
    print("Graph Connection Check: Fail")
except Exception as e:
    print("Graph Connection Check: Pass")

try:
    graph.validate(
        check_connected=False, check_symmetry=True
    )
    print("Graph Symmetry Check: Fail")
except Exception as e:
    print("Graph Symmetry Check: Pass")

validate(
    name="Dijkstra",
    realized=graph.dijkstra(origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="Bellman-Ford",
    realized=graph.bellman_ford(origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="A*",
    realized=graph.a_star(
        origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=graph.bmssp(0, 5),
    expected=expected,
)

validate(
    name="Shortest Path Tree",
    realized=graph.get_tree_path(
        origin_id=0,
        destination_id=5,
        tree_data=graph.get_shortest_path_tree(origin_id=0),
    ),
    expected=expected,
)

empty_graph = Graph([])

try:
    # Empty graph should raise an exception regardless of checks, since it has no nodes
    empty_graph.validate(check_symmetry=True, check_connected=True)
    print("Empty Graph: Fail")
except Exception as e:
    print(f"Empty Graph: Pass")