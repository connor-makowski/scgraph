import os

import pytest
from scgraph.utils import has_cpp
from scgraph import Graph

# A test run says which build it expects with an environment variable, so that
# a build that fell back to pure Python without a word is noticed.
CPP_BUILD_IS_EXPECTED = os.environ.get("SCGRAPH_REQUIRE_CPP") == "1"
PURE_PYTHON_BUILD_IS_EXPECTED = (
    os.environ.get("SCGRAPH_REQUIRE_PYTHON") == "1"
    or os.environ.get("SCGRAPH_SKIP_CPP") == "1"
)


def test_run_does_not_expect_both_builds():
    assert not (
        CPP_BUILD_IS_EXPECTED and PURE_PYTHON_BUILD_IS_EXPECTED
    ), "Conflicting build expectations"


@pytest.mark.skipif(
    not CPP_BUILD_IS_EXPECTED, reason="the C++ build is not expected"
)
def test_cpp_build_gives_the_cpp_graph():
    assert has_cpp(), "SCGRAPH_REQUIRE_CPP=1 but the extension is unavailable"
    assert Graph.__module__ == "scgraph.cpp"


@pytest.mark.skipif(
    not CPP_BUILD_IS_EXPECTED, reason="the C++ build is not expected"
)
def test_cpp_build_has_the_native_route_coordinates():
    # Route coordinates are built natively: without this function the library
    # falls back to Python without a word
    import scgraph.cpp

    assert hasattr(scgraph.cpp, "coordinate_lists")


@pytest.mark.skipif(
    not PURE_PYTHON_BUILD_IS_EXPECTED,
    reason="the pure-Python build is not expected",
)
def test_pure_python_build_gives_the_python_graph():
    assert not has_cpp(), "Expected an installation without the C++ extension"
    assert Graph.__module__ == "scgraph.graph"
