from scgraph import GeoGraph
from scgraph.utils import get_line_path


# A route becomes a GeoJSON LineString of its points, longitude first.
def test_route_as_geojson_line():
    geograph = GeoGraph(nodes=[[50, 10], [51, 11]], graph=[{1: 1}, {0: 1}])
    route = geograph.get_shortest_path(
        origin_node={"latitude": 49.9, "longitude": 10},
        destination_node={"latitude": 51.1, "longitude": 11},
    )
    assert get_line_path(route) == {
        "type": "LineString",
        "coordinates": [[10, 49.9], [10, 50], [11, 51], [11, 51.1]],
    }
