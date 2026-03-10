from scgraph import CHGraph
from scgraph.utils import validate
import os
import json


def test_ch_save_load():
    print("Testing CHGraph Save/Load...")
    # Define an arbitrary graph
    graph_data = [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]

    # 1. Create and Save
    ch_graph = CHGraph(graph_data)
    filename = "test_graph.chjson"
    ch_graph.save_as_chjson(filename)
    print(f"Saved to {filename}")

    # 2. Load
    loaded_ch = CHGraph.load_from_chjson(filename)
    print(f"Loaded from {filename}")

    # 3. Compare Ranks
    if ch_graph.ranks == loaded_ch.ranks:
        print("PASS: Ranks match")
    else:
        print("FAIL: Ranks do not match")

    # 4. Compare Search Results
    output_orig = ch_graph.search(0, 5)
    output_load = loaded_ch.search(0, 5)

    validate("CHGraph Save/Load Search Result", output_load, output_orig)

    # 5. Load without original graph (optional but supported for search)
    # We need to manually remove original_graph from the file to test this or have a load method that supports it
    with open(filename, "r") as f:
        data = json.load(f)
    data["original_graph"] = None
    with open("test_no_orig.chjson", "w") as f:
        json.dump(data, f)

    loaded_no_orig = CHGraph.load_from_chjson("test_no_orig.chjson")
    output_no_orig = loaded_no_orig.search(0, 5)
    validate("CHGraph Load No Orig Search Result", output_no_orig, output_orig)

    # Cleanup
    if os.path.exists(filename):
        os.remove(filename)
    if os.path.exists("test_no_orig.chjson"):
        os.remove("test_no_orig.chjson")


if __name__ == "__main__":
    test_ch_save_load()
