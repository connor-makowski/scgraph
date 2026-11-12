"""Stage 4: Pipeline acceptance testing and route certification.

Validates compiled transportation networks against authoritative ground-truth
datasets (OSRM road distances, CERDI / NGA Pub. 151 maritime routes, FRA NTAD
Class I freight rail corridors, and strategic canal/strait passage boxes).
"""

import csv
from dataclasses import dataclass, field
from functools import lru_cache
import logging
import math
from pathlib import Path
from typing import Any

from scgraph.utils import haversine

logger = logging.getLogger(__name__)
CASES_DIR = Path(__file__).parent / "cases"


@dataclass
class ValidationResult:
    """Summary of pipeline validation checks.

    Attributes:
        passed (int): Number of acceptance checks that succeeded.
        failed (int): Number of acceptance checks that failed.
        total (int): Total number of acceptance cases evaluated.
        failures (list[dict[str, Any]]): Diagnostic failure records containing
            case ID, measured values, and error explanations.
    """

    passed: int = 0
    failed: int = 0
    total: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """True if every evaluated case passed with zero failures."""
        return self.failed == 0 and self.total > 0

    def summary(self) -> str:
        """Formatted human-readable summary of validation results.

        Returns:
            str: One-line summary string (e.g. 'PASSED: 5/5 checks OK').
        """
        status = "PASSED" if self.is_success else "FAILED"
        return f"{status}: {self.passed}/{self.total} checks OK (failed: {self.failed})"


def _to_lat_lon(point: Any) -> tuple[float, float]:
    """Normalize input coordinate to a (latitude, longitude) tuple.

    Parameters:
        point (tuple[float, float] | list[float] | dict[str, float]): Coordinate
            representation as a sequence of numbers or a dict with 'latitude'
            and 'longitude' keys.

    Returns:
        tuple[float, float]: Normalized (latitude, longitude) floats.
    """
    if isinstance(point, dict):
        return float(point["latitude"]), float(point["longitude"])
    return float(point[0]), float(point[1])


def _sampled_points(
    coordinates: list[list[float]], step_km: float = 5.0
) -> list[tuple[float, float]]:
    """Sample points along a coordinate path for bounding-box corridor checks.

    Interpolates intermediate positions every `step_km` along segments to ensure
    long, straight edges traversing corridors (e.g. across the Suez or Panama
    Canal bounding boxes) are reliably detected without aliasing. Unwraps
    longitudes across the antimeridian.

    Parameters:
        coordinates (list[list[float]]): Path coordinates as `[lat, lon]` pairs.
        step_km (float): Maximum sampling interval along segments in kilometres.

    Returns:
        list[tuple[float, float]]: Sampled sequence of `(lat, lon)` points.
    """
    if not coordinates:
        return []
    out = [_to_lat_lon(coordinates[0])]
    for i in range(len(coordinates) - 1):
        lat1, lon1 = _to_lat_lon(coordinates[i])
        lat2, lon2 = _to_lat_lon(coordinates[i + 1])
        lon2_unwrap = lon2 + (
            360 if lon1 - lon2 > 180 else -360 if lon2 - lon1 > 180 else 0
        )
        km = haversine((lat1, lon1), (lat2, lon2_unwrap))
        steps = max(1, math.ceil(km / step_km))
        for s in range(1, steps + 1):
            lat = lat1 + (lat2 - lat1) * s / steps
            lon = lon1 + (lon2_unwrap - lon1) * s / steps
            out.append((lat, (lon + 180) % 360 - 180))
    return out


def _row_to_case(row: dict[str, str]) -> dict[str, Any]:
    """Convert a raw CSV dictionary row into a standardized test case dict.

    Parameters:
        row (dict[str, str]): Key-value mapping representing a single CSV row.

    Returns:
        dict[str, Any]: Standardized case dictionary with origin, destination,
            tolerances, and expected distances or bounding box constraints.
    """
    case: dict[str, Any] = {
        "id": row["id"],
        "origin": (float(row["origin_lat"]), float(row["origin_lon"])),
        "destination": (
            float(row["destination_lat"]),
            float(row["destination_lon"]),
        ),
        "tolerance": float(row["tolerance"]) if row.get("tolerance") else 0.05,
    }
    ref = row.get("reference", "")
    if ref.replace(".", "", 1).isdigit():
        case["expected_km"] = float(ref)
    elif ref in ("enters", "avoids"):
        case[f"{ref}_box"] = tuple(
            float(row[f"box_{s}"]) for s in ("south", "west", "north", "east")
        )
    return case


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    """Index all test cases from CSV datasets by their unique case ID.

    Scans the `cases/` directory and parses road, rail, crossing, passage,
    river port, and sea distance datasets into an in-memory dictionary.
    Excludes large macro-coverage datasets.

    Returns:
        dict[str, dict[str, Any]]: Mapping of case ID to test case dictionary.
    """
    cases = {}
    for path in CASES_DIR.glob("*.csv"):
        if "coverage" in path.name:
            continue
        with open(path, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row["id"].startswith("#"):
                    continue
                if row["id"] in cases:
                    raise ValueError(
                        f"Validation case '{row['id']}' is defined twice; "
                        f"the second time in {path.name}"
                    )
                cases[row["id"]] = _row_to_case(row)
    return cases


def load_cases(
    contract: Any = None, region: str | None = None
) -> list[dict[str, Any]]:
    """Load and resolve validation test cases for a pipeline contract.

    Supports multiple declarative declaration patterns:
    - Dict with a list of case IDs: `{"cases": ["paris_berlin", ...]}`
    - Dict with a regional mapping: `{"cases": {"europe/france": [...], ...}}`
    - Raw list of case IDs or custom explicit dictionaries.

    Parameters:
        contract (dict | list | None): Declarative validation contract from a
            pipeline module, or a list of case ID strings / dicts.
        region (str | None): Geographic sub-region filter (e.g. 'europe/france',
            'europe/luxembourg'). Used to select region-specific cases.

    Returns:
        list[dict[str, Any]]: Resolved test case dictionaries containing
            origin, destination, expected distances, and corridor boxes.
    """
    if isinstance(contract, dict):
        spec = contract.get("cases", contract)
        if isinstance(spec, dict):
            if region is None:  # every region's cases
                spec = [c for sub in spec.values() for c in sub]
            else:  # a region without cases is not checked against another's
                spec = spec.get(region, [])
        contract = spec

    if not contract:
        return []

    cat = _catalog()
    unknown = [c for c in contract if not isinstance(c, dict) and c not in cat]
    if unknown:
        raise ValueError(f"Unknown validation case(s): {', '.join(unknown)}")
    return [c if isinstance(c, dict) else cat[c] for c in contract]


def validate_network(
    network: Any,
    cases: list[dict[str, Any]],
    *,
    max_snap_km: float = 50.0,
    silent: bool = True,
) -> ValidationResult:
    """Validate a GeoGraph against declarative acceptance cases.

    Routes every test case through the compiled network and verifies:
    1. Snapping distance: Both origin and destination must snap to a network
       node within `max_snap_km` (or the case's custom `max_snap_km`).
    2. Reachability: A valid shortest path must connect the endpoints.
    3. Distance tolerance: Measured length must be within `tolerance` of
       `expected_km`.
    4. Corridor constraints: If `enters_box` is defined, the path must pass
       through the designated geographic bounding box. If `avoids_box` is
       defined, the path must not enter the box.

    Parameters:
        network (GeoGraph): Instantiated GeoGraph network to validate.
        cases (list[dict[str, Any]]): List of validation case dictionaries.
        max_snap_km (float): Maximum allowable snapping distance from case
            coordinates to network nodes in kilometres. Defaults to 50.0 km.
        silent (bool): If True, suppresses log warnings on individual case
            failures. Defaults to True.

    Returns:
        ValidationResult: Detailed outcome detailing passed, failed, and
            measured metrics for each evaluated case.
    """
    result = ValidationResult(total=len(cases))

    for case in cases:
        cid = case.get("id", "unnamed")
        orig = _to_lat_lon(case["origin"])
        dest = _to_lat_lon(case["destination"])
        allowed_snap = case.get("max_snap_km", max_snap_km)

        try:
            c_orig = network.snap_index.closest_idx(point=list(orig))
            c_dest = network.snap_index.closest_idx(point=list(dest))
            snap_km = max(
                haversine(orig, network.nodes[c_orig]),
                haversine(dest, network.nodes[c_dest]),
            )
        # Whatever a case raises is recorded as its failure, and the next cases run
        except Exception as err:  # noqa: BLE001
            result.failed += 1
            result.failures.append(
                {"id": cid, "error": f"Snapping failed: {err}"}
            )
            continue

        if snap_km > allowed_snap:
            result.failed += 1
            result.failures.append(
                {
                    "id": cid,
                    "error": f"Snapping {snap_km:.1f} km exceeds {allowed_snap} km",
                }
            )
            continue

        need_path = "enters_box" in case or "avoids_box" in case
        try:
            route = network.get_shortest_path(
                {"latitude": orig[0], "longitude": orig[1]},
                {"latitude": dest[0], "longitude": dest[1]},
                length_only=not need_path,
                silent=True,
            )
            km = float(route["length"])
        except Exception as err:  # noqa: BLE001 (recorded, as above)
            result.failed += 1
            result.failures.append(
                {"id": cid, "error": f"Routing failed: {err}"}
            )
            continue

        errors = []
        if "expected_km" in case:
            exp = case["expected_km"]
            tol = case.get("tolerance", 0.05)
            if abs(km - exp) / exp > tol:
                errors.append(
                    f"{km:.1f} km deviates by {abs(km - exp) / exp:.1%} from {exp:.1f} km"
                )

        if need_path:
            pts = _sampled_points(route.get("coordinate_path", []))
            for key, should_enter in (
                ("enters_box", True),
                ("avoids_box", False),
            ):
                if key in case:
                    s, w, n, e = case[key]
                    entered = any(
                        s <= p[0] <= n and w <= p[1] <= e for p in pts
                    )
                    if entered != should_enter:
                        errors.append(
                            f"Box check {key} failed (entered={entered})"
                        )

        if errors:
            result.failed += 1
            result.failures.append({"id": cid, "errors": errors})
            if not silent:
                logger.warning("Case %s FAILED: %s", cid, "; ".join(errors))
        else:
            result.passed += 1

    return result
