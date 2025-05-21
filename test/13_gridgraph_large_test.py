from scgraph import GridGraph
from time import time

print("\n===============\nCache + GridGraph Tests:\n===============")

x_size = 300
y_size = 300
blocks = [(5, i) for i in range(3, y_size)]
shape = [(0, 0), (0, 1), (1, 0), (1, 1)]

graph_creating_start_time = time()
gridGraph = GridGraph(
    x_size=x_size,
    y_size=y_size,
    blocks=blocks,
    shape=shape,
    add_exterior_walls=True,
)
graph_creation_time = time() - graph_creating_start_time
print("300x300 Graph Creation Time: ", graph_creation_time)

output_start_time = time()
output = gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 290},
    destination_node={"x": 290, "y": 290},
    cache=True,
    cache_for="origin",
)
output_start_time = time() - output_start_time
print("Initial Output Time: ", output_start_time)

cached_output_start_time = time()
cached_output = gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 290},
    destination_node={"x": 290, "y": 291},
    cache=True,
    cache_for="origin",
)
cached_output_time = time() - cached_output_start_time
print("Cached Output Time: ", cached_output_time)

print("")

if cached_output_time > 0.005:
    print("GridGraph + Cache Test: FAIL")
else:
    print("GridGraph + Cache Test: PASS")
