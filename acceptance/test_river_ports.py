"""
Large river, estuary and lake ports reach the sea by water.

Reference: the great circle from the port to the sea, at an offshore point chosen at its
waterway's mouth (cases/river_ports.csv; ports at their World Port Index position).
Pass rule: a port node lies within JOIN_KM of the port, and the water route from it to
the sea node nearest the offshore point is at most MAX_RATIO times the great circle
between the two nodes.
"""

import pytest
from conftest import cases, nearest_km, route_km
from scgraph.utils import haversine

MODES = ("port", "sea")
CASES = cases("river_ports")
JOIN_KM = 5.0
MAX_RATIO = 1.8


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_river_ports(network, record, case):
    join_km, port = nearest_km(network, case["origin"], "port")
    _, sea = nearest_km(network, case["destination"], "sea")
    km = route_km(network, port, sea)
    ratio = None if km is None else round(km / haversine(port, sea), 2)
    record(case, {"join_km": join_km, "water_route_km": km, "ratio": ratio})
    assert join_km <= JOIN_KM, f"port node at {join_km:.1f} km vs {JOIN_KM}"
    assert ratio is not None, f"no water route to the sea"
    assert ratio <= MAX_RATIO, f"{ratio} x the great circle vs {MAX_RATIO}"
