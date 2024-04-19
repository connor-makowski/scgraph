from scgraph.geographs.marnet import marnet_geograph

# Get the shortest path between 
output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23,"longitude": 121.47}, 
    destination_node={"latitude": 32.08,"longitude": -81.09}
)
print('Length: ',output['length']) #=> Length:  19596.4653
print('Path: ', output['coordinate_path'])
