"""
Island and strait crossings: road routes that need a bridge, a tunnel or a ferry.

Reference: the crossing a road trip takes between the two places (cases/crossings.csv,
references/coverage_cases.py; places from Natural Earth, two from Wikipedia).
Pass rule: both ends lie within MAX_SNAP_KM of a road node (rounded to 0.01 km), and a
road route joins them; without the first condition, a network with no road nearby would
pass by snapping across the water.
"""

import pytest
from conftest import cases, nearest_km, route_km

MODES = ("road",)
CASES = cases("crossings")
MAX_SNAP_KM = 5.0


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_crossings(network, record, case):
    a, b = case["origin"], case["destination"]
    snap_km = [round(nearest_km(network, end)[0], 2) for end in (a, b)]
    km = route_km(network, a, b)
    record(case, {"snap_km": snap_km, "km": km})
    assert max(snap_km) <= MAX_SNAP_KM, f"ends {snap_km} km off road"
    assert km is not None, f"no road route vs {case['reference']}"
