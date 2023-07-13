import time
from scgraph import Graph
from scgraph.data import marnet_data

print('\n===============\nMarnet Tests:\n===============')

my_graph = Graph(data=marnet_data)

# # Graph Validation
# my_graph.validate_graph()

# # Node Validation
# my_graph.validate_nodes()
start = time.time()
output = my_graph.get_shortest_path(
    origin={
        "latitude": 31.23,
        "longitude": 121.47
    }, 
    destination={
        "latitude": 32.08,
        "longitude": -81.09
    },
    algorithm="dijkstra"
)

print(f"PASS Dijkstra ({round(time.time()-start, 4)}s)")

start = time.time()
output = my_graph.get_shortest_path(
    origin={
        "latitude": 31.23,
        "longitude": 121.47
    }, 
    destination={
        "latitude": 32.08,
        "longitude": -81.09
    },
    algorithm="dijkstra_v2"
)

print(f"PASS Dijkstra_v2 ({round(time.time()-start, 4)}s)")