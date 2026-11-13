import math

import pytest

from scgraph.utils import hard_round

# The classes of the C++ extension, or None when the extension is not built.
try:
    from scgraph.cpp import CHGraph as CppCHGraph
    from scgraph.cpp import Graph as CppGraph
    from scgraph.cpp import TNRGraph as CppTNRGraph
except ImportError:
    CppGraph = CppCHGraph = CppTNRGraph = None

# The mark of a test that compares the C++ classes with the pure-Python ones,
# or that checks a behaviour of the C++ classes alone. Any other test takes
# the fixture graph_class, ch_class or tnr_class of conftest.py.
needs_the_cpp_extension = pytest.mark.skipif(
    CppGraph is None, reason="The C++ extension is not built"
)


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
