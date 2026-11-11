import pytest
from helpers import assert_result

# For each built-in network, one route and its published length. The two
# maritime routes cross the Pacific from one side of the antimeridian
# (longitude 180) to the other; the rail and road routes join two points of
# the United States less than 150 km apart.
PUBLISHED_ROUTES = {
    "marnet": {
        "origin": {"latitude": 30, "longitude": 160},
        "destination": {"latitude": 30, "longitude": -160},
        "length": 4477.148,
    },
    "oak_ridge_maritime": {
        "origin": {"latitude": 30, "longitude": 160},
        "destination": {"latitude": 30, "longitude": -160},
        "length": 3894.053,
    },
    "north_america_rail": {
        "origin": {"latitude": 48.325, "longitude": -102.352},
        "destination": {"latitude": 48.561, "longitude": -102.651},
        "length": 39.9236,
    },
    "us_freeway": {
        "origin": {"latitude": 41.129, "longitude": -85.158},
        "destination": {"latitude": 42.297, "longitude": -84.996},
        "length": 138.6748,
    },
}
BUILT_IN_NETWORKS = list(PUBLISHED_ROUTES)


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_built_in_network_has_links_in_both_directions(name, request):
    geograph = request.getfixturevalue(name)

    geograph.validate(check_symmetry=True, check_connected=False)


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_built_in_network_has_valid_coordinates(name, request):
    geograph = request.getfixturevalue(name)

    geograph.validate_nodes()


# marnet is the one built-in network that is required to be in one part.
def test_marnet_joins_every_two_of_its_nodes(marnet):
    marnet.validate(check_symmetry=False, check_connected=True)


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_built_in_network_gives_its_published_distance(name, request):
    geograph = request.getfixturevalue(name)
    published = PUBLISHED_ROUTES[name]

    route = geograph.get_shortest_path(
        origin_node=published["origin"],
        destination_node=published["destination"],
        algorithm_fn="dijkstra",
    )

    assert_result({"length": route["length"]}, {"length": published["length"]})


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_route_on_a_built_in_network_follows_its_links(name, request):
    geograph = request.getfixturevalue(name)
    origin = PUBLISHED_ROUTES[name]["origin"]
    destination = PUBLISHED_ROUTES[name]["destination"]

    route = geograph.get_shortest_path(
        origin_node=origin,
        destination_node=destination,
        algorithm_fn="dijkstra",
        output_path=True,
    )

    # A link of the network joins each node of the path to the next one
    path = route["path"]
    links = geograph.graph_object.graph
    assert all(v in links[u] for u, v in zip(path, path[1:]))
    # The requested origin, the point of each node of the path, the requested
    # destination
    assert route["coordinate_path"] == [
        [origin["latitude"], origin["longitude"]],
        *(geograph.nodes[node_id] for node_id in path),
        [destination["latitude"], destination["longitude"]],
    ]


# The four tests below compare an algorithm with Dijkstra on the published
# route of each network: the route does not depend on the algorithm.


@pytest.mark.parametrize("algorithm", ["bmssp", "bidirectional_dijkstra"])
@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_algorithm_finds_the_route_of_dijkstra(name, algorithm, request):
    geograph = request.getfixturevalue(name)
    query = {
        "origin_node": PUBLISHED_ROUTES[name]["origin"],
        "destination_node": PUBLISHED_ROUTES[name]["destination"],
    }

    found = geograph.get_shortest_path(**query, algorithm_fn=algorithm)

    assert_result(
        found, geograph.get_shortest_path(**query, algorithm_fn="dijkstra")
    )


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_a_star_with_the_haversine_heuristic_finds_the_route_of_dijkstra(
    name, request
):
    geograph = request.getfixturevalue(name)
    query = {
        "origin_node": PUBLISHED_ROUTES[name]["origin"],
        "destination_node": PUBLISHED_ROUTES[name]["destination"],
    }

    found = geograph.get_shortest_path(
        **query,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": geograph.haversine},
    )

    assert_result(
        found, geograph.get_shortest_path(**query, algorithm_fn="dijkstra")
    )


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_a_star_with_the_cheap_ruler_heuristic_finds_the_route_of_dijkstra(
    name, request
):
    geograph = request.getfixturevalue(name)
    query = {
        "origin_node": PUBLISHED_ROUTES[name]["origin"],
        "destination_node": PUBLISHED_ROUTES[name]["destination"],
    }

    found = geograph.get_shortest_path(
        **query,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": geograph.cheap_ruler},
    )

    assert_result(
        found, geograph.get_shortest_path(**query, algorithm_fn="dijkstra")
    )


@pytest.mark.parametrize("name", BUILT_IN_NETWORKS)
def test_cached_shortest_path_finds_the_route_of_dijkstra_twice(name, request):
    geograph = request.getfixturevalue(name)
    query = {
        "origin_node": PUBLISHED_ROUTES[name]["origin"],
        "destination_node": PUBLISHED_ROUTES[name]["destination"],
    }

    # The first call computes the shortest path tree of the origin and keeps
    # it; the second call reads the route in the tree it kept
    first = geograph.get_shortest_path(
        **query, algorithm_fn="cached_shortest_path"
    )
    second = geograph.get_shortest_path(
        **query, algorithm_fn="cached_shortest_path"
    )

    expected = geograph.get_shortest_path(**query, algorithm_fn="dijkstra")
    assert_result(first, expected)
    assert_result(second, expected)
