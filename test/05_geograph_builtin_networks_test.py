import pytest
from helpers import assert_result

_PACIFIC = (
    {"latitude": 30, "longitude": 160},
    {"latitude": 30, "longitude": -160},
)
# For each built-in network: an origin, a destination and the published length
# of the route between them
_ROUTES = {
    "marnet": (*_PACIFIC, 4477.148),
    "oak_ridge_maritime": (*_PACIFIC, 3894.053),
    "north_america_rail": (
        {"latitude": 48.325, "longitude": -102.352},
        {"latitude": 48.561, "longitude": -102.651},
        39.9236,
    ),
    "us_freeway": (
        {"latitude": 41.129, "longitude": -85.158},
        {"latitude": 42.297, "longitude": -84.996},
        138.6748,
    ),
}


# A built-in network has valid coordinates and symmetric links; marnet is also
# connected.
@pytest.mark.parametrize("name", list(_ROUTES))
def test_built_in_network_is_valid(name, request):
    geograph = request.getfixturevalue(name)
    geograph.validate(check_symmetry=True, check_connected=name == "marnet")
    geograph.validate_nodes()


# A built-in network gives its published distance, on a route that goes from
# the origin to the destination through nodes that links of the network join.
@pytest.mark.parametrize("name", list(_ROUTES))
def test_built_in_network_gives_its_published_distance(name, request):
    geograph = request.getfixturevalue(name)
    origin, destination, length = _ROUTES[name]
    route = geograph.get_shortest_path(
        origin_node=origin,
        destination_node=destination,
        algorithm_fn="dijkstra",
        output_path=True,
    )
    assert_result({"length": route["length"]}, {"length": length})
    path = route["path"]
    graph = geograph.graph_object.graph
    assert all(v in graph[u] for u, v in zip(path, path[1:]))
    assert route["coordinate_path"] == [
        [origin["latitude"], origin["longitude"]],
        *(geograph.nodes[node_id] for node_id in path),
        [destination["latitude"], destination["longitude"]],
    ]


# The route does not depend on the algorithm. It is asked twice, so that the
# second answer of cached_shortest_path comes from the tree it kept.
@pytest.mark.parametrize(
    "algorithm, heuristic",
    [
        ("a_star", "haversine"),
        ("a_star", "cheap_ruler"),
        ("bmssp", None),
        ("bidirectional_dijkstra", None),
        ("cached_shortest_path", None),
    ],
)
@pytest.mark.parametrize("name", list(_ROUTES))
def test_route_does_not_depend_on_the_algorithm(
    name, algorithm, heuristic, request
):
    geograph = request.getfixturevalue(name)
    origin, destination, _ = _ROUTES[name]
    query = {"origin_node": origin, "destination_node": destination}
    expected = geograph.get_shortest_path(**query, algorithm_fn="dijkstra")
    if heuristic:
        query["algorithm_kwargs"] = {
            "heuristic_fn": getattr(geograph, heuristic)
        }
    for _ in range(2):
        assert_result(
            geograph.get_shortest_path(**query, algorithm_fn=algorithm),
            expected,
        )
