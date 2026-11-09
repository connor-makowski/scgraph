"""
Major freight rail corridors run end to end at their published length.

Reference: the corridor's published length (cases/rail_corridors.csv, read 2026-11-06;
its `note` says when the length is a composite of segments, or for another alignment
than the main freight line); endpoints from OSM Nominatim
(references/rail_corridors_geocode.py).
Pass rule: both endpoints have a rail node within SNAP_KM, and the route between these
two nodes is at most LONGER above and SHORTER below the published length. Missing or
broken links make routes longer; a shorter route is an alternative alignment (a
high-speed line, a cross-border shortcut, straight arcs that cut curves), so the lower
bound only catches a wrong reference or snap. Gauges and gauge breaks are in the cases,
never failed.
"""

import pytest
from conftest import cases, nearest_km, route_km

MODES = ("rail",)
CASES = cases("rail_corridors")
SNAP_KM = 10.0
LONGER = 0.10
SHORTER = 0.20


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_rail_corridors(network, record, case):
    (origin_km, origin), (destination_km, destination) = (
        nearest_km(network, case[end]) for end in ("origin", "destination")
    )
    km = route_km(network, origin, destination)
    record(case, {"snap_km": [origin_km, destination_km], "km": km})
    published = float(case["reference"])
    snap_km = max(origin_km, destination_km)
    assert snap_km <= SNAP_KM, f"rail {snap_km:.1f} km away"
    assert km is not None, f"no rail route vs {published} km"
    ratio = km / published - 1
    assert -SHORTER <= ratio <= LONGER, f"{km:.0f} km vs {published} km"
