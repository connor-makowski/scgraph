import time
from scgraph import Graph
from scgraph.data import example_data

print('\n===============\nBasic Tests:\n===============')

print ('\nTest 1a: Basic manually passed graph with no nodes and raw dijkstra fn')
data = {
    # "nodes": {
    #     "0": {"latitude": 0, "longitude": 0},
    #     "1": {"latitude": 0, "longitude": 1},
    #     "2": {"latitude": 1, "longitude": 0},
    #     "3": {"latitude": 1, "longitude": 1},
    #     "4": {"latitude": 1, "longitude": 2},
    #     "5": {"latitude": 2, "longitude": 1}
    # },
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

try:
    my_graph.validate_graph()
except:
    print ('FAIL Validation')

expected = {
    'path_ids': ["0", "2", "1", "3", "5"],
    'length': 10,
    # 'path': [
    #     {'latitude': 0, 'longitude': 0}, 
    #     {'latitude': 1, 'longitude': 0}, 
    #     {'latitude': 0, 'longitude': 1}, 
    #     {'latitude': 1, 'longitude': 1}, 
    #     {'latitude': 2, 'longitude': 1}
    # ]
}

actual = my_graph.dijkstra(origin="0", destination="5")

if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)


print ('\nTest 1b: Basic manually passed graph with no nodes and raw dijkstra_v2 fn')
actual = my_graph.dijkstra_v2(origin="0", destination="5")
if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)


print ('\nTest 2a: Basic manually passed graph with nodes and raw dijkstra fn')
data = {
    "nodes": {
        "0": {"latitude": 0, "longitude": 0},
        "1": {"latitude": 0, "longitude": 1},
        "2": {"latitude": 1, "longitude": 0},
        "3": {"latitude": 1, "longitude": 1},
        "4": {"latitude": 1, "longitude": 2},
        "5": {"latitude": 2, "longitude": 1}
    },
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

try:
    my_graph.validate_nodes()
    my_graph.validate_graph()
except:
    print ('FAIL Validation')

expected = {
    'path_ids': ["0", "2", "1", "3", "5"],
    'length': 10,
    'path': [
        {'latitude': 0, 'longitude': 0}, 
        {'latitude': 1, 'longitude': 0}, 
        {'latitude': 0, 'longitude': 1}, 
        {'latitude': 1, 'longitude': 1}, 
        {'latitude': 2, 'longitude': 1}
    ]
}

actual = my_graph.dijkstra(origin="0", destination="5")

if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)


print ('\nTest 2b: Basic manually passed graph with nodes and raw dijkstra_v2 fn')
actual = my_graph.dijkstra_v2(origin="0", destination="5")
if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)



print ('\nTest 3a: Basic graph with example data')
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

print ('\nTest 3b: Basic graph with example data and not initalizing a new graph')
actual = my_graph.get_shortest_path(
    origin={
        "latitude": 0.0,
        "longitude": 0.0
    }, 
    destination={
        "latitude": 1.0,
        "longitude": 1.0
    }
)

expected = {
    'path_ids': ['origin', '1', '2', '4', 'destination'],
    'path': [
        {'latitude': 0.0, 'longitude': 0.0}, 
        {'latitude': 0.0, 'longitude': 0.0}, 
        {'latitude': 0.0, 'longitude': 1.0},
        {'latitude': 1.0, 'longitude': 1.0}, 
        {'latitude': 1.0, 'longitude': 1.0}
    ],
    'length': 2.0
}
if actual == expected:
    print('PASS')
else:
    print('FAIL')
    print('Expected:', expected)
    print('Actual:', actual)