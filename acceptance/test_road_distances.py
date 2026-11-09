"""
Road distances between city pairs on every inhabited continent, both ways.

Reference: OSRM driving distances, one query per direction, frozen
(cases/road_distances.csv, references/road_distances_osrm.py); city centres from Natural
Earth.
Pass rule: each direction, with scgraph's coordinate query (each end snapped to its
nearest road node, the legs off the network included), is within TOLERANCE of its OSRM
value, or of the case's own `tolerance` (its reason in `tolerance_reason`); and the two
directions differ by at most MAX_ASYMMETRY of their mean. Percents are rounded (to 0.1 %
and 0.01 %) before they are judged, as when the thresholds were set.
"""

import pytest
from conftest import cases, route_km

MODES = ("road",)
CASES = cases("road_distances")
TOLERANCE = 0.10
MAX_ASYMMETRY = 0.05


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_road_distances(network, record, case):
    a, b = case["origin"], case["destination"]
    km = [route_km(network, a, b), route_km(network, b, a)]
    record(case, {"km": km})
    osrm = [float(case["reference"]), float(case["reference_back"])]
    assert None not in km, f"no road route vs {osrm} km"
    diff_pct = [round(100 * (k / o - 1), 1) for k, o in zip(km, osrm)]
    within = max(map(abs, diff_pct)) <= 100 * (case["tolerance"] or TOLERANCE)
    assert within, f"{diff_pct} % vs OSRM {osrm} km"
    asymmetry = round(100 * abs(km[0] - km[1]) / (sum(km) / 2), 2)  # percent
    assert asymmetry <= 100 * MAX_ASYMMETRY, f"directions {asymmetry} % apart"
