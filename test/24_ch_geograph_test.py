from scgraph.geographs.marnet import marnet_geograph
from scgraph.graph import Graph
from scgraph import CHGraph
from scgraph.utils import validate, hard_round
import time


def test_ch_marnet():
    print("Testing CHGraph with Marnet Geograph...")

    # Extract the underlying graph data
    graph_data = marnet_geograph.graph_object.graph

    # 1. Initialization (Pre-processing)
    print("Preprocessing CHGraph (this may take a few seconds)...")
    start_pre = time.time()
    ch_graph = CHGraph(graph_data)
    print(f"Preprocessing took {time.time() - start_pre:.2f} seconds.")

    # Standard Graph for comparison
    standard_graph = Graph(graph_data)

    # 2. Compare Dijkstra vs CH search for several pairs
    # (origin_id, destination_id)
    test_pairs = [
        (0, 100),
        (500, 1500),
        (2000, 3000),
        (10, 5000),
        (123, 456),
        (800, 200),
    ]

    for origin, dest in test_pairs:
        print(f"\nTesting path from {origin} to {dest}:")

        # Dijkstra
        start_d = time.time()
        d_res = standard_graph.dijkstra(origin, dest)
        d_time = time.time() - start_d

        # CH Search
        start_ch = time.time()
        ch_res = ch_graph.search(origin, dest)
        ch_time = time.time() - start_ch

        # Check if lengths match (round to avoid float issues)
        d_len = hard_round(4, d_res["length"])
        ch_len = hard_round(4, ch_res["length"])

        if d_len == ch_len:
            print(f"PASS: Lengths match ({d_len})")
            print(f"Dijkstra: {d_time*1000:.2f}ms, CH: {ch_time*1000:.2f}ms")
            print(f"Speedup: {d_time/ch_time:.1f}x")
        else:
            print(f"FAIL: Dijkstra length {d_len}, CH length {ch_len}")
            # Optional: compare paths if they differ but lengths match (can happen if multiple shortest paths exist)


if __name__ == "__main__":
    test_ch_marnet()
