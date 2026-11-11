import pytest

from scgraph.helpers.douglas_peucker import douglas_peucker
from scgraph.helpers.visvalingam import visvalingam


# Visvalingam keeps the asked share of the interior points, removing each time
# the point of the smallest triangle: here (4, 0) (area 0.5), then (3, 1) (1.5
# once (4, 0) is gone) against 2 and 3 for the two others.
def test_visvalingam_keeps_the_most_significant_points():
    data = [[0, 0], [1, 3], [2, 0], [3, 1], [4, 0], [5, 0]]
    assert visvalingam(data, pct_to_keep=50) == [[0, 0], [1, 3], [2, 0], [5, 0]]


_LINE = [[0, 0], [1, 2], [2, 1], [3, 0.2], [4, 0]]


# Douglas-Peucker keeps the points farther than the tolerance from the
# simplified line, and the farthest ones beyond it up to min_points. In _LINE,
# (1, 2) is 2 away from the line of the two ends, then (2, 1) and (3, 0.2) are
# 0.28 and 0.39 away from the line (1, 2) - (4, 0).
@pytest.mark.parametrize(
    "coords, tolerance, min_points, expected",
    [
        (_LINE, 0.5, 2, [[0, 0], [1, 2], [4, 0]]),
        (_LINE, 5, 2, [[0, 0], [4, 0]]),
        (_LINE, 5, 3, [[0, 0], [1, 2], [4, 0]]),
        ([[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]], 0, 2, [[0, 0], [4, 4]]),
    ],
)
def test_douglas_peucker_keeps_the_farthest_points(
    coords, tolerance, min_points, expected
):
    assert douglas_peucker(coords, tolerance, min_points) == expected


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
