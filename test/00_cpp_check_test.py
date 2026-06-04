import os

from scgraph.utils import has_cpp


def test_cpp_availability():
    should_have_cpp = os.environ.get("SCGRAPH_SKIP_CPP") != "1"
    assert (
        has_cpp() == should_have_cpp
    ), f"Expected C++ availability to be {should_have_cpp} but got {has_cpp()} instead"
