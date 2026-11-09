"""
Strategic passages: the sea route between two ports takes the passage it should.

Reference: for each port pair, a passage box and whether the shortest route "enters" it
(Suez, Panama, Kiel, Malacca...) or "avoids" it (the Arctic while closed, Skagen where
the Kiel canal is shorter) (cases/passages.csv).
Pass rule: the route between the two ports' positions over sea nodes (so that a sea-only
network runs it too) enters the box exactly when the reference says "enters". The route
is sampled every STEP_KM, so that a long straight arc across a box is seen.
"""

import math

import pytest
from conftest import cases
from scgraph.utils import haversine

MODES = ("sea",)
CASES = cases("passages")
STEP_KM = 5.0


def sampled(points):
    """The points of a path and points every STEP_KM along each of its segments
    (longitudes unwrapped across 180 degrees)."""
    out = list(points[:1])
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        lon2 += 360 if lon1 - lon2 > 180 else -360 if lon2 - lon1 > 180 else 0
        km = haversine((lat1, lon1), (lat2, lon2))
        steps = max(1, math.ceil(km / STEP_KM))
        for i in range(1, steps + 1):
            lat = lat1 + (lat2 - lat1) * i / steps
            lon = lon1 + (lon2 - lon1) * i / steps
            out.append((lat, (lon + 180) % 360 - 180))
    return out


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_passages(network, record, case):
    (lat1, lon1), (lat2, lon2) = case["origin"], case["destination"]
    route = network.get_shortest_path(
        {"latitude": lat1, "longitude": lon1},
        {"latitude": lat2, "longitude": lon2},
        silent=True,
    )
    south, west, north, east = (
        float(case[f"box_{side}"])
        for side in ("south", "west", "north", "east")
    )
    entered = any(
        south <= lat <= north and west <= lon <= east
        for lat, lon in sampled(route["coordinate_path"])
    )
    measured = "enters" if entered else "avoids"
    record(case, {"km": route["length"], "box": measured})
    assert measured == case["reference"], f"{measured} {case['passage']}"
