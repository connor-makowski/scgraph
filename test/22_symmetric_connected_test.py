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
    with pytest.raises(Exception):
        _ASYMMETRIC.validate(check_symmetry=True, check_connected=False)


def test_asymmetric_connectivity_passes():
    _ASYMMETRIC.validate(check_symmetry=False, check_connected=True)


def test_disconnected_symmetry_passes():
    _SYMMETRIC_DISCONNECTED.validate(check_symmetry=True, check_connected=False)


def test_disconnected_connectivity_raises():
    with pytest.raises(Exception):
        _SYMMETRIC_DISCONNECTED.validate(
            check_symmetry=False, check_connected=True
        )


def test_one_way_disconnected_raises():
    with pytest.raises(Exception):
        _ONE_WAY_DISCONNECTED.validate(
            check_symmetry=False, check_connected=True
        )
