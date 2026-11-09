"""
Road coverage: large cities reach the main road network of their landmass.

Reference: every Natural Earth populated place with POP_MAX >= 500,000; its landmass is
the Natural Earth land polygon that holds it (the Americas split at the Darien Gap), and
the case's destination is the landmass's most populous city (cases/coverage.csv,
references/coverage_cases.py; rows disabled for Natural Earth errors say why).
Pass rule: at least MIN_SHARE of the cities snap to a road node within MAX_SNAP_KM, in
the strongly connected component of their main city's node. The rule is a share, so this
is one test over every city, each recorded. On a landmass with a single listed city (New
York on Manhattan, Singapore...), only the distance rule tests it.
Assumption: the build leaves no arc between two kept components, so a route from the
main city to a city means that both lie in one strongly connected component.
"""

from itertools import groupby

from conftest import cases, nearest_km, route_km

MODES = ("road",)
CASES = cases("coverage")
MAX_SNAP_KM = 5.0
MIN_SHARE = 0.99


def same_component(network, main, city):
    """Whether a route joins the main city to the city (see the assumption), read from
    the shortest path tree of the main city's node, computed once and cached."""
    km = route_km(network, main, city, algorithm_fn="cached_shortest_path")
    return km is not None


def test_coverage(network, record):
    failed = []
    by_landmass = sorted(CASES, key=lambda case: case["landmass"])
    for _, group in groupby(by_landmass, key=lambda case: case["landmass"]):
        network.graph_object.reset_cache()  # one tree kept: ~150 MB at 10 M nodes
        for case in group:
            city, main = case["origin"], case["destination"]
            snap_km, _ = nearest_km(network, city)
            joined = same_component(network, main, city)
            record(case, {"snap_km": snap_km, "same_component_as_main": joined})
            if not (snap_km <= MAX_SNAP_KM and joined):
                failed.append(case["id"])
    share = 1 - len(failed) / len(CASES)
    assert share >= MIN_SHARE, f"{share:.2%} vs {MIN_SHARE:.0%}: {failed}"
