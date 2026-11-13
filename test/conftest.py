import os

import pytest
from scgraph import GeoGraph
from scgraph.graph import Graph as PythonGraph
from scgraph.contraction_hierarchies import CHGraph as PythonCHGraph
from scgraph.transit_node_routing import TNRGraph as PythonTNRGraph
from helpers import CppCHGraph, CppGraph, CppTNRGraph
from scgraph.utils import resolve_cache_dir

# The graph classes of each build of scgraph that can be tested here.
_CLASSES = {
    "python": {
        "graph": PythonGraph,
        "ch": PythonCHGraph,
        "tnr": PythonTNRGraph,
    }
}
if CppGraph is not None:
    _CLASSES["cpp"] = {"graph": CppGraph, "ch": CppCHGraph, "tnr": CppTNRGraph}


@pytest.fixture(params=_CLASSES)
def build(request):
    # A test that takes graph_class, ch_class or tnr_class runs once with the
    # pure-Python classes. It runs once more with the C++ classes when the
    # extension is built. A test that takes two of them gets the two classes
    # of the same build.
    return request.param


@pytest.fixture
def graph_class(build):
    return _CLASSES[build]["graph"]


@pytest.fixture
def ch_class(build):
    return _CLASSES[build]["ch"]


@pytest.fixture
def tnr_class(build):
    return _CLASSES[build]["tnr"]


@pytest.fixture(scope="session", autouse=True)
def own_cache(tmp_path_factory):
    # The tests download into their own cache, never the user's: a temporary directory, or
    # SCGRAPH_CACHE_DIR if set (a cache filled once, to run the tests without downloading)
    if os.environ.get("SCGRAPH_CACHE_DIR"):
        yield
        return
    os.environ["SCGRAPH_CACHE_DIR"] = str(
        tmp_path_factory.mktemp("scgraph-cache")
    )
    yield
    del os.environ["SCGRAPH_CACHE_DIR"]


@pytest.fixture(scope="session")
def published():
    # A built-in network in the node numbering of its .graphjson, for the tests that name
    # nodes by id (load_geograph and network files number the nodes along a Hilbert curve)
    def load(name):
        GeoGraph.load_geograph(name)  # downloads the .graphjson into the cache
        return GeoGraph.load_from_graphjson(
            str(resolve_cache_dir().joinpath(f"{name}.graphjson"))
        )

    return load


@pytest.fixture(scope="session")
def marnet():
    return GeoGraph.load_geograph("marnet")


@pytest.fixture(scope="session")
def us_freeway():
    return GeoGraph.load_geograph("us_freeway")


@pytest.fixture(scope="session")
def oak_ridge_maritime():
    return GeoGraph.load_geograph("oak_ridge_maritime")


@pytest.fixture(scope="session")
def north_america_rail():
    return GeoGraph.load_geograph("north_america_rail")


@pytest.fixture(scope="session")
def world_highways_and_marnet():
    return GeoGraph.load_geograph("world_highways_and_marnet")
