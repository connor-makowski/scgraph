import json
import pytest
from scgraph import GridGraph

_X_SIZE = 300
_Y_SIZE = 300
_BLOCKS = [(5, i) for i in range(3, _Y_SIZE)]
_SHAPE = [(0, 0), (0, 1), (1, 0), (1, 1)]
_ORIGIN = {"x": 1, "y": 8}
_DEST = {"x": 8, "y": 8}


@pytest.fixture(scope="module")
def exported_grid(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("gridgraph")
    grid = GridGraph(
        x_size=_X_SIZE,
        y_size=_Y_SIZE,
        blocks=_BLOCKS,
        shape=_SHAPE,
        add_exterior_walls=True,
    )
    grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
        algorithm_fn="cached_shortest_path",
    )
    export_path = str(tmp / "test.gridgraph")
    grid.export_object(filename=export_path)
    return GridGraph.import_object(filename=export_path)


def test_import_cached_path_matches(exported_grid):
    original = GridGraph(
        x_size=_X_SIZE,
        y_size=_Y_SIZE,
        blocks=_BLOCKS,
        shape=_SHAPE,
        add_exterior_walls=True,
    )
    original_output = original.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
    )
    imported_output = exported_grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
        algorithm_fn="cached_shortest_path",
    )
    assert round(original_output["length"], 4) == round(
        imported_output["length"], 4
    )


def test_import_keeps_cache_and_cached_path_matches_dijkstra(tmp_path):
    # A grid of its own: the other test fills the cache of exported_grid
    grid = GridGraph(
        x_size=11,
        y_size=10,
        blocks=[(5, i) for i in range(3, 10)],
        shape=_SHAPE,
        add_exterior_walls=True,
    )
    # This cached query stores the shortest path tree of the origin
    grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
        algorithm_fn="cached_shortest_path",
    )
    export_path = str(tmp_path / "test.gridgraph")
    grid.export_object(filename=export_path)
    imported = GridGraph.import_object(filename=export_path)

    # Verify that the cache was successfully imported
    cache = imported.graph_object.get_cache()
    assert cache[imported.get_idx(**_ORIGIN)], "Cache was not imported properly"

    dijkstra_output = grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
        algorithm_fn="dijkstra",
    )
    imported_output = imported.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
        algorithm_fn="cached_shortest_path",
    )
    assert imported_output == dijkstra_output


def test_grid_save_as_geojson_writes_each_edge_from_x_y_to_x_y(tmp_path):
    # Three cells in a row, with the moves right and left: 4 edges
    grid = GridGraph(
        x_size=3,
        y_size=1,
        blocks=[],
        add_exterior_walls=False,
        conn_data=[(1, 0, 1.0), (-1, 0, 1.0)],
    )
    grid.save_as_geojson(tmp_path / "grid.geojson")

    features = json.loads((tmp_path / "grid.geojson").read_text())["features"]

    assert len(features) == 4
    assert features[0] == {
        "type": "Feature",
        "properties": {"origin_idx": 0, "destination_idx": 1, "distance": 1.0},
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0]]},
    }
