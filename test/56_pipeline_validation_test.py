"""Tests for Stage 4 pipeline acceptance validation."""

import pytest

from scgraph.pipelines.steps.stage4_validation import (
    ValidationResult,
    validate_network,
)
from scgraph.pipelines import (
    marnet as marnet_pipeline,
    north_america_rail as rail_pipeline,
    oak_ridge_maritime as orm_pipeline,
    us_freeway as freeway_pipeline,
)


def test_validation_result_summary():
    """Verify ValidationResult summary representation and status flag."""
    res_ok = ValidationResult(passed=3, failed=0, total=3)
    assert res_ok.is_success
    assert "PASSED: 3/3 checks OK" in res_ok.summary()

    res_fail = ValidationResult(
        passed=2,
        failed=1,
        total=3,
        failures=[{"id": "c1", "errors": ["Too long"]}],
    )
    assert not res_fail.is_success
    assert "FAILED: 2/3 checks OK (failed: 1)" in res_fail.summary()

    res_empty = ValidationResult(total=0)
    assert not res_empty.is_success


def test_validation_marnet(marnet):
    """Validate marnet against its declared Stage 4 test cases."""
    result = validate_network(marnet, marnet_pipeline.VALIDATION_CASES)
    assert result.is_success
    assert result.passed == len(marnet_pipeline.VALIDATION_CASES)
    assert len(result.failures) == 0


def test_validation_us_freeway(us_freeway):
    """Validate us_freeway against its declared Stage 4 test cases."""
    result = validate_network(us_freeway, freeway_pipeline.VALIDATION_CASES)
    assert result.is_success
    assert result.passed == len(freeway_pipeline.VALIDATION_CASES)


def test_validation_north_america_rail(north_america_rail):
    """Validate north_america_rail against its declared Stage 4 test cases."""
    result = validate_network(
        north_america_rail, rail_pipeline.VALIDATION_CASES
    )
    assert result.is_success
    assert result.passed == len(rail_pipeline.VALIDATION_CASES)


def test_validation_oak_ridge_maritime(oak_ridge_maritime):
    """Validate oak_ridge_maritime against its declared Stage 4 test cases."""
    result = validate_network(oak_ridge_maritime, orm_pipeline.VALIDATION_CASES)
    assert result.is_success
    assert result.passed == len(orm_pipeline.VALIDATION_CASES)


def test_validation_constraints(marnet):
    """Verify tolerance, min_km, max_km and bounding corridor checks."""
    # Case with too strict tolerance should fail
    strict_case = [
        {
            "id": "strict_rotterdam_nyc",
            "origin": (51.95, 4.14),
            "destination": (40.71, -74.01),
            "expected_km": 5000.0,  # real is ~6151 km
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
            "origin": (0.0, 25.0),  # Congo rainforest, far from any sea lane
            "destination": (40.71, -74.01),
        }
    ]
    res_snap = validate_network(marnet, offshore_case, max_snap_km=50.0)
    assert not res_snap.is_success
    assert "Snapping exceeds 50.0 km" in res_snap.failures[0]["error"]
