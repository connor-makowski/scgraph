import os

import pytest
from scgraph import GeoGraph


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
