import time
from scgraph import Graph

print('\n===============\nTime Tests:\n===============')

def gen_graph(size, avg_connections=10):
    return {i:{i+j:1 for j in range(avg_connections) if j!=i and j< size} for i in range(size)}

def test_size(size):
    graph = gen_graph(size)
    my_graph = Graph(data={'graph':graph})
    start = time.time()
    my_graph.dijkstra(origin=0, destination=size-1)
    print (f'({size}) Dijkstra time (seconds):', time.time()-start)

test_size(10)
test_size(100)
test_size(1000)
test_size(10000)