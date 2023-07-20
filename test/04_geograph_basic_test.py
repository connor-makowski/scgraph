import time
from scgraph import GeoGraph, Graph

def validate(name, realized, expected):
    if realized == expected:
        print(f'{name}: PASS')
    else:
        print(f'{name}: FAIL')
        print('Expected:', expected)
        print('Realized:', realized)

print('\n===============\nBasic GeoGraph Tests:\n===============')
nodes = {
    0: {"latitude": 0, "longitude": 0},
    1: {"latitude": 0, "longitude": 1},
    2: {"latitude": 1, "longitude": 0},
    3: {"latitude": 1, "longitude": 1},
    4: {"latitude": 1, "longitude": 2},
    5: {"latitude": 2, "longitude": 1}
}
graph = {
    0:{1: 5, 2: 1},
    1:{0: 5, 2: 2, 3: 1},
    2:{0: 1, 1: 2, 3: 4, 4: 8},
    3:{1: 1, 2: 4, 4: 3, 5: 6},
    4:{2: 8, 3: 3},
    5:{3: 6}
}

expected = {
    "path": [6, 0, 2, 1, 3, 5, 7],
    "coordinate_path": [
        {'latitude': 0, 'longitude': 0},
        {'latitude': 0, 'longitude': 0},
        {'latitude': 1, 'longitude': 0},
        {'latitude': 0, 'longitude': 1},
        {'latitude': 1, 'longitude': 1},
        {'latitude': 2, 'longitude': 1},
        {'latitude': 2, 'longitude': 1}
    ],
    "length": 10
}

my_graph = GeoGraph(nodes=nodes, graph=graph)

origin_node = {'latitude': 0, 'longitude': 0}
destination_node = {'latitude': 2, 'longitude': 1}

validate(
    name='GeoGraph Graph Validation',
    realized = my_graph.validate_graph(),
    expected = None
)

validate(
    name='GeoGraph Node Validation',
    realized = my_graph.validate_nodes(),
    expected = None
)

validate(
    name='GeoGraph Shortest Path', 
    realized = my_graph.get_shortest_path(
        origin_node = origin_node,
        destination_node = destination_node
    ), 
    expected = expected
)