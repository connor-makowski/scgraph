from SCgraph import SCgraph, marnet_data

my_graph = SCgraph(data=marnet_data)

# SCgraph Validation
my_graph.validate_graph()

# # Node Validation
my_graph.validate_nodes()

output = my_graph.get_shortest_path(
    origin={
        "latitude": 31.23,
        "longitude": 121.47
    }, 
    destination={
        "latitude": 49.08,
        "longitude": -123.09
    }
)

# print(output)

print(str([[i['latitude'],i['longitude']] for i in output['path']]))