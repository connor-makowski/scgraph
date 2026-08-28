#!/usr/bin/env python3
import time
import random
from scgraph.geograph import GeoGraph
from scgraph.grid import GridGraph
from scgraph.contraction_hierarchies import CHGraph as PyCHGraph
from scgraph.transit_node_routing import TNRGraph as PyTNRGraph

try:
    from scgraph.cpp import CHGraph as CppCHGraph, TNRGraph as CppTNRGraph
    HAS_CPP = True
except ImportError:
    HAS_CPP = False

def run_bench(name, fn, *args, **kwargs):
    print(f"  Starting: {name} ...", flush=True)
    start = time.perf_counter()
    res = fn(*args, **kwargs)
    duration = time.perf_counter() - start
    print(f"  Finished: {name} in {duration*1000:.2f} ms", flush=True)
    return duration, res

def benchmark_graph(graph_name, adj_list):
    num_nodes = len(adj_list)
    print(f"\n--- Benchmarking Graph: {graph_name} ({num_nodes} nodes) ---", flush=True)
    random.seed(42)
    
    num_queries = 20
    queries = []
    for _ in range(num_queries):
        u = random.randint(0, num_nodes - 1)
        v = random.randint(0, num_nodes - 1)
        while u == v:
            v = random.randint(0, num_nodes - 1)
        queries.append((u, v))

    # Python CH (only for smaller graphs)
    # Python CH
    py_ch_prep_time, py_ch = run_bench("Python CH Preprocessing", PyCHGraph, adj_list)
    # Find queries with valid paths using Py CH
    successful_queries = []
    py_ch_query_times = []
    for u, v in queries:
        try:
            start = time.perf_counter()
            py_ch.search(u, v)
            py_ch_query_times.append(time.perf_counter() - start)
            successful_queries.append((u, v))
        except Exception:
            pass

    # Baseline Dijkstra (Python)
    from scgraph.graph import Graph as PyGraph
    py_base_graph = PyGraph(adj_list)
    py_dijkstra_query_times = []
    for u, v in successful_queries:
        try:
            start = time.perf_counter()
            py_base_graph.dijkstra(u, v)
            py_dijkstra_query_times.append(time.perf_counter() - start)
        except Exception:
            pass
    if py_dijkstra_query_times:
        print(f"  Python Dijkstra Baseline Avg (x{len(py_dijkstra_query_times)}) : {sum(py_dijkstra_query_times)/len(py_dijkstra_query_times)*1000:.2f} ms", flush=True)

    py_bidirectional_query_times = []
    for u, v in successful_queries:
        try:
            start = time.perf_counter()
            py_base_graph.bidirectional_dijkstra(u, v)
            py_bidirectional_query_times.append(time.perf_counter() - start)
        except Exception:
            pass
    if py_bidirectional_query_times:
        print(f"  Python Bidirectional Dijkstra Avg (x{len(py_bidirectional_query_times)}) : {sum(py_bidirectional_query_times)/len(py_bidirectional_query_times)*1000:.2f} ms", flush=True)

    if py_ch_query_times:
        print(f"  Finished: Python CH Queries Avg (x{len(successful_queries)}) : {sum(py_ch_query_times)/len(successful_queries)*1000:.2f} ms", flush=True)
    else:
        print("  Python CH: No successful queries found")

    # Python TNR
    if num_nodes <= 12000:
        py_tnr_prep_time, py_tnr = run_bench("Python TNR Preprocessing", PyTNRGraph, adj_list, num_transit_nodes=100)
        print("  Starting: Python TNR Queries ...", flush=True)
        py_tnr_query_times = []
        for u, v in successful_queries:
            try:
                start = time.perf_counter()
                py_tnr.search(u, v)
                py_tnr_query_times.append(time.perf_counter() - start)
            except Exception:
                pass
        if py_tnr_query_times:
            print(f"  Finished: Python TNR Queries Avg (x{len(py_tnr_query_times)}) : {sum(py_tnr_query_times)/len(py_tnr_query_times)*1000:.2f} ms", flush=True)
    else:
        print(f"  Skipping Python TNR Preprocessing (graph too large: {num_nodes} nodes)", flush=True)

    if HAS_CPP:
        # C++ Dijkstra Baseline
        from scgraph.cpp import Graph as CppGraph
        cpp_base_graph = CppGraph(adj_list)
        cpp_dijkstra_query_times = []
        for u, v in successful_queries:
            try:
                start = time.perf_counter()
                cpp_base_graph.dijkstra(u, v)
                cpp_dijkstra_query_times.append(time.perf_counter() - start)
            except Exception:
                pass
        if cpp_dijkstra_query_times:
            print(f"  C++ Dijkstra Baseline Avg (x{len(cpp_dijkstra_query_times)})    : {sum(cpp_dijkstra_query_times)/len(cpp_dijkstra_query_times)*1000:.2f} ms", flush=True)

        cpp_bidirectional_query_times = []
        for u, v in successful_queries:
            try:
                start = time.perf_counter()
                cpp_base_graph.bidirectional_dijkstra(u, v)
                cpp_bidirectional_query_times.append(time.perf_counter() - start)
            except Exception:
                pass
        if cpp_bidirectional_query_times:
            print(f"  C++ Bidirectional Dijkstra Avg (x{len(cpp_bidirectional_query_times)})    : {sum(cpp_bidirectional_query_times)/len(cpp_bidirectional_query_times)*1000:.2f} ms", flush=True)

        # C++ CH
        # For very large graphs like world highways (300k+ nodes), even C++ preprocessing can be slow/memory intensive.
        # Let's log it clearly.
        cpp_ch_prep_time, cpp_ch = run_bench("C++ CH Preprocessing", CppCHGraph, adj_list)
        
        print("  Starting: C++ CH Queries ...", flush=True)
        cpp_ch_query_times = []
        for u, v in successful_queries:
            try:
                start = time.perf_counter()
                cpp_ch.search(u, v)
                cpp_ch_query_times.append(time.perf_counter() - start)
            except Exception:
                pass
        if cpp_ch_query_times:
            print(f"  Finished: C++ CH Queries Avg (x{len(cpp_ch_query_times)}) : {sum(cpp_ch_query_times)/len(cpp_ch_query_times)*1000:.2f} ms", flush=True)

        # C++ TNR
        cpp_tnr_prep_time, cpp_tnr = run_bench("C++ TNR Preprocessing", CppTNRGraph, adj_list, num_transit_nodes=100)
        
        print("  Starting: C++ TNR Queries ...", flush=True)
        cpp_tnr_query_times = []
        for u, v in successful_queries:
            try:
                start = time.perf_counter()
                cpp_tnr.search(u, v, length_only=False)
                cpp_tnr_query_times.append(time.perf_counter() - start)
            except Exception:
                pass
        if cpp_tnr_query_times:
            print(f"  Finished: C++ TNR Queries Avg (x{len(cpp_tnr_query_times)}) : {sum(cpp_tnr_query_times)/len(cpp_tnr_query_times)*1000:.2f} ms", flush=True)

def main():
    print(f"C++ Extension available: {HAS_CPP}", flush=True)
    
    # 1. Marnet
    print("\nLoading Marnet...", flush=True)
    marnet = GeoGraph.load_geograph("marnet")
    benchmark_graph("marnet", marnet.graph)

    # 2. GridGraphs
    for size in [100]:
        print(f"\nGenerating GridGraph {size}x{size}...", flush=True)
        blocks = [(size//2, i) for i in range(5, size)]
        shape = [(0, 0), (0, 1), (1, 0), (1, 1)]
        grid = GridGraph(
            x_size=size,
            y_size=size,
            blocks=blocks,
            shape=shape,
            add_exterior_walls=True,
        )
        benchmark_graph(f"grid_{size}x{size}", grid.graph)

if __name__ == "__main__":
    main()
