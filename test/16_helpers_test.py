import json

import pytest

from scgraph.helpers.douglas_peucker import douglas_peucker
from scgraph.helpers.geojson import simplify_geojson
from scgraph.helpers.visvalingam import visvalingam


def test_visvalingam_removes_the_points_of_the_smallest_triangles_first():
    # A point's weight is the area of the triangle it makes with its two
    # neighbours. (4, 0) has the smallest (0.5) and goes first; (3, 1) then makes
    # a triangle of area 1.5 with (2, 0) and (5, 0), smaller than the 3 of (1, 3)
    # and the 2 of (2, 0), and goes second.
    line = [[0, 0], [1, 3], [2, 0], [3, 1], [4, 0], [5, 0]]

    kept = visvalingam(line, pct_to_keep=50)

    assert kept == [[0, 0], [1, 3], [2, 0], [5, 0]]


# A line with one high peak and two small bumps. From the straight line between
# its ends, the peak (1, 2) is 2 away. Once the peak is kept, the bumps (2, 1)
# and (3, 0.2) are 0.28 and 0.39 away from the line peak -> end.
LINE_WITH_A_PEAK_AND_TWO_BUMPS = [[0, 0], [1, 2], [2, 1], [3, 0.2], [4, 0]]


def test_douglas_peucker_keeps_a_point_farther_than_the_tolerance():
    # The peak is 2 away (kept); the bumps are under 0.5 away (dropped)
    kept = douglas_peucker(LINE_WITH_A_PEAK_AND_TWO_BUMPS, tolerance=0.5)

    assert kept == [[0, 0], [1, 2], [4, 0]]


def test_douglas_peucker_keeps_only_the_ends_under_a_large_tolerance():
    # No point is 5 away from the line between the ends
    kept = douglas_peucker(LINE_WITH_A_PEAK_AND_TWO_BUMPS, tolerance=5)

    assert kept == [[0, 0], [4, 0]]


def test_douglas_peucker_keeps_the_farthest_points_up_to_min_points():
    # The tolerance alone would keep the two ends; a third point is asked for,
    # and the peak is the farthest
    kept = douglas_peucker(
        LINE_WITH_A_PEAK_AND_TWO_BUMPS, tolerance=5, min_points=3
    )

    assert kept == [[0, 0], [1, 2], [4, 0]]


def test_douglas_peucker_reduces_a_straight_line_to_its_ends():
    straight_line = [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]

    assert douglas_peucker(straight_line, tolerance=0) == [[0, 0], [4, 4]]


def test_douglas_peucker_refuses_a_negative_tolerance():
    with pytest.raises(ValueError, match="tolerance must be >= 0"):
        douglas_peucker([[0, 0], [1, 1]], tolerance=-1.0)


# A GeoJSON file of one line of five points: a flat-topped bump, (2, 2) and
# (3, 2), above the base (1, 1) -> (5, 1) on which (4, 1) lies.
@pytest.fixture
def geojson_file_of_a_line_with_a_bump(tmp_path):
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
                            "coordinates": [
                                [1, 1],
                                [2, 2],
                                [3, 2],
                                [4, 1],
                                [5, 1],
                            ],
                        },
                    }
                ],
            }
        )
    )
    return str(path)


def test_simplify_geojson_with_visvalingam_keeps_the_asked_share_of_points(
    geojson_file_of_a_line_with_a_bump,
):
    lines = simplify_geojson(
        geojson_file_of_a_line_with_a_bump,
        algorithm="visvalingam",
        pct_to_keep=50,
        min_points=3,
        silent=True,
    )

    # Half of the 3 interior points is 1.5, rounded to 2, plus the two ends
    assert len(lines[0]) == 4


def test_simplify_geojson_with_douglas_peucker_drops_points_within_tolerance(
    geojson_file_of_a_line_with_a_bump,
):
    lines = simplify_geojson(
        geojson_file_of_a_line_with_a_bump,
        algorithm="douglas_peucker",
        tolerance=0.5,
        silent=True,
    )

    # The two points of the bump are 1 away from the base: one of them is kept.
    # The two other interior points are then less than 0.5 away from the
    # simplified line (0.32 or 0.45, according to the point kept).
    assert len(lines[0]) == 3


def test_simplify_geojson_refuses_an_unknown_algorithm(
    geojson_file_of_a_line_with_a_bump,
):
    with pytest.raises(
        ValueError, match="Unsupported simplification algorithm"
    ):
        simplify_geojson(
            geojson_file_of_a_line_with_a_bump,
            algorithm="unknown",
            silent=True,
        )
