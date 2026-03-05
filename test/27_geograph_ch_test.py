from scgraph import GeoGraph, CHGraph
from scgraph.geographs.marnet import marnet_geograph
from scgraph.utils import hard_round
import time


def test_geograph_ch():
    print("Testing GeoGraph with CHGraph...")

    # 1. Create a CHGraph from Marnet data
    graph_data = marnet_geograph.graph_object.graph
    nodes = marnet_geograph.nodes

    print("Preprocessing CHGraph...")
    ch_graph = CHGraph(graph_data)

    # 2. Create a GeoGraph using the CHGraph object
    ch_geograph = GeoGraph(
        graph=ch_graph,
        nodes=nodes,
        intermediate_nodes=marnet_geograph.intermediate_nodes,
    )

    # 3. Define test points
    # Singapore to Los Angeles approximately
    origin = {"latitude": 1.29027, "longitude": 103.851959}
    destination = {"latitude": 34.052235, "longitude": -118.243683}

    # 4. Compare results
    print("\nCalculating shortest path with standard GeoGraph (Dijkstra)...")
    res_std = marnet_geograph.get_shortest_path(
        origin, destination, get_intermediate_nodes=True
    )

    print("\nCalculating shortest path with CH GeoGraph...")
    # Specify algorithm_fn='get_shortest_path' to use CH search
    res_ch = ch_geograph.get_shortest_path(
        origin,
        destination,
        algorithm_fn="get_shortest_path",
        get_intermediate_nodes=True,
    )

    # 5. Validate
    len_std = hard_round(4, res_std["length"])
    len_ch = hard_round(4, res_ch["length"])

    if len_std == len_ch:
        print(f"PASS: Lengths match ({len_std})")
    else:
        print(f"FAIL: Lengths differ! Std: {len_std}, CH: {len_ch}")

    if res_std["coordinate_path"] == res_ch["coordinate_path"]:
        print("PASS: Coordinate paths match")
    else:
        print(f"FAIL: Coordinate paths differ!")
        print(f"Std coord path length: {len(res_std['coordinate_path'])}")
        print(f"CH coord path length: {len(res_ch['coordinate_path'])}")

    # Test another pair (more "on-graph" potentially)
    print("\nTesting another path (London to New York)...")
    origin2 = {"latitude": 51.5074, "longitude": -0.1278}
    destination2 = {"latitude": 40.7128, "longitude": -74.0060}

    res_std2 = marnet_geograph.get_shortest_path(
        origin2, destination2, get_intermediate_nodes=True
    )
    res_ch2 = ch_geograph.get_shortest_path(
        origin2,
        destination2,
        algorithm_fn="get_shortest_path",
        get_intermediate_nodes=True,
    )

    if hard_round(4, res_std2["length"]) == hard_round(4, res_ch2["length"]):
        print(f"PASS: Lengths match ({hard_round(4, res_std2['length'])})")
    else:
        print(
            f"FAIL: Lengths differ! Std: {res_std2['length']}, CH: {res_ch2['length']}"
        )

    if res_std2["coordinate_path"] == res_ch2["coordinate_path"]:
        print("PASS: Coordinate paths match")
    else:
        print("FAIL: Coordinate paths differ!")


if __name__ == "__main__":
    test_geograph_ch()
