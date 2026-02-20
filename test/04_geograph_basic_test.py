from scgraph import GeoGraph
from scgraph.utils import validate

print("\n===============\nBasic GeoGraph Tests:\n===============")
nodes = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
graph = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]

expected = {
    "coordinate_path": [[0, 0], [0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 1]],
    "length": 10,
}

my_graph = GeoGraph(nodes=nodes, graph=graph)

origin_node = {"latitude": 0, "longitude": 0}
destination_node = {"latitude": 2, "longitude": 1}

validate(
    name="GeoGraph Graph Validation",
    realized=my_graph.validate(),
    expected=None,
)

validate(
    name="GeoGraph Node Validation",
    realized=my_graph.validate_nodes(),
    expected=None,
)

validate(
    name="GeoGraph Shortest Path",
    realized=my_graph.get_shortest_path(
        origin_node=origin_node, destination_node=destination_node
    ),
    expected=expected,
)
