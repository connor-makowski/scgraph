import time
import random
import os
from scgraph.graph import Graph as PythonGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False
from scgraph.geograph import GeoGraph
from scgraph.utils import validate

random.seed(42)


def run_performance_test(name, graph_data, origin_id, destination_id):
    print(f"\n--- Testing {name} ---")
    print(f"Graph size: {len(graph_data)} nodes")

    py_graph = PythonGraph(graph_data)

    # Measure Python Dijkstra
    start_time = time.time()
    py_dijkstra_result = py_graph.dijkstra(origin_id, destination_id)
    py_dijkstra_time = time.time() - start_time
    print(f"Python Dijkstra time: {py_dijkstra_time:.4f}s")

    # Measure Python Dijkstra Buckets
    start_time = time.time()
    py_buckets_result = py_graph.dijkstra_buckets(origin_id, destination_id)
    py_buckets_time = time.time() - start_time
    print(f"Python Dijkstra Buckets time: {py_buckets_time:.4f}s")

    validate(
        name=f"{name} - Python Dijkstra vs Buckets",
        realized=round(py_buckets_result["length"], 6),
        expected=round(py_dijkstra_result["length"], 6),
    )

    if py_buckets_time < py_dijkstra_time:
        print(
            f"SUCCESS (PY): Buckets was {py_dijkstra_time / py_buckets_time:.2f}x faster"
        )
    else:
        print(
            f"INFO (PY): Buckets was {py_buckets_time / py_dijkstra_time:.2f}x slower"
        )

    if HAS_CPP:
        cpp_graph = CppGraph(graph_data)

        # Measure C++ Dijkstra
        start_time = time.time()
        cpp_dijkstra_result = cpp_graph.dijkstra(origin_id, destination_id)
        cpp_dijkstra_time = time.time() - start_time
        print(f"C++ Dijkstra time: {cpp_dijkstra_time:.4f}s")

        # Measure C++ Dijkstra Buckets
        start_time = time.time()
        cpp_buckets_result = cpp_graph.dijkstra_buckets(
            origin_id, destination_id
        )
        cpp_buckets_time = time.time() - start_time
        print(f"C++ Dijkstra Buckets time: {cpp_buckets_time:.4f}s")

        validate(
            name=f"{name} - C++ Dijkstra vs Buckets",
            realized=round(cpp_buckets_result["length"], 6),
            expected=round(cpp_dijkstra_result["length"], 6),
        )

        validate(
            name=f"{name} - Python vs C++ Buckets",
            realized=round(cpp_buckets_result["length"], 6),
            expected=round(py_buckets_result["length"], 6),
        )

        if cpp_buckets_time < cpp_dijkstra_time:
            print(
                f"SUCCESS (CPP): Buckets was {cpp_dijkstra_time / cpp_buckets_time:.2f}x faster"
            )
        else:
            print(
                f"INFO (CPP): Buckets was {cpp_buckets_time / cpp_dijkstra_time:.2f}x slower"
            )

        print(
            f"Overall C++ Buckets Speedup over Python Buckets: {py_buckets_time / cpp_buckets_time:.2f}x"
        )

    return True


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

run_performance_test(
    "200x200 Grid (Int weights 1-10)", graph_data, 0, size * size - 1
)

# 2. Custom Grid Graph Test (Float, some < 1)
size = 200
graph_data_float = []
for y in range(size):
    for x in range(size):
        node_id = x + y * size
        edges = {}
        if x + 1 < size:
            edges[node_id + 1] = random.uniform(0.1, 10.0)
        if y + 1 < size:
            edges[node_id + size] = random.uniform(0.1, 10.0)
        graph_data_float.append(edges)

run_performance_test(
    "200x200 Grid (Float weights 0.1-10.0)",
    graph_data_float,
    0,
    size * size - 1,
)

# 3. GeoGraph Tests (Original Float Weights)
geograph_files = [
    ("Marnet", "geographs/marnet.graphjson"),
    ("US Freeway", "geographs/us_freeway.graphjson"),
]

for name, rel_path in geograph_files:
    if os.path.exists(rel_path):
        geograph = GeoGraph.load_from_graphjson(rel_path)
        run_performance_test(
            f"GeoGraph: {name} (Original Floats)",
            geograph.graph,
            0,
            len(geograph.graph) // 2,
        )
    else:
        print(f"\nSkipping {name} - file not found at {rel_path}")

print("\nPerformance testing complete.")
