import pytest
from scgraph import GeoGraph


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
