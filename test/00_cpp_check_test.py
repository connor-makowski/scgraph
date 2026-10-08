import os

from scgraph.utils import has_cpp
from scgraph import Graph


def test_cpp_availability():
    require_cpp = os.environ.get("SCGRAPH_REQUIRE_CPP") == "1"
    require_python = (
        os.environ.get("SCGRAPH_REQUIRE_PYTHON") == "1"
        or os.environ.get("SCGRAPH_SKIP_CPP") == "1"
    )
    assert not (
        require_cpp and require_python
    ), "Conflicting build expectations"
    if require_cpp:
        assert (
            has_cpp()
        ), "SCGRAPH_REQUIRE_CPP=1 but the extension is unavailable"
        assert Graph.__module__ == "scgraph.cpp"
    elif require_python:
        assert (
            not has_cpp()
        ), "Expected an installation without the C++ extension"
        assert Graph.__module__ == "scgraph.graph"


if __name__ == "__main__":
    test_cpp_availability()
