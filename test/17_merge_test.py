from copy import deepcopy
import pytest
from scgraph import GeoGraph

_PORTS = [
    [42.3601, -71.0589],
    [40.7128, -74.0060],
    [39.9526, -75.1652],
    [39.2904, -76.6122],
    [38.9072, -77.0369],
    [32.0835, -81.0998],
    [32.7765, -79.9311],
    [30.3322, -81.6557],
    [25.7617, -80.1918],
    [27.9506, -82.4572],
    [29.9511, -90.0715],
    [29.7604, -95.3698],
    [34.0522, -118.2437],
    [37.7749, -122.4194],
    [47.6062, -122.3321],
    [45.5152, -122.6784],
]
_ATLANTA = {"latitude": 33.7490, "longitude": -84.3880}
_LONDON = {"latitude": 51.5074, "longitude": -0.1278}
_EXPECTED_FREEWAY_LENGTH = 7459.1121
_EXPECTED_MARNET_LENGTH = 8820.8927


def test_merge_and_route():
    freeway = GeoGraph.load_geograph("us_freeway")
    marnet = GeoGraph.load_geograph("marnet")
    freeway.merge_with_other_geograph(
        other_geograph=marnet,
        connection_nodes=_PORTS,
        circuity_to_current_geograph=1.1,
        circuity_to_other_geograph=1.3,
        node_addition_type_current_geograph="closest",
        node_addition_type_other_geograph="closest",
        node_addition_math="euclidean",
    )
    freeway_result = freeway.get_shortest_path(
        origin_node=_ATLANTA, destination_node=_LONDON
    )
    marnet_result = marnet.get_shortest_path(
        origin_node=_ATLANTA, destination_node=_LONDON
    )
    # The merged GeoGraph must route like a GeoGraph built from scratch on the
    # merged network (whose constructor indexes every node for snapping)
    rebuilt = GeoGraph(
        graph=deepcopy(freeway.graph_object.graph),
        nodes=deepcopy(freeway.nodes),
        default_off_graph_circuity=freeway.default_off_graph_circuity,
        default_node_addition_circuity=freeway.default_node_addition_circuity,
        geograph_units=freeway.geograph_units,
    )
    assert freeway_result == rebuilt.get_shortest_path(
        origin_node=_ATLANTA, destination_node=_LONDON
    )
    assert abs(freeway_result["length"] - _EXPECTED_FREEWAY_LENGTH) < 0.1
    assert abs(marnet_result["length"] - _EXPECTED_MARNET_LENGTH) < 0.1


def _chain(start_longitude):
    # Four nodes in a line: the two interior nodes are reduced by reduce()
    nodes = [[0, start_longitude + i] for i in range(4)]
    graph = [{1: 111.2}, {0: 111.2, 2: 111.2}, {1: 111.2, 3: 111.2}, {2: 111.2}]
    return GeoGraph(nodes=nodes, graph=graph)


@pytest.mark.parametrize(
    "reduce_current, reduce_other", [(True, False), (False, True)]
)
def test_merge_reduced_geographs(reduce_current, reduce_other):
    # Merging must use the original graphs, whether or not they were reduced.
    # No connection nodes: adding nodes would already undo reduce().
    expected = _chain(0)
    expected.merge_with_other_geograph(_chain(10), connection_nodes=[])
    current, other = _chain(0), _chain(10)
    if reduce_current:
        current.reduce()
    if reduce_other:
        other.reduce()
    current.merge_with_other_geograph(other, connection_nodes=[])
    assert current.graph_object.graph == expected.graph_object.graph
    assert current.nodes == expected.nodes
