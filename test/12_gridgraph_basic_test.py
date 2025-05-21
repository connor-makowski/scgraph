from scgraph import GridGraph
from time import time

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

output = gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 8},
    destination_node={"x": 8, "y": 8},
    output_coordinate_path="list_of_lists",
)

expected_output = {
    "length": 16.071,
    "coordinate_path": [
        [1, 8],
        [2, 7],
        [3, 6],
        [3, 5],
        [4, 4],
        [4, 3],
        [4, 2],
        [5, 2],
        [6, 2],
        [6, 3],
        [6, 4],
        [6, 5],
        [6, 6],
        [7, 7],
        [8, 8],
    ],
}

success = True
if output != expected_output:
    success = False

if success == False:
    print("Basic GridGraph Test: FAIL")
else:
    print("Basic GridGraph Test: PASS")
