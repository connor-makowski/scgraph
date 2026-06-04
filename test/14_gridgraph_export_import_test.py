import pytest
from scgraph import GridGraph
from scgraph.utils import has_cpp

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
        cache=True,
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
        cache=True,
    )
    assert round(original_output["length"], 4) == round(
        imported_output["length"], 4
    )


def test_import_cached_is_fast(exported_grid):
    import time

    start = time.time()
    exported_grid.get_shortest_path(
        origin_node=_ORIGIN,
        destination_node=_DEST,
        output_coordinate_path="list_of_lists",
        cache=True,
    )
    elapsed = time.time() - start
    epxectation = 0.0005 if has_cpp() else 0.010
    assert (
        elapsed < epxectation
    ), f"Cached lookup took {elapsed*1000:.3f}ms — cache may not be working"
