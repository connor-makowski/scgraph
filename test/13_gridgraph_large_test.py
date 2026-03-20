from scgraph.grid import GridGraph
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
    algorithm_fn="a_star",
    heuristic_fn="euclidean",
)
a_star_output_time = time() - a_star_output_start_time
print("A* Output Time: ", a_star_output_time * 1000, "ms")

# Gridgraph test for Dijkstra
dijkstra_output_start_time = time()
dijkstra_output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    cache=False,
    algorithm_fn="dijkstra",
)
dijkstra_output_time = time() - dijkstra_output_start_time
print("Dijkstra Output Time: ", dijkstra_output_time * 1000, "ms")

# # Gridgraph test for BMSSP
# bmssp_output_start_time = time()
# bmssp_output = gridGraph.get_shortest_path(
#     origin_node={"x": 10, "y": y_size - 10},
#     destination_node={"x": x_size - 10, "y": y_size - 10},
#     algorithm_fn="bmssp",
# )
# bmssp_output_time = time() - bmssp_output_start_time
# print("BMSSP Output Time: ", bmssp_output_time * 1000, "ms")

# Standard GridGraph test poplating the initial cache for the origin node
output_start_time = time()
output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    algorithm_fn="cached_shortest_path",
)
output_start_time = time() - output_start_time
print("Shortest Path Tree + Output Time: ", output_start_time * 1000, "ms")

cached_output_start_time = time()
cached_output = gridGraph.get_shortest_path(
    origin_node={"x": 10, "y": y_size - 10},
    destination_node={"x": x_size - 10, "y": y_size - 10},
    algorithm_fn="cached_shortest_path",
)
cached_output_time = time() - cached_output_start_time
print(
    "Cached Shortest Path Tree Output Time: ", cached_output_time * 1000, "ms"
)

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
# if hard_round(4, bmssp_output["length"]) != hard_round(
#     4, cached_output["length"]
# ):
#     success = False
if success:
    print("GridGraph + Cache Test: PASS")
else:
    print("GridGraph + Cache Test: FAIL")
