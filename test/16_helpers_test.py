import pytest

from scgraph.helpers.douglas_peucker import douglas_peucker
from scgraph.helpers.visvalingam import visvalingam


def test_visvalingam_basic():
    data = [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]]
    expected = [[1, 1], [3, 2], [4, 1], [5, 1]]
    assert visvalingam(data, pct_to_keep=50, min_points=3) == expected


def test_douglas_peucker_basic():
    data = [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]]
    # Tolerance 0.5 retains (2, 2) whose perpendicular distance from (1, 1)-(5, 1) is 1.0 > 0.5
    # (3, 2) is within 0.316 of segment (2, 2)-(5, 1), so dropped
    assert douglas_peucker(data, tolerance=0.5) == [[1, 1], [2, 2], [5, 1]]


def test_douglas_peucker_min_points():
    data = [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]]
    # High tolerance drops all interior points by distance, but min_points=3 keeps the highest deviation
    assert douglas_peucker(data, tolerance=2.0, min_points=2) == [
        [1, 1],
        [5, 1],
    ]
    assert douglas_peucker(data, tolerance=2.0, min_points=3) == [
        [1, 1],
        [2, 2],
        [5, 1],
    ]


def test_douglas_peucker_colinear():
    colinear = [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]
    assert douglas_peucker(colinear, tolerance=0.0) == [[0, 0], [4, 4]]


def test_douglas_peucker_invalid_tolerance():
    with pytest.raises(ValueError, match="tolerance must be >= 0"):
        douglas_peucker([[0, 0], [1, 1]], tolerance=-1.0)


def test_simplify_geojson_algorithms(tmp_path):
    import json
    from scgraph.helpers.geojson import simplify_geojson

    sample = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]],
                },
            }
        ],
    }
    input_file = tmp_path / "input.geojson"
    input_file.write_text(json.dumps(sample))

    # Visvalingam
    res_vis = simplify_geojson(
        str(input_file),
        algorithm="visvalingam",
        pct_to_keep=50,
        min_points=3,
        silent=True,
    )
    assert len(res_vis[0]) == 4

    # Douglas-Peucker
    res_dp = simplify_geojson(
        str(input_file),
        algorithm="douglas_peucker",
        tolerance=0.5,
        silent=True,
    )
    assert len(res_dp[0]) == 3

    # Invalid algorithm
    with pytest.raises(
        ValueError, match="Unsupported simplification algorithm"
    ):
        simplify_geojson(str(input_file), algorithm="unknown", silent=True)
