from scgraph.bmssp import BMSSP

from scgraph.graph import Graph

graph = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
    # Uncomment this and the BMSSP algorithm breaks
    # {7: 1},
    # {8: 1},
    # {6: 1},
]

print(Graph.dijkstra_makowski(
    graph=graph,
    origin_id=0,
    destination_id=4
))

print(Graph.dijkstra_makowski(
    graph=graph,
    origin_id=0,
    destination_id=5
))

print(BMSSP(
    graph=graph,
    origin_id=0,
    destination_id=4
))


print(BMSSP(
    graph=graph,
    origin_id=0,
    destination_id=5
))
