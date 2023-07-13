import time
from scgraph import Graph

print('\n===============\nTime Tests:\n===============')

def gen_graph(size, avg_connections=10):
    return {i:{i+j:1 for j in range(1,avg_connections) if i+j<size} for i in range(size-1)}

def test_size(size, algorithm):
    graph = gen_graph(size)
    my_graph = Graph(data={'graph':graph})
    start = time.time()
    if algorithm == 'dijkstra':
        my_graph.dijkstra(origin=0, destination=size-1)
    elif algorithm == 'dijkstra_v2':
        my_graph.dijkstra_v2(origin=0, destination=size-1)
    else:
        print('Invalid algorithm')
        return
    print (f'{algorithm}({size}) time (s):', time.time()-start)

print ('\nDijkstra Tests:')
test_size(10, 'dijkstra')
test_size(100, 'dijkstra')
test_size(1000, 'dijkstra')
test_size(10000, 'dijkstra')
print ('\nDijkstra V2 Tests:')
test_size(10, 'dijkstra_v2')
test_size(100, 'dijkstra_v2')
test_size(1000, 'dijkstra_v2')
test_size(10000, 'dijkstra_v2')
test_size(100000, 'dijkstra_v2')
print()