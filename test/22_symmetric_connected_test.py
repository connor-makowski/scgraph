import pytest
from scgraph import Graph

_SYMMETRIC_CONNECTED = Graph(
    [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]
)
_ASYMMETRIC = Graph(
    [
        {1: 5, 2: 1},
        {0: 99, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]
)
_SYMMETRIC_DISCONNECTED = Graph(
    [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
        {7: 3},
        {6: 3},
    ]
)
_ONE_WAY_DISCONNECTED = Graph([{1: 5}, {2: 2}, {3: 4}, {}])


def test_symmetric_connected_both():
    _SYMMETRIC_CONNECTED.validate(check_symmetry=True, check_connected=True)


def test_symmetric_connected_symmetry_only():
    _SYMMETRIC_CONNECTED.validate(check_symmetry=True, check_connected=False)


def test_symmetric_connected_connectivity_only():
    _SYMMETRIC_CONNECTED.validate(check_symmetry=False, check_connected=True)


def test_asymmetric_symmetry_raises():
    with pytest.raises(ValueError, match="not symmetric"):
        _ASYMMETRIC.validate(check_symmetry=True, check_connected=False)


def test_asymmetric_connectivity_passes():
    _ASYMMETRIC.validate(check_symmetry=False, check_connected=True)


def test_disconnected_symmetry_passes():
    _SYMMETRIC_DISCONNECTED.validate(check_symmetry=True, check_connected=False)


def test_disconnected_connectivity_raises():
    with pytest.raises(RuntimeError, match="not fully connected"):
        _SYMMETRIC_DISCONNECTED.validate(
            check_symmetry=False, check_connected=True
        )


def test_one_way_disconnected_raises():
    with pytest.raises(RuntimeError, match="not fully connected"):
        _ONE_WAY_DISCONNECTED.validate(
            check_symmetry=False, check_connected=True
        )


# `validate` raises the same type with the C++ extension and in pure Python:
# TypeError for a value of the wrong type, ValueError for a wrong value. With
# the C++ class, the TypeError comes when the graph is created.
def test_validate_refuses_a_graph_that_is_not_a_list(graph_class):
    rows_in_a_dictionary = {0: {1: 1.0}, 1: {0: 1.0}}

    with pytest.raises(TypeError):
        graph_class(rows_in_a_dictionary).validate()


def test_validate_refuses_a_row_that_is_not_a_dictionary(graph_class):
    with pytest.raises(TypeError):
        graph_class([[1], [0]]).validate()


def test_validate_refuses_a_destination_id_that_is_not_an_integer(graph_class):
    with pytest.raises(TypeError):
        graph_class([{"1": 1.0}, {0: 1.0}]).validate()


def test_validate_refuses_a_distance_that_is_not_a_number(graph_class):
    with pytest.raises(TypeError):
        graph_class([{1: "far"}, {0: "far"}]).validate()


def test_validate_refuses_a_negative_distance(graph_class):
    with pytest.raises(ValueError, match="non-negative"):
        graph_class([{1: -1.0}, {0: -1.0}]).validate()
