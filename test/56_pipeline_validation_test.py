"""Tests for Stage 4 pipeline acceptance validation."""

import importlib

import pytest

from helpers import great_circle_km
from scgraph import GeoGraph, pipelines
from scgraph.pipelines.steps.stage4_validation import (
    load_cases,
    validate_network,
)


# Every pipeline lists its validation cases in `VALIDATION`. A case that a
# pipeline lists by its id must be a row of the files of cases.
@pytest.mark.parametrize("name", pipelines.NAMES)
def test_every_case_that_a_pipeline_lists_exists(name):
    pipeline = importlib.import_module(f"scgraph.pipelines.{name}")

    assert load_cases(pipeline.VALIDATION)


# A regional pipeline lists its cases by region. `paris_marseille` is a row of
# `cases/route_lengths.csv`.
CASES_BY_REGION = {"cases": {"europe/france": ["paris_marseille"]}}


def test_a_regional_pipeline_gets_the_cases_of_the_region_asked():
    cases = load_cases(CASES_BY_REGION, region="europe/france")

    assert [case["id"] for case in cases] == ["paris_marseille"]


def test_a_region_without_cases_gets_no_case():
    assert load_cases(CASES_BY_REGION, region="europe/spain") == []


def test_a_case_that_is_in_no_file_of_cases_is_refused():
    with pytest.raises(ValueError, match="no_such_case"):
        load_cases({"cases": ["no_such_case"]})


@pytest.mark.parametrize(
    "name", ["marnet", "us_freeway", "north_america_rail", "oak_ridge_maritime"]
)
def test_published_network_passes_its_validation_cases(name, request):
    validation = importlib.import_module(f"scgraph.pipelines.{name}").VALIDATION
    result = validate_network(
        request.getfixturevalue(name), load_cases(validation)
    )
    assert result.is_success, result.failures
    assert result.passed == len(validation["cases"])


# The tests below use a network of two towns on the equator, one degree of
# longitude apart: 111.19 km on a sphere of radius 6371 km. One road joins them.
WEST_TOWN, EAST_TOWN = (0, 0), (0, 1)
ROAD_KM = great_circle_km(WEST_TOWN, EAST_TOWN)


@pytest.fixture
def two_towns():
    return GeoGraph(
        graph=[{1: ROAD_KM}, {0: ROAD_KM}],
        nodes=[list(WEST_TOWN), list(EAST_TOWN)],
    )


def a_case(kind, **fields):
    """A case between the two towns, with the fields of a row of `cases/<kind>.csv`."""
    return {
        "id": "west_town_east_town",
        "kind": kind,
        "origin": WEST_TOWN,
        "destination": EAST_TOWN,
        "tolerance": None,
        "reference_back": None,
        **fields,
    }


def test_a_route_of_the_reference_length_passes(two_towns):
    result = validate_network(
        two_towns, [a_case("route_lengths", reference=ROAD_KM)]
    )

    assert result.is_success


def test_a_route_much_longer_than_its_reference_fails(two_towns):
    # The reference says 50 km and the road is 111 km long
    result = validate_network(
        two_towns, [a_case("route_lengths", reference=50)]
    )

    assert not result.is_success
    assert result.failures[0]["id"] == "west_town_east_town"


def test_a_road_distance_fails_when_the_road_goes_one_way_only():
    one_way_road = GeoGraph(
        graph=[{1: ROAD_KM}, {}], nodes=[list(WEST_TOWN), list(EAST_TOWN)]
    )

    result = validate_network(
        one_way_road, [a_case("road_distances", reference=ROAD_KM)]
    )

    assert result.failures[0]["error"] == "no road route"


def test_a_crossing_fails_when_one_end_is_far_from_any_road(two_towns):
    # One degree of latitude north of the road: 111 km away, the limit is 5 km
    island = (1, 0.5)

    result = validate_network(
        two_towns, [a_case("crossings", destination=island, reference="ferry")]
    )

    assert "km from a road" in result.failures[0]["error"]


# A passage case gives a box. Here the box lies across the road, half way.
BOX_ACROSS_THE_ROAD = {
    "box_south": -0.1,
    "box_north": 0.1,
    "box_west": 0.4,
    "box_east": 0.6,
    "passage": "the middle of the road",
}


def test_a_passage_case_passes_when_the_route_enters_its_box(two_towns):
    result = validate_network(
        two_towns,
        [a_case("passages", reference="enters", **BOX_ACROSS_THE_ROAD)],
    )

    assert result.is_success


def test_a_passage_case_fails_when_the_route_should_stay_out_of_its_box(
    two_towns,
):
    result = validate_network(
        two_towns,
        [a_case("passages", reference="avoids", **BOX_ACROSS_THE_ROAD)],
    )

    assert not result.is_success


def test_coverage_passes_when_one_city_in_a_hundred_has_no_road(two_towns):
    # 99 cities at the west town, whose main city is the east town, and one city
    # 111 km north of the road
    cities = [a_case("coverage", id=f"city_{n}") for n in range(99)]
    far_city = a_case("coverage", id="far_city", origin=(1, 0))

    assert validate_network(two_towns, cities + [far_city]).is_success


def test_coverage_fails_when_two_cities_in_a_hundred_have_no_road(two_towns):
    cities = [a_case("coverage", id=f"city_{n}") for n in range(98)]
    far_cities = [
        a_case("coverage", id=f"far_city_{n}", origin=(1, 0)) for n in range(2)
    ]

    result = validate_network(two_towns, cities + far_cities)

    assert [failure["id"] for failure in result.failures] == [
        "far_city_0",
        "far_city_1",
    ]


def test_a_road_distance_is_not_met_by_a_sea_route(tmp_path):
    # The two towns have no road between them. A sea node near each town and a
    # sea link join them. The network is read from a file, on its road mode only.
    file = str(tmp_path / "towns_joined_by_sea.scgraph")
    GeoGraph(
        graph=[{2: 1.0}, {3: 1.0}, {0: 1.0, 3: ROAD_KM}, {1: 1.0, 2: ROAD_KM}],
        nodes=[list(WEST_TOWN), list(EAST_TOWN), [0.01, 0], [0.01, 1]],
        node_modes=[0, 0, 1, 1],
        modes=[{"name": "road"}, {"name": "sea"}],
    ).save_as_scgraph(file)

    result = validate_network(
        file, [a_case("road_distances", reference=ROAD_KM)]
    )

    assert result.failures[0]["error"] == "no road route"


def test_a_road_distance_fails_when_the_route_is_much_shorter_than_driving(
    two_towns,
):
    # The reference says 140 km and the road is 111 km long: 21 % shorter, and
    # the limit is 10 %
    result = validate_network(
        two_towns, [a_case("road_distances", reference=140)]
    )

    assert result.failures[0]["error"] == "111 km against 140 km"


def test_a_rail_corridor_fails_when_the_route_is_much_longer_than_published(
    two_towns,
):
    # The published length is 95 km and the route is 111 km long: 17 % longer,
    # and the limit is 10 %
    result = validate_network(
        two_towns, [a_case("rail_corridors", reference=95)]
    )

    assert result.failures[0]["error"] == "111 km against 95 km"


def test_a_sea_distance_fails_when_it_is_far_from_the_published_distance(
    two_towns,
):
    # The published distance is 160 km and the route is 111 km long. The
    # difference is above both limits: 10 % and 30 km.
    result = validate_network(
        two_towns, [a_case("sea_distances", reference=160)]
    )

    assert result.failures[0]["error"] == "111 km against 160 km"


def test_a_river_port_fails_when_no_node_is_near_the_port(two_towns):
    # 0.06 degree of latitude north of the west town: 6.7 km away, and the
    # limit is 5 km
    port = (0.06, 0)

    result = validate_network(two_towns, [a_case("river_ports", origin=port)])

    assert result.failures[0]["error"] == "the nearest port node is 6.7 km away"
