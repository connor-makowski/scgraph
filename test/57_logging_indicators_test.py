import logging

import pytest
from scgraph import GeoGraph

# A line of four nodes, 1 degree apart along the equator
line = GeoGraph(
    nodes=[[0.0, 0.0], [0.0, 1.0], [0.0, 2.0], [0.0, 3.0]],
    graph=[{1: 111.2}, {0: 111.2, 2: 111.2}, {1: 111.2, 3: 111.2}, {2: 111.2}],
)


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
            # 0.1 degree north of the first node
            {"latitude": 0.1, "longitude": 0.0},
            {"latitude": 0.0, "longitude": 3.0},
            algorithm_fn=algorithm,
            algorithm_kwargs=algorithm_kwargs,
            output_path=True,
        )
    (indicators,) = [
        record.scgraph
        for record in caplog.records
        if getattr(record, "scgraph", {}).get("step")
        == "find the shortest path"
    ]
    assert indicators["algorithm"] == algorithm
    # 0.1 degree of latitude is 11.12 km, whatever the circuity of the query
    assert indicators["origin_snap_distance"] == pytest.approx(11.12, abs=0.01)
    # The search scans at least the nodes of the route before the last one
    assert indicators["node_scans"] >= len(route["path"]) - 1


def test_a_search_that_counts_nothing_logs_no_node_scans(caplog):
    ends = (
        {"latitude": 0.0, "longitude": 0.0},
        {"latitude": 0.0, "longitude": 3.0},
    )
    # Dijkstra leaves its count in the thread; Bellman-Ford counts nothing
    line.get_shortest_path(*ends, algorithm_fn="dijkstra")
    with caplog.at_level(logging.DEBUG, logger="scgraph"):
        line.get_shortest_path(*ends, algorithm_fn="bellman_ford")
    (indicators,) = [
        record.scgraph
        for record in caplog.records
        if getattr(record, "scgraph", {}).get("step")
        == "find the shortest path"
    ]
    assert "node_scans" not in indicators
