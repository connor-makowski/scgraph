from scgraph import GridGraph
from time import time

print("\n===============\nGridGraph Import Export Tests:\n===============")

print_timings = True

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
if print_timings:
    print(
        f"GridGraph Creation Time: {(time() - graph_creating_start_time)*1000:.6f} ms"
    )

first_shortest_path_start_time = time()
output = gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 8},
    destination_node={"x": 8, "y": 8},
    output_coordinate_path="list_of_lists",
    cache=True,
    cache_for="origin",
)
if print_timings:
    print(
        f"GridGraph First Shortest Path Time: {(time() - first_shortest_path_start_time)*1000:.6f} ms"
    )

# Export the graph to a file
export_start_time = time()
gridGraph.export_object(
    filename="/tmp/export",
)
if print_timings:
    print(f"GridGraph Export Time: {(time() - export_start_time)*1000:.6f} ms")

import_start_time = time()
new_gridGraph = GridGraph.import_object(
    filename="/tmp/export",
)
if print_timings:
    print(f"GridGraph Import Time: {(time() - import_start_time)*1000:.6f} ms")

imported_shortest_path_start_time = time()
output = new_gridGraph.get_shortest_path(
    origin_node={"x": 1, "y": 8},
    destination_node={"x": 8, "y": 8},
    output_coordinate_path="list_of_lists",
)
imported_shortest_path_time = time() - imported_shortest_path_start_time
if print_timings:
    print(
        f"GridGraph Imported Shortest Path Time: {(imported_shortest_path_time)*1000:.6f} ms"
    )

success = True
if (
    imported_shortest_path_time > 0.001
):  # liberal 1ms threshold - It normally clocks around 40µs
    print(
        "Imported shortest path time is too long - Check if the graph was cached / imported correctly"
    )
    print("GridGraph Import Export Test: FAIL")
    success = False

if success == False:
    print("GridGraph Import Export Test: FAIL")
else:
    print("GridGraph Import Export Test: PASS")
