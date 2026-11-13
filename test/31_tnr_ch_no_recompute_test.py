from scgraph import GeoGraph


def _make_dummy_geograph(rows=12, cols=12):
    nodes = []
    graph = []
    for r in range(rows):
        for c in range(cols):
            # Coordinates range from 0.0 to 1.1
            nodes.append([float(r) / 10.0, float(c) / 10.0])
            edges = {}
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbor_id = nr * cols + nc
                    edges[neighbor_id] = 1.0
            graph.append(edges)
    return GeoGraph(nodes=nodes, graph=graph)


def test_no_recompute(graph_class):
    geo = _make_dummy_geograph(rows=12, cols=12)
    # Wrap in the target graph class (Python or C++)
    geo.graph_object = graph_class(graph=geo.graph)

    origin = {"latitude": 0.0, "longitude": 0.0}
    destination = {"latitude": 1.1, "longitude": 1.1}

    # 1. Test Contraction Hierarchy (CH)
    ch_before = geo.graph_object.create_contraction_hierarchy()
    assert ch_before is not None

    res_ch = geo.get_shortest_path(
        origin, destination, algorithm_fn="contraction_hierarchy"
    )
    # Verify the cached CH hierarchy was reused and not recomputed
    ch_after = geo.graph_object.create_contraction_hierarchy()
    if hasattr(geo.graph_object, "__ch_graph__"):
        assert geo.graph_object.__ch_graph__ is ch_before
    assert ch_after is ch_before

    # 2. Test Transit Node Routing (TNR)
    tnr_before = geo.graph_object.create_tnr_hierarchy(num_transit_nodes=20)
    assert tnr_before is not None

    res_tnr = geo.get_shortest_path(origin, destination, algorithm_fn="tnr")
    # Verify the cached TNR hierarchy was reused and not recomputed
    tnr_after = geo.graph_object.create_tnr_hierarchy(num_transit_nodes=20)
    if hasattr(geo.graph_object, "__tnr_graph__"):
        assert geo.graph_object.__tnr_graph__ is tnr_before
    assert tnr_after is tnr_before

    # Verify correctness
    dijkstra = geo.get_shortest_path(
        origin, destination, algorithm_fn="dijkstra"
    )
    assert abs(res_ch["length"] - dijkstra["length"]) < 1e-3
    assert abs(res_tnr["length"] - dijkstra["length"]) < 1e-3
