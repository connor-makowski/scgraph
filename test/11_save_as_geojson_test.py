import json
import pytest
from helpers import great_circle_km
from scgraph import GeoGraph

_NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


@pytest.fixture
def tmp_graph(tmp_path):
    return GeoGraph(nodes=list(_NODES), graph=list(_GRAPH)), tmp_path


# Saving must write the original graph, whether or not the geograph was reduced
@pytest.mark.parametrize("reduce", [False, True])
def test_save_load_geojson(tmp_graph, reduce):
    geo, tmp = tmp_graph
    if reduce:
        geo.reduce()
    geojson_path = str(tmp / "test.geojson")
    geo.save_as_geojson(geojson_path)
    loaded = GeoGraph.load_from_geojson(geojson_path, silent=True)
    assert loaded.nodes == _NODES
    # GeoJSON stores geometries: compare edges, not their recomputed lengths
    edges = [set(d) for d in loaded.graph_object.graph]
    assert edges == [set(d) for d in _GRAPH]


@pytest.mark.parametrize("reduce", [False, True])
def test_save_load_graphjson(tmp_graph, reduce):
    geo, tmp = tmp_graph
    if reduce:
        geo.reduce()
    graphjson_path = str(tmp / "test.graphjson")
    geo.save_as_graphjson(graphjson_path)
    loaded = GeoGraph.load_from_graphjson(graphjson_path)
    assert loaded.graph_object.graph == _GRAPH
    assert loaded.nodes == _NODES


def test_load_from_graphjson_reads_a_shape_with_or_without_its_end_nodes(
    tmp_path,
):
    # Three nodes on the equator, 0.01 degree apart, linked 0 - 1 - 2. The
    # shape of a link is the list of the points between its two nodes. Here
    # each link has one such point, 0.003 degree north of its middle.
    geograph = GeoGraph(
        nodes=[[0.0, 0.0], [0.0, 0.01], [0.0, 0.02]],
        graph=[{1: 1.5}, {0: 1.5, 2: 1.5}, {1: 1.5}],
        intermediate_nodes=[
            # Form of the files of scgraph 3.6: the shape repeats the two nodes
            {1: [[0.0, 0.0], [0.003, 0.005], [0.0, 0.01]]},
            {
                0: [[0.0, 0.01], [0.003, 0.005], [0.0, 0.0]],
                # Form of today: the shape holds the point between the nodes
                2: [[0.003, 0.015]],
            },
            {1: [[0.0, 0.02], [0.003, 0.015], [0.0, 0.01]]},
        ],
    )
    filename = str(tmp_path / "shaped.graphjson")
    geograph.save_as_graphjson(filename)

    loaded = GeoGraph.load_from_graphjson(filename)

    route = loaded.get_shortest_path(
        origin_node={"latitude": 0.001, "longitude": 0.0},
        destination_node={"latitude": 0.001, "longitude": 0.02},
        output_coordinate_path="list_of_lists",
    )
    assert route["coordinate_path"] == [
        [0.001, 0.0],  # the requested origin
        [0.0, 0.0],  # node 0
        [0.003, 0.005],  # the shape of the link 0 -> 1, without nodes 0 and 1
        [0.0, 0.01],  # node 1
        [0.003, 0.015],  # the shape of the link 1 -> 2
        [0.0, 0.02],  # node 2
        [0.001, 0.02],  # the requested destination
    ]


def _write_geojson_line(path, coordinates):
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


# A longitude above 180 or below -180 is the same place as a longitude within
# the range, 360 degrees away. The loader keeps 180 and -180 as they are.
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
    # The line ends on the equator, at the longitude that the test checks
    _write_geojson_line(
        path, [[written_longitude - 0.5, 89.5], [written_longitude, 0]]
    )

    loaded = GeoGraph.load_from_geojson(str(path), silent=True)

    assert [0, loaded_longitude] in loaded.nodes


def test_load_from_geojson_accepts_a_point_at_the_pole(tmp_path):
    path = tmp_path / "line.geojson"
    _write_geojson_line(path, [[12, 89.5], [12.5, 90]])

    loaded = GeoGraph.load_from_geojson(str(path), silent=True)

    assert [90, 12.5] in loaded.nodes


def test_load_from_geojson_refuses_a_latitude_beyond_the_pole(tmp_path):
    path = tmp_path / "line.geojson"
    _write_geojson_line(path, [[12, 89.5], [12.5, 95]])

    with pytest.raises(ValueError, match="Latitude"):
        GeoGraph.load_from_geojson(str(path), silent=True)


def test_load_from_geojson_weighs_a_link_by_its_great_circle_length(tmp_path):
    # The line is far from the equator and from Greenwich. If the loader
    # swapped latitude and longitude there, the length would differ.
    path = tmp_path / "line.geojson"
    _write_geojson_line(path, [[100, 50], [101, 51]])

    loaded = GeoGraph.load_from_geojson(str(path), silent=True)

    expected = great_circle_km([50, 100], [51, 101])
    assert loaded.graph_object.graph[0][1] == pytest.approx(expected, abs=0.001)
