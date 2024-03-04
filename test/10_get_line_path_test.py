from scgraph.geographs.marnet import marnet_geograph
from scgraph.utils import get_line_path

origin_node = {"latitude": 30, "longitude": 160}
destination_node = {"latitude": 30, "longitude": -160}

try:
    output = marnet_geograph.get_shortest_path(
        origin_node=origin_node, destination_node=destination_node
    )

    get_line_path(output, filename=None)
    # get_line_path(output, filename='test.json')
except Exception:
    print("Get Line Path: FAIL")
