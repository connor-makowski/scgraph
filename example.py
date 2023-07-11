from scgraph import Graph
from scgraph.data import marnet_data

my_graph = Graph(data=marnet_data)
# Get the shortest path between 
output = my_graph.get_shortest_path(
    origin={"latitude": 31.23,"longitude": 121.47}, 
    destination={"latitude": 32.08,"longitude": -81.09}
)
print('Length: ',output['length'])
# print(str([[i['latitude'],i['longitude']] for i in output['path']]))
