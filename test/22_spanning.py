import time
from pamda import pamda
from scgraph.grid import GridGraph
from scgraph.geographs.marnet import graph as marnet_graph
from scgraph.geographs.us_freeway import graph as us_freeway_graph

from scgraph_data.world_highways_and_marnet import graph as world_highways_and_marnet_graph
from scgraph.spanning import SpanningTree



print("\n===============\nCPP vs Python Tests:\n===============")


def validate(name, realized, expected):
    if realized == expected:
        print(f"{name}: PASS")
    else:
        print(f"{name}: FAIL")
        print("Expected:", expected)
        print("Realized:", realized)


def time_test(name, thunk):
    start = time.time()
    thunk()
    print(f"{name}: {round((time.time()-start)*1000, 4)}ms")


graph = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


validate(
    name="Spanning Tree: CPP vs Python Basic",
    realized=SpanningTree.makowskis_spanning_tree(graph, 1, use_cpp=True),
    expected=SpanningTree.makowskis_spanning_tree(graph, 1),
)

c_shortest_path_tree_marnet = SpanningTree.makowskis_spanning_tree(graph=marnet_graph, node_id=1, use_cpp=True)
py_shortest_path_tree_marnet = SpanningTree.makowskis_spanning_tree(graph=marnet_graph, node_id=1)

validate(
    name="Spanning Tree: CPP vs Python Marnet",
    realized=SpanningTree.makowskis_spanning_tree(graph=marnet_graph, node_id=1, use_cpp=True),
    expected=SpanningTree.makowskis_spanning_tree(graph=marnet_graph, node_id=1),
)

print("\n===============\nCPP vs Python Time Tests:\n===============")

# Basic Graph
time_test(
    "Shortest Path Tree Comparison (basic - CPP)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=graph, node_id=0, use_cpp=True
    ),
)

time_test(
    "Shortest Path Tree Comparison (basic - python)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=graph, node_id=0
    ),
)

# Marnet Graph
time_test(
    "Shortest Path Tree Comparison (marnet - CPP)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=marnet_graph, node_id=0, use_cpp=True
    ),
)

time_test(
    "Shortest Path Tree Comparison (marnet - python)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=marnet_graph, node_id=0
    ),
)

# US Freeway Graph
time_test(
    "Shortest Path Tree Comparison (us_freeway - CPP)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=us_freeway_graph, node_id=0, use_cpp=True
    ),
)
time_test(
    "Shortest Path Tree Comparison (us_freeway - python)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=us_freeway_graph, node_id=0
    ),
)

# World Highways and Marnet Graph
time_test(
    "Shortest Path Tree Comparison (world_highways_and_marnet - CPP)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=world_highways_and_marnet_graph, node_id=0, use_cpp=True
    ),
)
time_test(
    "Shortest Path Tree Comparison (world_highways_and_marnet - python)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=world_highways_and_marnet_graph, node_id=0
    ),
)

# Huge Gridgraph
x_size = 500
y_size = 500
blocks = [(150, i) for i in range(5, y_size)]
shape = [(0, 0), (0, 1), (1, 0), (1, 1)]

gridGraph = GridGraph(
    x_size=x_size,
    y_size=y_size,
    blocks=blocks,
    shape=shape,
    add_exterior_walls=True,
)

time_test(
    f"Shortest Path Tree Comparison ({x_size}x{y_size} grid - CPP)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=gridGraph.graph, node_id=0, use_cpp=True
    ),
)

time_test(
    f"Shortest Path Tree Comparison ({x_size}x{y_size} grid - python)",
    pamda.thunkify(SpanningTree.makowskis_spanning_tree)(
        graph=gridGraph.graph, node_id=0
    ),
)