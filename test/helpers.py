import math

from scgraph.graph import Graph as PyGraph
from scgraph.utils import hard_round

# The graph classes a test of both implementations is parametrised with: the pure-Python
# class and, when the extension is built, the C++ class
try:
    from scgraph.cpp import Graph as CppGraph

    GRAPH_CLASSES = [PyGraph, CppGraph]
except ImportError:
    GRAPH_CLASSES = [PyGraph]


def assert_result(realized, expected):
    if isinstance(realized, dict) and "length" in realized:
        realized = {**realized, "length": hard_round(3, realized["length"])}
    if isinstance(expected, dict) and "length" in expected:
        expected = {**expected, "length": hard_round(3, expected["length"])}
    assert realized == expected


def great_circle_km(a, b):
    """Great-circle distance between [lat, lon] points (R = 6371 km), written apart from
    scgraph's own formula so that tests check it."""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))
