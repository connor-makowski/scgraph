"""
Sea distances between major ports (Suez, Panama, across 180 degrees, around the Capes).

Reference: CERDI-seadistance when CERDI's ports are the case's ports, else NGA Pub. 151
(cases/sea_distances.csv keeps both values when it has them).
Pass rule: the water route between the two ports is within TOLERANCE of the reference
(the deviation rounded to 0.01 %), or within MIN_KM of it for short pairs, where the
approach to each port weighs. A port is its port node within JOIN_KM of its World Port
Index position (as in test_river_ports). A port without one is not joined, which
test_river_ports judges: the sea node nearest the port stands in for it (its join
distance is recorded), so that this test judges sea distances only.
"""

import pytest
from conftest import cases, nearest_km, route_km

MODES = ("port", "sea")
CASES = cases("sea_distances")
TOLERANCE = 0.10
MIN_KM = 30.0
JOIN_KM = 5.0


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_sea_distances(network, record, case):
    ends, measured = [], {}
    for end in ("origin", "destination"):
        join_km, node = nearest_km(network, case[end], "port")
        if join_km > JOIN_KM:  # not joined
            node = nearest_km(network, case[end], "sea")[1]
        ends.append(node)
        measured[f"{end}_join_km"] = join_km
    km = measured["km"] = route_km(network, *ends)
    record(case, measured)
    reference = float(case["reference"])
    assert km is not None, f"no water route vs {reference} km"
    deviation = round(km / reference - 1, 4)
    close = abs(deviation) <= TOLERANCE or abs(km - reference) <= MIN_KM
    assert close, f"{km:.0f} km vs {reference:.0f} km"
