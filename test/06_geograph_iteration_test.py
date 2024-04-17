from scgraph import GeoGraph
from scgraph.geographs.marnet import marnet_geograph

print("\n===============\nGeoGraph Iteration Test:\n===============")

iterations = [
    [
        {"latitude": 35.1799528, "longitude": 129.0752365},
        {"latitude": 36.0638034, "longitude": 120.3781372},
    ],
    [
        {"latitude": 36.0638034, "longitude": 120.3781372},
        {"latitude": 31.2312707, "longitude": 121.4700152},
    ],
    [
        {"latitude": 31.2312707, "longitude": 121.4700152},
        {"latitude": 22.5590503, "longitude": 114.2324407},
    ],
    [
        {"latitude": 22.5590503, "longitude": 114.2324407},
        {"latitude": 47.6038321, "longitude": -122.330062},
    ],
]

failed = False
for i in iterations:
    output = marnet_geograph.get_shortest_path(
        origin_node=i[0],
        destination_node=i[1],
    )
    if len(output["coordinate_path"]) < 3:
        failed = True

if failed:
    print(f"Iteration Test: FAIL")
else:
    print(f"Iteration Test: PASS")
