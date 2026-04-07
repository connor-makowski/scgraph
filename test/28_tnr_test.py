from scgraph import GeoGraph, TNRGraph
import time, os


def test_tnr_basic():
    print("Testing TNR Basic...")
    # Small test graph
    graph = [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]
    tnr = TNRGraph(graph=graph, num_transit_nodes=2)

    # Test point to point
    res = tnr.get_shortest_path(0, 5)
    print(f"Path: {res['path']}, Length: {res['length']}")
    assert res["length"] == 10
    assert res["path"] == [0, 2, 1, 3, 5]
    print("TNR Basic Passed!")


def test_tnr_geograph():
    print("\nTesting TNR with GeoGraph (Marnet)...")
    from scgraph.graph import Graph

    marnet = GeoGraph.load_geograph("marnet")
    # Force use of Python Graph object for this test
    marnet.graph_object = Graph(graph=marnet.graph)

    # Preprocess TNR with 100 transit nodes
    start_time = time.time()
    marnet.graph_object.create_tnr_hierarchy(num_transit_nodes=100)
    print(f"TNR Preprocessing took: {time.time() - start_time:.2f}s")

    # Shanghai to Savannah
    origin = {"latitude": 31.23, "longitude": 121.47}
    destination = {"latitude": 32.08, "longitude": -81.09}

    # Standard Dijkstra for baseline
    start_time = time.time()
    dijkstra_res = marnet.get_shortest_path(
        origin, destination, algorithm_fn="dijkstra"
    )
    dijkstra_time = time.time() - start_time
    print(
        f"Dijkstra took: {dijkstra_time:.4f}s, Length: {dijkstra_res['length']}"
    )

    # Contraction Hierarchy for comparison
    marnet.graph_object.create_contraction_hierarchy()
    start_time = time.time()
    ch_res = marnet.get_shortest_path(
        origin, destination, algorithm_fn="contraction_hierarchy"
    )
    ch_time = time.time() - start_time
    print(
        f"CH (path) took: {ch_time:.4f}s, Length: {ch_res['length']}"
    )

    # TNR
    start_time = time.time()
    tnr_res = marnet.get_shortest_path(origin, destination, algorithm_fn="tnr")
    tnr_time = time.time() - start_time
    print(f"TNR (path) took: {tnr_time:.4f}s, Length: {tnr_res['length']}")

    # TNR length only (should be ~O(1))
    start_time = time.time()
    tnr_len_res = marnet.get_shortest_path(origin, destination, algorithm_fn="tnr", length_only=True)
    tnr_len_time = time.time() - start_time
    print(f"TNR (length_only) took: {tnr_len_time:.4f}s, Length: {tnr_len_res['length']}")

    # Verify results are close (floating point)
    assert abs(dijkstra_res["length"] - tnr_res["length"]) < 1e-3
    assert abs(dijkstra_res["length"] - ch_res["length"]) < 1e-3
    assert abs(dijkstra_res["length"] - tnr_len_res["length"]) < 1e-3
    print(f"TNR Speedup over Dijkstra (path): {dijkstra_time / tnr_time:.2f}x")
    print(f"TNR Speedup over CH (path): {ch_time / tnr_time:.2f}x")
    print(f"TNR Speedup over CH (length_only): {ch_time / tnr_len_time:.2f}x")
    print("TNR GeoGraph Passed!")


def test_tnr_save_load():
    print("\nTesting TNR Save/Load...")
    graph = [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]
    tnr = TNRGraph(graph=graph, num_transit_nodes=2)
    tnr.save_as_tnrjson("test_tnr.tnrjson")

    tnr_loaded = TNRGraph.load_from_tnrjson("test_tnr.tnrjson")
    res = tnr_loaded.get_shortest_path(0, 5)
    assert res["length"] == 10
    os.remove("test_tnr.tnrjson")
    
    print("TNR Save/Load Passed!")


if __name__ == "__main__":
    test_tnr_basic()
    test_tnr_geograph()
    test_tnr_save_load()
