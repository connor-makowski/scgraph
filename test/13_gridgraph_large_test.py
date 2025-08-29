from scgraph import GridGraph
from scgraph.graph import Graph
from time import time
from scgraph.utils import hard_round

print("\n===============\nCache + GridGraph Tests:\n===============")

x_size = 300
y_size = 300
blocks = [(150, i) for i in range(5, y_size)]
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
print(
    f"{x_size}x{y_size} Graph Creation Time: ", graph_creation_time * 1000, "ms"
)

# Gridgraph test for A*
a_star_output_start_time = time()
a_star_output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    algorithm_fn=Graph.a_star,
    heuristic_fn="euclidean",
)
a_star_output_time = time() - a_star_output_start_time
print("A* Output Time: ", a_star_output_time * 1000, "ms")

# Gridgraph test for Dijkstra-Modified
dijkstra_output_start_time = time()
dijkstra_output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    cache=False,
    algorithm_fn=Graph.dijkstra_makowski,
)
dijkstra_output_time = time() - dijkstra_output_start_time
print("Dijkstra-Modified Output Time: ", dijkstra_output_time * 1000, "ms")

# Gridgraph test for BMSSP
bmssp_output_start_time = time()
bmssp_output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    algorithm_fn=Graph.bmssp,
)
bmssp_output_time = time() - bmssp_output_start_time
print("BMSSP Output Time: ", bmssp_output_time * 1000, "ms")

# Standard GridGraph test poplating the initial cache for the origin node
output_start_time = time()
output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    cache=True,
    cache_for="origin",
)
output_start_time = time() - output_start_time
print("Spanning Tree + Output Time: ", output_start_time * 1000, "ms")

cached_output_start_time = time()
cached_output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    cache=True,
    cache_for="origin",
)
cached_output_time = time() - cached_output_start_time
print("Cached Spanning Tree Output Time: ", cached_output_time * 1000, "ms")

print("")

success = True
if cached_output_time > 0.005:
    success = False
if hard_round(4, dijkstra_output["length"]) != hard_round(
    4, a_star_output["length"]
):
    success = False
if hard_round(4, a_star_output["length"]) != hard_round(
    4, cached_output["length"]
):
    success = False
if hard_round(4, output["length"]) != hard_round(4, cached_output["length"]):
    success = False
if hard_round(4, bmssp_output["length"]) != hard_round(
    4, cached_output["length"]
):
    success = False
if success:
    print("GridGraph + Cache Test: PASS")
else:
    print("GridGraph + Cache Test: FAIL")
