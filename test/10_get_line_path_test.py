from scgraph.utils import get_line_path


def test_get_line_path(marnet):
    output = marnet.get_shortest_path(
        origin_node={"latitude": 30, "longitude": 160},
        destination_node={"latitude": 30, "longitude": -160},
    )
    get_line_path(output, filename=None)
