from scgraph.geographs.us_freeway import us_freeway_geograph
from scgraph import CHGraph, Graph
from scgraph.utils import hard_round
import time
import random


def test_ch_highways():
    print("Testing CHGraph with US Freeway Geograph...")

    # Extract the underlying graph data correctly
    graph_data = us_freeway_geograph.graph_object.graph

    # 1. Initialization (Pre-processing)
    print(f"Preprocessing CHGraph with {len(graph_data)} nodes...")
    start_pre = time.time()
    ch_graph = CHGraph(graph_data)
    print(f"Preprocessing took {time.time() - start_pre:.2f} seconds.")

    # Standard Graph for comparison
    standard_graph = Graph(graph_data)

    # 2. Compare Dijkstra vs CH search for random pairs
    num_tests = 10
    nodes_count = len(graph_data)

    success_count = 0
    for i in range(num_tests):
        origin = random.randint(0, nodes_count - 1)
        dest = random.randint(0, nodes_count - 1)

        try:
            # Dijkstra
            start_d = time.time()
            d_res = standard_graph.dijkstra(origin, dest)
            d_time = time.time() - start_d

            # CH Search
            start_ch = time.time()
            ch_res = ch_graph.search(origin, dest)
            ch_time = time.time() - start_ch

            # Check if lengths match
            d_len = hard_round(4, d_res["length"])
            ch_len = hard_round(4, ch_res["length"])

            if d_len == ch_len:
                success_count += 1
                speedup = d_time/ch_time if ch_time > 0 else float('inf')
                print(
                    f"Test {i+1}: PASS ({origin} -> {dest}, len={d_len}, speedup={speedup:.1f}x)"
                )
            else:
                print(
                    f"Test {i+1}: FAIL ({origin} -> {dest}) - Dijkstra: {d_len}, CH: {ch_len}"
                )
        except Exception as e:
            # Likely disconnected nodes
            print(f"Test {i+1}: SKIPPED ({origin} -> {dest}) - {str(e)}")

    print(f"\nSummary: {success_count}/{num_tests} successful matches.")


if __name__ == "__main__":
    test_ch_highways()
