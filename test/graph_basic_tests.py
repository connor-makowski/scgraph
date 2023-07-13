import time
from scgraph import Graph
from scgraph.data import example_data

print('\n===============\nBasic Tests:\n===============')

print ('\nTest 1: Basic manually passed graph and raw dijkstra fn')
data = {
    "nodes": {},
    "graph": {
        "0":{"1": 5, "2": 1},
        "1":{"0": 5, "2": 2, "3": 1},
        "2":{"0": 1, "1": 2, "3": 4, "4": 8},
        "3":{"1": 1, "2": 4, "4": 3, "5": 6},
        "4":{"2": 8, "3": 3},
        "5":{"3": 6}
    }
}

# Skipping Nodes input for this test
my_graph = Graph(data=data)

my_graph.validate_graph()

expected = {
    'path_ids': ["0", "2", "1", "3", "5"],
    'length': 10
}

actual = my_graph.dijkstra(origin="0", destination="5")

if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)


print ('\nTest 2: Basic graph with example data')
my_graph = Graph(data=example_data)

my_graph.validate_graph()
my_graph.validate_nodes()

actual = my_graph.get_shortest_path(
    origin={
        "latitude": 1.0,
        "longitude": 0.0
    }, 
    destination={
        "latitude": 1.0,
        "longitude": 1.0
    }
)

expected = {
    'path_ids': ['origin', '3', '4', 'destination'],
    'path': [
        {'latitude': 1.0, 'longitude': 0.0}, 
        {'latitude': 1.0, 'longitude': 0.0}, 
        {'latitude': 1.0, 'longitude': 1.0}, 
        {'latitude': 1.0, 'longitude': 1.0}
    ],
    'length': 1.0
}


if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)