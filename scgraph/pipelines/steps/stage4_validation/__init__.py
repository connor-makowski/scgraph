"""Stage 4: Pipeline acceptance testing and route certification.

Provides validation runners that verify compiled networks against declarative
acceptance test cases (distances, tolerances, and passage corridors).
"""

from dataclasses import dataclass, field
import logging
from typing import Any

from scgraph.utils import haversine

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Summary of pipeline validation checks."""

    passed: int = 0
    failed: int = 0
    total: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """True if all validation cases passed."""
        return self.failed == 0 and self.total > 0

    def summary(self) -> str:
        """Formatted human-readable summary of validation results."""
        status = "PASSED" if self.is_success else "FAILED"
        return f"{status}: {self.passed}/{self.total} checks OK (failed: {self.failed})"


def _to_lat_lon(
    point: tuple[float, float] | dict[str, float],
) -> tuple[float, float]:
    """Normalize input coordinate to (lat, lon) tuple."""
    if isinstance(point, dict):
        return float(point["latitude"]), float(point["longitude"])
    return float(point[0]), float(point[1])


def _sampled_points(
    coordinates: list[list[float]], step: int = 10
) -> list[list[float]]:
    """Sample points along a coordinate path for corridor bounding-box checks."""
    if len(coordinates) <= step:
        return coordinates
    return coordinates[::step] + [coordinates[-1]]


def validate_network(
    network: Any,
    cases: list[dict[str, Any]],
    *,
    max_snap_km: float = 50.0,
    silent: bool = True,
) -> ValidationResult:
    """Validate a GeoGraph against declarative acceptance cases.

    Args:
        network: Instantiated GeoGraph object.
        cases: List of validation test case dictionaries.
        max_snap_km: Maximum allowable snapping distance to network nodes.
        silent: If True, suppress log warnings on failures.

    Returns:
        ValidationResult detailing passed, failed, and measured case metrics.
    """
    result = ValidationResult(total=len(cases))

    for case in cases:
        case_id = case.get("id", "unnamed_case")
        origin = _to_lat_lon(case["origin"])
        destination = _to_lat_lon(case["destination"])

        # Check snapping distance
        try:
            closest_origin = network.snap_index.closest_idx(point=list(origin))
            closest_dest = network.snap_index.closest_idx(
                point=list(destination)
            )
            snap_orig_km = haversine(origin, network.nodes[closest_origin])
            snap_dest_km = haversine(destination, network.nodes[closest_dest])
        except Exception as error:
            result.failed += 1
            entry = {
                "id": case_id,
                "error": f"Snapping failed: {error}",
                "case": case,
            }
            result.failures.append(entry)
            result.details.append(entry)
            continue

        if snap_orig_km > max_snap_km or snap_dest_km > max_snap_km:
            result.failed += 1
            entry = {
                "id": case_id,
                "error": (
                    f"Snapping exceeds {max_snap_km} km: origin {snap_orig_km:.1f} km, "
                    f"destination {snap_dest_km:.1f} km"
                ),
                "case": case,
            }
            result.failures.append(entry)
            result.details.append(entry)
            continue

        # Route computation
        try:
            need_path = "enters_box" in case or "avoids_box" in case
            route = network.get_shortest_path(
                {"latitude": origin[0], "longitude": origin[1]},
                {"latitude": destination[0], "longitude": destination[1]},
                length_only=not need_path,
                silent=True,
            )
            measured_km = float(route["length"])
        except Exception as error:
            result.failed += 1
            entry = {
                "id": case_id,
                "error": f"Routing failed (unconnected): {error}",
                "case": case,
            }
            result.failures.append(entry)
            result.details.append(entry)
            continue

        # Distance checks
        failure_reasons = []
        expected_km = case.get("expected_km")
        tolerance = case.get("tolerance", 0.05)

        if expected_km is not None:
            diff_ratio = abs(measured_km - expected_km) / expected_km
            if diff_ratio > tolerance:
                failure_reasons.append(
                    f"Length {measured_km:.1f} km deviates by {diff_ratio:.2%} "
                    f"from expected {expected_km:.1f} km (tolerance {tolerance:.0%})"
                )

        if "min_km" in case and measured_km < case["min_km"]:
            failure_reasons.append(
                f"Length {measured_km:.1f} km is below min_km {case['min_km']}"
            )
        if "max_km" in case and measured_km > case["max_km"]:
            failure_reasons.append(
                f"Length {measured_km:.1f} km exceeds max_km {case['max_km']}"
            )

        # Passage corridor checks
        if "enters_box" in case:
            south, west, north, east = case["enters_box"]
            entered = any(
                south <= lat <= north and west <= lon <= east
                for lat, lon in _sampled_points(
                    route.get("coordinate_path", [])
                )
            )
            if not entered:
                failure_reasons.append(
                    f"Route failed to enter box {case['enters_box']}"
                )

        if "avoids_box" in case:
            south, west, north, east = case["avoids_box"]
            entered = any(
                south <= lat <= north and west <= lon <= east
                for lat, lon in _sampled_points(
                    route.get("coordinate_path", [])
                )
            )
            if entered:
                failure_reasons.append(
                    f"Route entered forbidden box {case['avoids_box']}"
                )

        # Compile outcome
        detail = {
            "id": case_id,
            "measured_km": measured_km,
            "expected_km": expected_km,
            "snap_origin_km": snap_orig_km,
            "snap_destination_km": snap_dest_km,
            "is_success": len(failure_reasons) == 0,
        }
        if failure_reasons:
            result.failed += 1
            detail["errors"] = failure_reasons
            result.failures.append(detail)
            if not silent:
                logger.warning(
                    "Case %s FAILED: %s", case_id, "; ".join(failure_reasons)
                )
        else:
            result.passed += 1

        result.details.append(detail)

    return result
