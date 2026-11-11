from scgraph import GridGraph

_ORIGIN = {"x": 1, "y": 8}
_QUERY = {
    "origin_node": _ORIGIN,
    "destination_node": {"x": 8, "y": 8},
    "output_coordinate_path": "list_of_lists",
}


# A grid exported with its cache and imported again holds the shortest path
# tree of the origin, and its cached route is the route that Dijkstra finds on
# the grid before the export.
def test_imported_grid_routes_from_the_exported_cache(tmp_path):
    grid = GridGraph(
        x_size=11,
        y_size=10,
        blocks=[(5, y) for y in range(3, 10)],
        shape=[(0, 0), (0, 1), (1, 0), (1, 1)],
        add_exterior_walls=True,
    )
    grid.get_shortest_path(**_QUERY, algorithm_fn="cached_shortest_path")
    filename = str(tmp_path / "test.gridgraph")
    grid.export_object(filename=filename)
    imported = GridGraph.import_object(filename=filename)
    assert imported.graph_object.get_cache()[imported.get_idx(**_ORIGIN)]
    assert imported.get_shortest_path(
        **_QUERY, algorithm_fn="cached_shortest_path"
    ) == grid.get_shortest_path(**_QUERY, algorithm_fn="dijkstra")
