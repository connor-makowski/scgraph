import json

import pytest
from helpers import great_circle_km

from scgraph import GeoGraph

# GeoJSON lines, as [longitude, latitude] points
_LINES = [
    [[0, 0], [0.01, 0], [0.02, 0]],
    [[0.01, 0], [0.01, 0.01]],  # meets the first line at one of its points
    [[0.015, -0.005], [0.015, 0.005]],  # crosses it without a shared point
    [[0, 1], [0.01, 1.005], [0.02, 1], [0.03, 1]],  # about 1.2 km per segment
]


def test_load_from_geojson_with_max_km_between_nodes(tmp_path):
    path = tmp_path / "lines.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "LineString", "coordinates": line}
                    for line in _LINES
                ],
            }
        )
    )
    geo = GeoGraph.load_from_geojson(
        str(path), silent=True, max_km_between_nodes=2
    )
    arcs = {
        (tuple(geo.nodes[u]), tuple(geo.nodes[v])): length
        for u, row in enumerate(geo.graph_object.graph)
        for v, length in row.items()
    }
    shapes = {
        (tuple(geo.nodes[u]), tuple(geo.nodes[v])): shape
        for u, row in enumerate(geo.intermediate_nodes)
        for v, shape in row.items()
    }
    long_arc = ((1, 0), (1, 0.02))
    expected = {
        ((0, 0), (0, 0.01)),
        ((0, 0.01), (0, 0.02)),
        ((0, 0.01), (0.01, 0.01)),  # the lines meet at their shared point
        ((-0.005, 0.015), (0.005, 0.015)),  # the crossing line stays apart
        long_arc,  # cut at the first point 2 km or more from the start
        ((1, 0.02), (1, 0.03)),
    }
    assert set(arcs) == expected | {(b, a) for a, b in expected}
    assert shapes[long_arc] == [[1, 0], [1.005, 0.01], [1, 0.02]]
    assert arcs[long_arc] == pytest.approx(
        great_circle_km((1, 0), (1.005, 0.01))
        + great_circle_km((1.005, 0.01), (1, 0.02))
    )
