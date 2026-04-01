import time
import random
import os
from scgraph.graph import Graph as PythonGraph
from scgraph.geograph import GeoGraph
from scgraph.utils import validate

random.seed(42)


def run_performance_test(name, graph, origin_id, destination_id):
    print(f"\n--- Testing {name} ---")
    print(f"Graph size: {len(graph.graph)} nodes")

    # Measure Dijkstra
    start_time = time.time()
    try:
        dijkstra_result = graph.dijkstra(origin_id, destination_id)
        dijkstra_time = time.time() - start_time
        print(f"Dijkstra time: {dijkstra_time:.4f}s")

        # Measure Dijkstra Buckets
        start_time = time.time()
        buckets_result = graph.dijkstra_buckets(origin_id, destination_id)
        buckets_time = time.time() - start_time
        print(f"Dijkstra Buckets time: {buckets_time:.4f}s")

        # Validate results
        validate(
            name=f"{name} - Dijkstra vs Dijkstra Buckets (Length)",
            realized=round(buckets_result["length"], 6),
            expected=round(dijkstra_result["length"], 6),
        )

        if buckets_time < dijkstra_time:
            print(
                f"SUCCESS: Dijkstra Buckets was {dijkstra_time / buckets_time:.2f}x faster than Dijkstra"
            )
        else:
            print(
                f"INFO: Dijkstra Buckets was {buckets_time / dijkstra_time:.2f}x slower than Dijkstra"
            )

        return dijkstra_time, buckets_time
    except Exception as e:
        print(f"Error testing {name}: {e}")
        import traceback

        traceback.print_exc()
        return None, None


print("\n===============\nDijkstra Buckets Performance Test:\n===============")

# 1. Custom Grid Graph Test (Integer)
size = 200
graph_data = []
for y in range(size):
    for x in range(size):
        node_id = x + y * size
        edges = {}
        if x + 1 < size:
            edges[node_id + 1] = random.randint(1, 10)
        if y + 1 < size:
            edges[node_id + size] = random.randint(1, 10)
        graph_data.append(edges)

grid_graph = PythonGraph(graph_data)
run_performance_test(
    "200x200 Grid (Int weights 1-10)", grid_graph, 0, size * size - 1
)

# 2. Custom Grid Graph Test (Float, some < 1)
size = 200
graph_data_float = []
for y in range(size):
    for x in range(size):
        node_id = x + y * size
        edges = {}
        if x + 1 < size:
            # Mostly >= 1, some small
            edges[node_id + 1] = random.uniform(0.1, 10.0)
        if y + 1 < size:
            edges[node_id + size] = random.uniform(0.1, 10.0)
        graph_data_float.append(edges)

grid_graph_float = PythonGraph(graph_data_float)
run_performance_test(
    "200x200 Grid (Float weights 0.1-10.0)",
    grid_graph_float,
    0,
    size * size - 1,
)

# 3. GeoGraph Tests (Original Float Weights)
geograph_files = [
    ("Marnet", "geographs/marnet.graphjson"),
    ("US Freeway", "geographs/us_freeway.graphjson"),
    (
        "World Highways and Marnet",
        "geographs/world_highways_and_marnet.graphjson",
    ),
]

for name, rel_path in geograph_files:
    if os.path.exists(rel_path):
        # Load GeoGraph
        geograph = GeoGraph.load_from_graphjson(rel_path)

        # Use Python Graph implementation
        py_graph = PythonGraph(geograph.graph)

        origin_id = 0
        destination_id = len(py_graph.graph) // 2

        run_performance_test(
            f"GeoGraph: {name} (Original Floats)",
            py_graph,
            origin_id,
            destination_id,
        )
    else:
        print(f"\nSkipping {name} - file not found at {rel_path}")

print("\nPerformance testing complete.")
