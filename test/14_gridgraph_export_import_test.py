from scgraph import GridGraph


def test_imported_grid_routes_from_the_exported_cache(tmp_path):
    # A grid with a wall on the column x = 5 from y = 3 to the top, and a route
    # from one side of the wall to the other
    grid = GridGraph(
        x_size=11,
        y_size=10,
        blocks=[(5, y) for y in range(3, 10)],
        shape=[(0, 0), (0, 1), (1, 0), (1, 1)],
        add_exterior_walls=True,
    )
    query = {
        "origin_node": {"x": 1, "y": 8},
        "destination_node": {"x": 8, "y": 8},
        "output_coordinate_path": "list_of_lists",
    }
    # This first cached query puts the shortest path tree of the origin in the
    # cache of the grid
    grid.get_shortest_path(**query, algorithm_fn="cached_shortest_path")
    filename = str(tmp_path / "test.gridgraph")

    grid.export_object(filename=filename)
    imported = GridGraph.import_object(filename=filename)

    # The imported grid holds the tree of the origin, and its cached route is
    # the route that Dijkstra finds on the grid before the export
    origin_id = imported.get_idx(x=1, y=8)
    assert imported.graph_object.get_cache()[origin_id]
    assert imported.get_shortest_path(
        **query, algorithm_fn="cached_shortest_path"
    ) == grid.get_shortest_path(**query, algorithm_fn="dijkstra")
