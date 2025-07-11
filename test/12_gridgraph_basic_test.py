from scgraph import GridGraph
from time import time
from scgraph.utils import hard_round

print("\n===============\nGridGraph Tests:\n===============")

x_size = 11
y_size = 10
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

# Since heuristic_fn is not specified, the gridGraph will default to using Dijkstra-Makowski
output = gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 8},
    destination_node={"x": 8, "y": 8},
    output_coordinate_path="list_of_lists",
)

# Specify a euclidean heuristic function to use the A*-Makowski algorithm
output_a_star = gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 8},
    destination_node={"x": 8, "y": 8},
    output_coordinate_path="list_of_lists",
    heuristic_fn='euclidean',
)

expected_output = 16.071

success = True
if hard_round(4, output['length']) != expected_output:
    success = False
if hard_round(4, output_a_star['length']) != expected_output:
    success = False

if success:
    print("Basic GridGraph Test: PASS")
else:
    print("Basic GridGraph Test: FAIL")
