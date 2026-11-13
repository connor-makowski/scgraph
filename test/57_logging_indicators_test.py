import logging

import pytest
from scgraph import GeoGraph

# A line of four nodes, 1 degree apart along the equator
line = GeoGraph(
    nodes=[[0.0, 0.0], [0.0, 1.0], [0.0, 2.0], [0.0, 3.0]],
    graph=[{1: 111.2}, {0: 111.2, 2: 111.2}, {1: 111.2, 3: 111.2}, {2: 111.2}],
)


def _read_indicators_of_the_query(caplog):
    """The values that the step `find the shortest path` logged at DEBUG. The
    test fails if the step logged more than once."""
    (indicators,) = [
        record.scgraph
        for record in caplog.records
        if getattr(record, "scgraph", {}).get("step")
        == "find the shortest path"
    ]
    return indicators


@pytest.mark.parametrize(
    "algorithm, algorithm_kwargs",
    [
        ("dijkstra", {}),
        ("bidirectional_dijkstra", {}),
        ("dijkstra_buckets", {}),
        ("bidirectional_buckets", {}),
        ("a_star", {"heuristic_fn": line.haversine}),
    ],
)
def test_a_query_logs_the_work_of_its_search_at_debug(
    caplog, algorithm, algorithm_kwargs
):
    with caplog.at_level(logging.DEBUG, logger="scgraph"):
        route = line.get_shortest_path(
            {"latitude": 0.0, "longitude": 0.0},
            {"latitude": 0.0, "longitude": 3.0},
            algorithm_fn=algorithm,
            algorithm_kwargs=algorithm_kwargs,
            output_path=True,
        )
    indicators = _read_indicators_of_the_query(caplog)
    assert indicators["algorithm"] == algorithm
    # A search scans every node of the route, except perhaps the last one
    assert indicators["node_scans"] >= len(route["path"]) - 1


def test_a_query_logs_how_far_its_ends_are_from_the_network(caplog):
    with caplog.at_level(logging.DEBUG, logger="scgraph"):
        line.get_shortest_path(
            # 0.1 degree north of the first node, 0.2 degree north of the last
            {"latitude": 0.1, "longitude": 0.0},
            {"latitude": 0.2, "longitude": 3.0},
        )
    indicators = _read_indicators_of_the_query(caplog)
    # 0.1 degree of latitude is 11.12 km. The log gives the straight distance,
    # without the circuity factor of the query
    assert indicators["origin_snap_distance"] == pytest.approx(11.12, abs=0.01)
    assert indicators["destination_snap_distance"] == pytest.approx(
        22.24, abs=0.01
    )


def test_a_search_that_counts_nothing_logs_no_node_scans(caplog):
    ends = (
        {"latitude": 0.0, "longitude": 0.0},
        {"latitude": 0.0, "longitude": 3.0},
    )
    # The Dijkstra search counts its node scans. Bellman-Ford counts nothing:
    # its log must not repeat the count of the search before
    line.get_shortest_path(*ends, algorithm_fn="dijkstra")
    with caplog.at_level(logging.DEBUG, logger="scgraph"):
        line.get_shortest_path(*ends, algorithm_fn="bellman_ford")
    indicators = _read_indicators_of_the_query(caplog)
    assert "node_scans" not in indicators
