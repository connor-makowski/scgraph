import time
from pamda import pamda
from scgraph import Graph

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

def gen_graph(size, avg_connections=10):
    return {i:{i+j:1 for j in range(1,avg_connections) if i+j<size} for i in range(size)}

print('\n===============\nScale Time Tests:\n===============')

for size in [100, 1000, 10000]:
    graph = gen_graph(size)
    print(f'\nGraph Size: {size}')
    time_test(f'Graph Validation ({size})', pamda.thunkify(Graph.validate_graph)(graph=graph, check_symmetry=False, check_connected=False))
    time_test(f'Dijkstra ({size})', pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=0, destination_id=size-1))
    time_test(f'Dijkstra-Makowski ({size})', pamda.thunkify(Graph.dijkstra_makowski)(graph=graph, origin_id=0, destination_id=size-1))