import time
from pamda import pamda
from scgraph import Graph
from scgraph.data import marnet_data

def validate(name, realized, expected):
    if realized == expected:
        print(f'{name}: PASS')
    else:
        print(f'{name}: FAIL')
        print('Expected:', expected)
        print('Realized:', realized)

def time_test(name, thunk):
    start = time.time()
    thunk()
    print(f"{name}: ({round(time.time()-start, 4)}s)")

print('\n===============\nMarnet Graph Tests:\n===============')

graph = marnet_data.get('graph')

expected = {
    'path': [0, 1, 3950, 7790, 9996, 8652, 604], 
    'length': 1247.1
}

validate(
    name='Graph Validation',
    realized = Graph.validate_graph(graph=graph),
    expected = None
)

validate(
    name='Dijkstra', 
    realized = Graph.dijkstra(graph=graph, origin_id=0, destination_id=604), 
    expected = expected
)

validate(
    name='Dijkstra_v2',
    realized = Graph.dijkstra_v2(graph=graph, origin_id=0, destination_id=604),
    expected = expected
)

print('\n===============\nMarnet Time Tests:\n===============')

time_test('Dijkstra 1', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=0, destination_id=5))
time_test('Dijkstra 2', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=100, destination_id=7999))
time_test('Dijkstra 3', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=4022, destination_id=8342))

time_test('Dijkstra_v2 1', pamda.thunkify(Graph.dijkstra_v2)(graph=graph, origin_id=0, destination_id=5))
time_test('Dijkstra_v2 2', pamda.thunkify(Graph.dijkstra_v2)(graph=graph, origin_id=100, destination_id=7999))
time_test('Dijkstra_v2 3', pamda.thunkify(Graph.dijkstra_v2)(graph=graph, origin_id=4022, destination_id=8342))