"""Tests of the default metric of a GeoGraph: the metric that a query without
`metric` minimises."""

import pytest

from scgraph import GeoGraph

# Three towns. A line of the drawing is one edge each way, with its km.
#
#           2 NORTH
#          /       \
#         2         2
#        /           \
#   0 WEST --- 3 --- 1 EAST
#
# The direct road is the shortest way from WEST to EAST: 3 km. It is slow: it
# takes 0.5 hour. Each other road takes 0.01 hour per km, so the way through
# NORTH is the fastest: 4 km in 0.04 hour.
WEST, EAST, NORTH = 0, 1, 2
# The points of a query from WEST to EAST. Each point is at its node: the
# route has no off-graph leg.
POINT_OF_WEST = {"latitude": 0.0, "longitude": 0.0}
POINT_OF_EAST = {"latitude": 0.0, "longitude": 0.02}


@pytest.fixture
def towns():
    geograph = GeoGraph(
        graph=[{EAST: 3, NORTH: 2}, {WEST: 3, NORTH: 2}, {WEST: 2, EAST: 2}],
        nodes=[[0.0, 0.0], [0.0, 0.02], [0.01, 0.01]],
    )
    geograph.create_metric(
        "hours",
        weight_per_km=0.01,
        edge_weights={(WEST, EAST): 0.5, (EAST, WEST): 0.5},
    )
    return geograph


def test_a_query_without_metric_minimises_the_default_metric(towns):
    towns.default_metric = "hours"

    route = towns.get_shortest_path(POINT_OF_WEST, POINT_OF_EAST)

    # The way through NORTH: 2 km + 2 km, in 0.02 h + 0.02 h.
    assert route["length"] == pytest.approx(4.0)
    assert route["metric_totals"]["hours"] == pytest.approx(0.04)


# An edit of the network removes its metrics. A query must then not return
# the shortest route in place of the fastest one.
def test_a_query_fails_when_the_geograph_lost_its_default_metric(towns):
    towns.default_metric = "hours"
    towns.remove_metric("hours")

    with pytest.raises(ValueError, match="`default_metric` of this geograph"):
        towns.get_shortest_path(POINT_OF_WEST, POINT_OF_EAST)
