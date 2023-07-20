import time
from scgraph import Graph

def validate(name, realized, expected):
    if realized == expected:
        print(f'{name}: PASS')
    else:
        print(f'{name}: FAIL')
        print('Expected:', expected)
        print('Realized:', realized)

print('\n===============\nBasic Graph Tests:\n===============')

graph = {
    0:{1: 5, 2: 1},
    1:{0: 5, 2: 2, 3: 1},
    2:{0: 1, 1: 2, 3: 4, 4: 8},
    3:{1: 1, 2: 4, 4: 3, 5: 6},
    4:{2: 8, 3: 3},
    5:{3: 6}
}

expected = {
    "path": [0, 2, 1, 3, 5],
    "length": 10
}

validate(
    name='Graph Validation',
    realized = Graph.validate_graph(graph=graph),
    expected = None
)

validate(
    name='Dijkstra', 
    realized = Graph.dijkstra(graph=graph, origin_id=0, destination_id=5), 
    expected = expected
)

validate(
    name='Dijkstra-Makowski',
    realized = Graph.dijkstra_makowski(graph=graph, origin_id=0, destination_id=5),
    expected = expected
)