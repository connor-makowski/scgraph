from scgraph import Graph
from scgraph.data import marnet_data

print('\n===============\nGraph Iteration Tests:\n===============')

my_graph = Graph(data=marnet_data)


iterations = [
    [{'latitude': 35.1799528, 'longitude': 129.0752365}, {'latitude': 36.0638034, 'longitude': 120.3781372}],
    [{'latitude': 36.0638034, 'longitude': 120.3781372}, {'latitude': 31.2312707, 'longitude': 121.4700152}],
    [{'latitude': 31.2312707, 'longitude': 121.4700152}, {'latitude': 22.5590503, 'longitude': 114.2324407}],
    [{'latitude': 22.5590503, 'longitude': 114.2324407}, {'latitude': 47.6038321, 'longitude': -122.330062}],
]

failed = False
for i in iterations:
    output = my_graph.get_shortest_path(
        origin=i[0],
        destination=i[1],
    )
    if len(output['path_ids'])<3:
        failed = True
    print(output['path_ids'])

if failed:
    print(f"FAIL")
else:
    print(f"PASS")