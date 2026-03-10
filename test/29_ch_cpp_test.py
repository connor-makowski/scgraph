from scgraph.cpp import CHGraph
from scgraph.utils import validate, hard_round


def test_ch_graph_cpp():
    print("Testing C++ CHGraph...")
    # Define an arbitrary graph
    graph_data = [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]

    # 1. Basic Search Test
    ch_graph = CHGraph(graph_data)

    # Test path 0 to 5
    # Standard Dijkstra says: {'path': [0, 2, 1, 3, 5], 'length': 10}
    output = ch_graph.search(origin_id=0, destination_id=5)
    expected = {"path": [0, 2, 1, 3, 5], "length": 10}
    validate("CHGraph search 0 to 5", output, expected)

    # Test path 5 to 0
    output = ch_graph.search(origin_id=5, destination_id=0)
    expected = {"path": [5, 3, 1, 2, 0], "length": 10}
    validate("CHGraph search 5 to 0", output, expected)

    # 2. Test with a larger path
    # Path 4 to 0: 4->3->1->2->0 (3+1+2+1 = 7) or 4->2->0 (8+1=9)
    output = ch_graph.search(origin_id=4, destination_id=0)
    expected = {"path": [4, 3, 1, 2, 0], "length": 7}
    validate("CHGraph search 4 to 0", output, expected)

    # 3. Test same node
    output = ch_graph.search(origin_id=2, destination_id=2)
    expected = {"path": [2], "length": 0}
    validate("CHGraph search 2 to 2", output, expected)


if __name__ == "__main__":
    try:
        from scgraph.cpp import CHGraph

        test_ch_graph_cpp()
    except ImportError:
        print("SCGraph C++ extension not found. Skipping C++ CHGraph tests.")
