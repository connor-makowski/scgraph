from scgraph import Graph
from scgraph.data import marnet_data

print('\n===============\nMarnet Tests:\n===============')

my_graph = Graph(data=marnet_data)

# Graph Validation
my_graph.validate_graph()

# Node Validation
my_graph.validate_nodes()

output = my_graph.get_shortest_path(
    origin={
        "latitude": 31.23,
        "longitude": 121.47
    }, 
    destination={
        "latitude": 32.08,
        "longitude": -81.09
    }
)

print("PASS")