from scgraph.graph import Graph

graph = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
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

print(Graph.bmssp(
    graph=graph,
    origin_id=0,
    destination_id=4
))


print(Graph.bmssp(
    graph=graph,
    origin_id=0,
    destination_id=5
))
