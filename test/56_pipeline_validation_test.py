"""Tests for Stage 4 pipeline acceptance validation."""

import importlib

import pytest

from scgraph import pipelines
from scgraph.pipelines.steps.stage4_validation import (
    load_cases,
    validate_network,
)


# Every case that a pipeline names exists, under one id, and a region without
# cases gets none
def test_every_pipeline_names_existing_validation_cases():
    for name in pipelines.NAMES:
        contract = getattr(
            importlib.import_module(f"scgraph.pipelines.{name}"),
            "VALIDATION",
            None,
        )
        assert contract is None or load_cases(contract)
    regional = {"cases": {"europe/france": ["paris_marseille"]}}
    assert [
        case["id"] for case in load_cases(regional, region="europe/france")
    ] == ["paris_marseille"]
    assert load_cases(regional, region="europe/spain") == []
    with pytest.raises(ValueError, match="no_such_case"):
        load_cases({"cases": ["no_such_case"]})


@pytest.mark.parametrize(
    "name", ["marnet", "us_freeway", "north_america_rail", "oak_ridge_maritime"]
)
def test_published_network_passes_its_validation_cases(name, request):
    contract = importlib.import_module(f"scgraph.pipelines.{name}").VALIDATION
    result = validate_network(
        request.getfixturevalue(name), load_cases(contract)
    )
    assert result.is_success, result.failures
    assert result.passed == len(contract["cases"])


def test_validation_constraints(marnet):
    """Verify tolerance, min_km, max_km and bounding corridor checks."""
    # Case with too strict tolerance should fail
    strict_case = [
        {
            "id": "strict_rotterdam_nyc",
            "origin": (51.95, 4.14),
            "destination": (40.71, -74.01),
            "expected_km": 5000.0,
            "tolerance": 0.01,
        }
    ]
    res_strict = validate_network(marnet, strict_case)
    assert not res_strict.is_success
    assert res_strict.failed == 1

    # Case with corridor check (passes through Atlantic box)
    corridor_case = [
        {
            "id": "atlantic_transit",
            "origin": (51.95, 4.14),
            "destination": (40.71, -74.01),
            "expected_km": 6151.0,
            "tolerance": 0.05,
            "enters_box": (30.0, -60.0, 55.0, -10.0),
        }
    ]
    res_corridor = validate_network(marnet, corridor_case)
    assert res_corridor.is_success

    # Case avoiding Pacific box
    avoid_case = [
        {
            "id": "avoid_pacific",
            "origin": (51.95, 4.14),
            "destination": (40.71, -74.01),
            "avoids_box": (-20.0, -170.0, 20.0, -100.0),
        }
    ]
    res_avoid = validate_network(marnet, avoid_case)
    assert res_avoid.is_success

    # Snapping distance limit exceeded
    offshore_case = [
        {
            "id": "deep_inland_node",
            "origin": (0.0, 25.0),
            "destination": (40.71, -74.01),
        }
    ]
    res_snap = validate_network(marnet, offshore_case, max_snap_km=50.0)
    assert not res_snap.is_success
    assert "Snapping" in res_snap.failures[0]["error"]
