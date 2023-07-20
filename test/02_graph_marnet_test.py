import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.marnet import graph as marnet_graph

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
    print(f"{name}: {round(time.time()-start, 4)}s")

print('\n===============\nMarnet Graph Tests:\n===============')

graph = marnet_graph

expected = {'path': [0,5594,9469,2838,9454,669,8258,2685,7843,1941,7500,9446,1013,2891,7903,2335,1453,8226,9108,5],'length': 4727.879}

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

print('\n===============\nMarnet Time Tests:\n===============')

time_test('Graph Validation', pamda.thunkify(Graph.validate_graph)(graph=graph))

time_test('Dijkstra 1', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=0, destination_id=5))
time_test('Dijkstra 2', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=100, destination_id=7999))
time_test('Dijkstra 3', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=4022, destination_id=8342))

time_test('Dijkstra-Makowski 1', pamda.thunkify(Graph.dijkstra_makowski)(graph=graph, origin_id=0, destination_id=5))
time_test('Dijkstra-Makowski 2', pamda.thunkify(Graph.dijkstra_makowski)(graph=graph, origin_id=100, destination_id=7999))
time_test('Dijkstra-Makowski 3', pamda.thunkify(Graph.dijkstra_makowski)(graph=graph, origin_id=4022, destination_id=8342))