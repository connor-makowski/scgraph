import json

import pytest

from scgraph.helpers.douglas_peucker import douglas_peucker
from scgraph.helpers.geojson import simplify_geojson
from scgraph.helpers.visvalingam import visvalingam


def test_visvalingam_basic():
    data = [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]]
    expected = [[1, 1], [3, 2], [4, 1], [5, 1]]
    assert visvalingam(data, pct_to_keep=50, min_points=3) == expected


# A line with one high peak and two small bumps. The peak (1, 2) is 2 away
# from the straight line between the two ends. The bumps (2, 1) and (3, 0.2)
# are 0.28 and 0.39 away from the straight line between the peak and the end.
_LINE_WITH_A_PEAK_AND_TWO_BUMPS = [[0, 0], [1, 2], [2, 1], [3, 0.2], [4, 0]]


def test_douglas_peucker_keeps_a_point_farther_than_the_tolerance():
    # The peak is 2 away: kept. The bumps are less than 0.5 away: removed.
    kept = douglas_peucker(_LINE_WITH_A_PEAK_AND_TWO_BUMPS, tolerance=0.5)

    assert kept == [[0, 0], [1, 2], [4, 0]]


def test_douglas_peucker_keeps_only_the_ends_under_a_large_tolerance():
    # No point is 5 away from the straight line between the two ends
    kept = douglas_peucker(_LINE_WITH_A_PEAK_AND_TWO_BUMPS, tolerance=5)

    assert kept == [[0, 0], [4, 0]]


def test_douglas_peucker_keeps_at_least_min_points_the_farthest_first():
    # The tolerance of 5 alone keeps the two ends. min_points asks for a
    # third point: the peak, which is the farthest from the line.
    kept = douglas_peucker(
        _LINE_WITH_A_PEAK_AND_TWO_BUMPS, tolerance=5, min_points=3
    )

    assert kept == [[0, 0], [1, 2], [4, 0]]


def test_douglas_peucker_reduces_a_straight_line_to_its_ends():
    straight_line = [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]

    kept = douglas_peucker(straight_line, tolerance=0)

    assert kept == [[0, 0], [4, 4]]


def test_douglas_peucker_refuses_a_negative_tolerance():
    with pytest.raises(ValueError, match="tolerance must be >= 0"):
        douglas_peucker([[0, 0], [1, 1]], tolerance=-1.0)


def _write_geojson_of_the_line_with_a_peak_and_two_bumps(tmp_path):
    """Write a GeoJSON file of one line and return its name."""
    path = tmp_path / "input.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": _LINE_WITH_A_PEAK_AND_TWO_BUMPS,
                        },
                    }
                ],
            }
        )
    )
    return str(path)


def test_simplify_geojson_with_visvalingam_keeps_the_asked_share_of_points(
    tmp_path,
):
    filename = _write_geojson_of_the_line_with_a_peak_and_two_bumps(tmp_path)

    lines = simplify_geojson(
        filename,
        algorithm="visvalingam",
        pct_to_keep=50,
        min_points=3,
    )

    # The line has 3 points between its ends. 50 % of 3 is 1.5, rounded to 2:
    # one point is removed. Visvalingam removes the point that makes the
    # smallest triangle with its two neighbours: the bump (2, 1), of area 0.1.
    assert lines == [[[0, 0], [1, 2], [3, 0.2], [4, 0]]]


def test_simplify_geojson_with_douglas_peucker_removes_points_within_tolerance(
    tmp_path,
):
    filename = _write_geojson_of_the_line_with_a_peak_and_two_bumps(tmp_path)

    lines = simplify_geojson(
        filename, algorithm="douglas_peucker", tolerance=0.5
    )

    # The peak is 2 away from the line between the ends: kept. The two bumps
    # are less than 0.5 away from the line between the peak and the end.
    assert lines == [[[0, 0], [1, 2], [4, 0]]]


def test_simplify_geojson_refuses_an_unknown_algorithm(tmp_path):
    filename = _write_geojson_of_the_line_with_a_peak_and_two_bumps(tmp_path)

    with pytest.raises(
        ValueError, match="Unsupported simplification algorithm"
    ):
        simplify_geojson(filename, algorithm="unknown")
