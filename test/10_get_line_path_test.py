from scgraph.utils import get_line_path


def test_get_line_path(marnet):
    output = marnet.get_shortest_path(
        origin_node={"latitude": 30, "longitude": 160},
        destination_node={"latitude": 30, "longitude": -160},
    )
    line = get_line_path(output, filename=None)
    # A GeoJSON line holds [longitude, latitude] points
    assert line["type"] == "LineString"
    assert line["coordinates"][0] == [160, 30]
    assert line["coordinates"][-1] == [-160, 30]
    assert len(line["coordinates"]) == len(output["coordinate_path"])
