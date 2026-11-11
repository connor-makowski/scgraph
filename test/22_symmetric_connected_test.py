import pytest
from helpers import GRAPH_CLASSES

_CONNECTED = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
# The link 0 <-> 1 has another weight from 1 to 0
_ASYMMETRIC = [_CONNECTED[0], {**_CONNECTED[1], 0: 99}, *_CONNECTED[2:]]
_TWO_COMPONENTS = [*_CONNECTED, {7: 3}, {6: 3}]
# Node 0 reaches every node, and no node reaches node 0
_ONE_WAY_CHAIN = [{1: 5}, {2: 2}, {3: 4}, {}]


# validate() accepts a graph or refuses it according to the checks asked: the
# symmetry of its links, and a path between every two nodes. It refuses an
# empty graph. For symmetry and connectivity, C++ raises ValueError and
# RuntimeError and pure Python AssertionError, hence Exception.
@pytest.mark.parametrize(
    "graph_data, check_symmetry, check_connected, error",
    [
        (_CONNECTED, True, True, None),
        (_ASYMMETRIC, True, False, Exception),
        (_ASYMMETRIC, False, True, None),
        (_TWO_COMPONENTS, True, False, None),
        (_TWO_COMPONENTS, False, True, Exception),
        (_ONE_WAY_CHAIN, True, False, Exception),
        (_ONE_WAY_CHAIN, False, True, Exception),
        ([], True, True, ValueError),
    ],
)
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_validate_checks_symmetry_and_connectivity(
    GraphClass, graph_data, check_symmetry, check_connected, error
):
    graph = GraphClass(graph_data)
    checks = {
        "check_symmetry": check_symmetry,
        "check_connected": check_connected,
    }
    if error is None:
        graph.validate(**checks)
    else:
        with pytest.raises(error):
            graph.validate(**checks)
