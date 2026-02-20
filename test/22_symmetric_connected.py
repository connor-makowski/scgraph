from scgraph import Graph
from scgraph.utils import validate


print("\n===============\nSymmetry + Connectivity Validation Tests:\n===============")

symmetric_connected_graph = Graph([
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
])

try:
    symmetric_connected_graph.validate(check_symmetry=True, check_connected=True)
    print("Symmetric+Connected Graph - Both Checks: Pass")
except Exception as e:
    print(f"Symmetric+Connected Graph - Both Checks: Fail")

try:
    symmetric_connected_graph.validate(check_symmetry=True, check_connected=False)
    print("Symmetric+Connected Graph - Symmetry Only: Pass")
except Exception as e:
    print(f"Symmetric+Connected Graph - Symmetry Only: Fail")

try:
    symmetric_connected_graph.validate(check_symmetry=False, check_connected=True)
    print("Symmetric+Connected Graph - Connected Only: Pass")
except Exception as e:
    print(f"Symmetric+Connected Graph - Connected Only: Fail")

# Asymmetric but connected: only symmetry check should fail
# Node 0->1 has weight 5, but 1->0 has weight 99 (asymmetric)
asymmetric_connected_graph = Graph([
    {1: 5, 2: 1},
    {0: 99, 2: 2, 3: 1},   # 1->0 is 99, not 5
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
])

try:
    asymmetric_connected_graph.validate(check_symmetry=True, check_connected=False)
    print("Asymmetric Graph - Symmetry Check: Fail")
except Exception as e:
    print("Asymmetric Graph - Symmetry Check: Pass")

try:
    asymmetric_connected_graph.validate(check_symmetry=False, check_connected=True)
    print("Asymmetric Graph - Connected Check (should pass): Pass")
except Exception as e:
    print(f"Asymmetric Graph - Connected Check (should pass): Fail")

# Symmetric but disconnected: only connectivity check should fail
# Nodes 6/7 are their own symmetric island, unreachable from node 0
symmetric_disconnected_graph = Graph([
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
    {7: 3},   # island
    {6: 3},   # island
])

try:
    symmetric_disconnected_graph.validate(check_symmetry=True, check_connected=False)
    print("Disconnected Graph - Symmetry Check (should pass): Pass")
except Exception as e:
    print(f"Disconnected Graph - Symmetry Check (should pass): Fail")

try:
    symmetric_disconnected_graph.validate(check_symmetry=False, check_connected=True)
    print("Disconnected Graph - Connected Check: Fail")
except Exception as e:
    print("Disconnected Graph - Connected Check: Pass")

# One-directional disconnection: reachable from 0 but not back
# This catches the inverse-graph traversal logic specifically
# Node 0 can reach node 2, but node 2 has no path back to node 0
one_way_disconnected_graph = Graph([
    {1: 5},    # 0 -> 1 only
    {2: 2},    # 1 -> 2 only
    {3: 4},    # 2 -> 3 only
    {},        # 3 is a sink
])

try:
    one_way_disconnected_graph.validate(check_symmetry=False, check_connected=True)
    print("One-Way Disconnected Graph - Connected Check: Fail")
except Exception as e:
    print("One-Way Disconnected Graph - Connected Check: Pass")
