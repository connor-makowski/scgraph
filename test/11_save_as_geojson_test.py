import json
import pytest
from helpers import great_circle_km
from scgraph import GeoGraph

# The [latitude, longitude] of six nodes one degree apart
NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
# The links of the six nodes, in both directions with the same weight. Node 4
# only lies between nodes 2 and 3: reduce() has a node to contract.
LINKS = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def test_geojson_file_gives_back_the_nodes_and_the_links(tmp_path):
    geograph = GeoGraph(nodes=list(NODES), graph=list(LINKS))
    path = str(tmp_path / "test.geojson")

    geograph.save_as_geojson(path)
    loaded = GeoGraph.load_from_geojson(path, silent=True)

    assert loaded.nodes == NODES
    # GeoJSON stores lines, not weights: the weights of the loaded graph are
    # the lengths of the lines, so only the pairs of linked nodes are compared
    linked_nodes = [set(links) for links in loaded.graph_object.graph]
    assert linked_nodes == [set(links) for links in LINKS]


def test_geojson_file_of_a_reduced_geograph_holds_the_graph_before_reduction(
    tmp_path,
):
    geograph = GeoGraph(nodes=list(NODES), graph=list(LINKS))
    geograph.reduce()
    path = str(tmp_path / "test.geojson")

    geograph.save_as_geojson(path)
    loaded = GeoGraph.load_from_geojson(path, silent=True)

    assert loaded.nodes == NODES
    linked_nodes = [set(links) for links in loaded.graph_object.graph]
    assert linked_nodes == [set(links) for links in LINKS]


def test_graphjson_file_gives_back_the_nodes_and_the_graph(tmp_path):
    geograph = GeoGraph(nodes=list(NODES), graph=list(LINKS))
    path = str(tmp_path / "test.graphjson")

    geograph.save_as_graphjson(path)
    loaded = GeoGraph.load_from_graphjson(path)

    assert loaded.nodes == NODES
    assert loaded.graph_object.graph == LINKS


def test_graphjson_file_of_a_reduced_geograph_holds_the_graph_before_reduction(
    tmp_path,
):
    geograph = GeoGraph(nodes=list(NODES), graph=list(LINKS))
    geograph.reduce()
    path = str(tmp_path / "test.graphjson")

    geograph.save_as_graphjson(path)
    loaded = GeoGraph.load_from_graphjson(path)

    assert loaded.nodes == NODES
    assert loaded.graph_object.graph == LINKS


def test_graphjson_file_gives_back_the_shapes_of_the_links(tmp_path):
    # Three nodes on the equator, 0.01 degree apart, and one shape point per
    # link, 0.003 degree north of the middle of the link. The shapes of
    # 0 <-> 1 and of 2 -> 1 repeat the two nodes of their link, as the files of
    # scgraph 3.6 do; the shape of 1 -> 2 holds only the point between the
    # nodes. Both forms must be read as the point between the nodes.
    geograph = GeoGraph(
        nodes=[[0.0, 0.0], [0.0, 0.01], [0.0, 0.02]],
        graph=[{1: 1.5}, {0: 1.5, 2: 1.5}, {1: 1.5}],
        intermediate_nodes=[
            {1: [[0.0, 0.0], [0.003, 0.005], [0.0, 0.01]]},
            {
                0: [[0.0, 0.01], [0.003, 0.005], [0.0, 0.0]],
                2: [[0.003, 0.015]],
            },
            {1: [[0.0, 0.02], [0.003, 0.015], [0.0, 0.01]]},
        ],
    )
    path = str(tmp_path / "shaped.graphjson")

    geograph.save_as_graphjson(path)
    loaded = GeoGraph.load_from_graphjson(path)

    route = loaded.get_shortest_path(
        origin_node={"latitude": 0.001, "longitude": 0.0},
        destination_node={"latitude": 0.001, "longitude": 0.02},
        output_coordinate_path="list_of_lists",
    )
    # The requested origin, each node once with the shape point of each link
    # between them, the requested destination
    assert route["coordinate_path"] == [
        [0.001, 0.0],
        [0.0, 0.0],
        [0.003, 0.005],
        [0.0, 0.01],
        [0.003, 0.015],
        [0.0, 0.02],
        [0.001, 0.02],
    ]


def write_geojson_line(path, coordinates):
    """Write a GeoJSON file of one line of [longitude, latitude] points."""
    path.write_text(
        json.dumps(
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "LineString", "coordinates": coordinates}
                ],
            }
        )
    )


# A longitude beyond 180 or below -180 is the same place as one within the
# range, 360 degrees away; 180 and -180 are kept as they are written.
@pytest.mark.parametrize(
    "written_longitude, loaded_longitude",
    [
        (180, 180),
        (-180, -180),
        (190.5, -169.5),
        (190.8498, -169.1502),
        (-180.5, 179.5),
    ],
)
def test_load_from_geojson_brings_a_longitude_back_within_180_degrees(
    tmp_path, written_longitude, loaded_longitude
):
    path = tmp_path / "line.geojson"
    # A line that ends on the equator at the longitude under test
    write_geojson_line(
        path, [[written_longitude - 0.5, 89.5], [written_longitude, 0]]
    )

    loaded = GeoGraph.load_from_geojson(str(path), silent=True)

    assert [0, loaded_longitude] in loaded.nodes


def test_load_from_geojson_accepts_a_point_at_the_pole(tmp_path):
    path = tmp_path / "line.geojson"
    write_geojson_line(path, [[12, 89.5], [12.5, 90]])

    loaded = GeoGraph.load_from_geojson(str(path), silent=True)

    assert [90, 12.5] in loaded.nodes


def test_load_from_geojson_refuses_a_latitude_beyond_the_pole(tmp_path):
    path = tmp_path / "line.geojson"
    write_geojson_line(path, [[12, 89.5], [12.5, 95]])

    with pytest.raises(ValueError, match="Latitude"):
        GeoGraph.load_from_geojson(str(path), silent=True)


def test_load_from_geojson_weighs_a_link_by_its_great_circle_length(tmp_path):
    # The line is far from the equator and from Greenwich: there, a latitude
    # taken for a longitude changes the length
    path = tmp_path / "line.geojson"
    write_geojson_line(path, [[100, 50], [101, 51]])

    loaded = GeoGraph.load_from_geojson(str(path), silent=True)

    expected = great_circle_km([50, 100], [51, 101])
    assert loaded.graph_object.graph[0][1] == pytest.approx(expected, abs=0.001)
