import pytest
from scgraph import GeoGraph, PathNotFoundError

# Two pairs of nodes far apart, with no arc between the pairs: no route joins them
graph_in_two_parts = GeoGraph(
    nodes=[[0.0, 0.0], [0.1, 0.1], [50.0, 50.0], [50.1, 50.1]],
    graph=[{1: 15.0}, {0: 15.0}, {3: 15.0}, {2: 15.0}],
)
origin = {"latitude": 0.0, "longitude": 0.0}
destination = {"latitude": 50.0, "longitude": 50.0}


def test_a_query_without_a_route_prints_nothing(capsys):
    with pytest.raises(PathNotFoundError):
        graph_in_two_parts.get_shortest_path(origin, destination)
    assert capsys.readouterr().out == ""


def test_a_query_without_a_route_explains_in_a_note_of_the_exception():
    with pytest.raises(PathNotFoundError) as raised:
        graph_in_two_parts.get_shortest_path(origin, destination)
    assert "destination_node_addition_type='all'" in str(raised.value.__notes__)


def test_the_silent_parameter_is_deprecated():
    with pytest.warns(DeprecationWarning, match="silent"):
        with pytest.raises(PathNotFoundError):
            graph_in_two_parts.get_shortest_path(
                origin, destination, silent=True
            )


def test_distance_matrix_warns_once_with_the_number_of_pairs_without_a_route():
    with pytest.warns(UserWarning, match="^2 pair"):
        matrix = graph_in_two_parts.distance_matrix([origin, destination])
    # The pairs (origin, destination) and (destination, origin) have no route
    assert matrix == [[0.0, None], [None, 0.0]]
