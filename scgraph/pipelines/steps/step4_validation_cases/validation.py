"""
This module holds the rules that check a built network against validation cases.
The docstring of the package `step4_validation_cases` describes the kinds of
cases and their rules.
"""

import csv
import logging
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import groupby
from pathlib import Path

from scgraph import GeoGraph, PathNotFoundError
from scgraph.utils import haversine

logger = logging.getLogger(__name__)

__all__ = ["ValidationResult", "load_validation_cases", "validate_network"]

CASES_DIR = Path(__file__).parent / "cases"


@dataclass
class ValidationResult:
    """The result of `validate_network`: counts, and one record for each failed case."""

    passed: int = 0
    failed: int = 0
    total: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """True when at least one case was checked and no case failed."""
        return self.failed == 0 and self.total > 0

    def summary(self) -> str:
        """Return one line for the log: PASSED or FAILED, with the counts."""
        status = "PASSED" if self.is_success else "FAILED"
        return f"{status}: {self.passed}/{self.total} cases OK (failed: {self.failed})"


# ----------------------------------------------------------------------------
# Measures on a network
# ----------------------------------------------------------------------------


def _find_path(
    network, origin, destination, with_path=False, from_tree=False
) -> dict | None:
    """Return the shortest route between two (latitude, longitude) points, or None
    when no route joins them. Each point is snapped to its closest node. The
    length includes the straight line from each point to its node.
    With `from_tree`, the shortest path tree of the origin is computed once and
    kept. The next routes from the same origin are read from that tree."""
    options = {"algorithm_fn": "cached_shortest_path"} if from_tree else {}
    try:
        return network.get_shortest_path(
            {"latitude": origin[0], "longitude": origin[1]},
            {"latitude": destination[0], "longitude": destination[1]},
            length_only=not with_path,
            **options,
        )
    except PathNotFoundError:
        return None


def _find_path_km(network, origin, destination, **options) -> float | None:
    route = _find_path(network, origin, destination, **options)
    return None if route is None else route["length"]


def _find_closest_node(network, point, mode=None) -> tuple:
    """Return the distance in km from `point` to the closest node, and the coordinates
    of that node. The node mode of a node is the kind of place where the node is, such
    as `road` or `port`. With `mode`, only the nodes of that node mode are candidates.
    When the network does not have that node mode, all its nodes are candidates. This is
    the case of a published network and of a file with a single node mode."""
    node_mode_names = [m["name"] for m in network.node_modes or []]
    if mode is None or mode not in node_mode_names:
        node = network.nodes[network.snap_index.closest_idx(point=list(point))]
        return haversine(point, node), tuple(node)
    wanted = node_mode_names.index(mode)
    return min(
        (haversine(point, node), tuple(node))
        for node, node_mode_id in zip(network.nodes, network.node_mode_ids)
        if node_mode_id == wanted
    )


# ----------------------------------------------------------------------------
# The rules. Each rule returns None when the case passes, or a message that
# says why the case fails.
# ----------------------------------------------------------------------------


def _check_road_distance(network, case) -> str | None:
    # The reference is a driving distance in each direction. A much longer route
    # shows a missing road. Two very different directions show a one-way error.
    there = _find_path_km(network, case["origin"], case["destination"])
    back = _find_path_km(network, case["destination"], case["origin"])
    if there is None or back is None:
        return "no road route"
    references = (
        case["reference"],
        case.get("reference_back") or case["reference"],
    )
    tolerance = case.get("tolerance") or 0.10
    for km, reference in zip((there, back), references):
        if abs(km / float(reference) - 1) > tolerance:
            return f"{km:.0f} km against {float(reference):.0f} km"
    if abs(there - back) > 0.05 * (there + back) / 2:
        return f"the two directions differ: {there:.0f} and {back:.0f} km"


def _check_crossing(network, case) -> str | None:
    # Each end must be close to a road. Without this check, a network with no
    # road on an island would still pass: the route would start from the closest
    # road, on the other side of the water.
    for end in ("origin", "destination"):
        km, _ = _find_closest_node(network, case[end])
        if km > 5.0:
            return f"the {end} is {km:.1f} km from a road"
    if _find_path_km(network, case["origin"], case["destination"]) is None:
        return f"no road route ({case['reference']})"


def _check_coverage(network, case) -> str | None:
    # The origin is a large city. The destination is the main city of the same
    # landmass. A route between them shows that the city is on the main road
    # network, and not on a separate piece of it.
    km, _ = _find_closest_node(network, case["origin"])
    if km > 5.0:
        return f"the closest road is {km:.1f} km away"
    # All the cities of a landmass have the same main city. Its shortest path
    # tree is computed once and serves them all. The tree of the previous landmass is
    # dropped first: on a world network, one tree takes about 150 MB.
    main_city = case["destination"]
    if getattr(network, "main_city_of_the_kept_tree", None) != main_city:
        network.graph_object.reset_cache()
        network.main_city_of_the_kept_tree = main_city
    if (
        _find_path_km(network, main_city, case["origin"], from_tree=True)
        is None
    ):
        return "no road route to the main city of the landmass"


def _check_rail_corridor(network, case) -> str | None:
    # A missing piece of track makes the route longer. A shorter route follows another line
    # (a high-speed line, a shortcut), so the lower limit is wider.
    (origin_km, origin), (destination_km, destination) = (
        _find_closest_node(network, case[end])
        for end in ("origin", "destination")
    )
    if max(origin_km, destination_km) > 10.0:
        return f"the track is {max(origin_km, destination_km):.1f} km away"
    km = _find_path_km(network, origin, destination)
    if km is None:
        return "no rail route"
    if not -0.20 <= km / float(case["reference"]) - 1 <= 0.10:
        return f"{km:.0f} km against {case['reference']} km"


def _check_sea_distance(network, case) -> str | None:
    # The route starts and ends at the port node of each port. When a port has no
    # port node within 5 km, the route uses the closest sea node instead. This
    # rule checks sea distances only. The river port rule reports a port that is
    # not joined to the sea.
    ends = []
    for end in ("origin", "destination"):
        km, node = _find_closest_node(network, case[end], "port")
        if km > 5.0:
            _, node = _find_closest_node(network, case[end], "sea")
        ends.append(node)
    km = _find_path_km(network, *ends)
    if km is None:
        return "no water route"
    # On a short route, the approach to each port is a large part of the
    # distance. The rule therefore also accepts a difference of 30 km.
    reference = float(case["reference"])
    if abs(km / reference - 1) > 0.10 and abs(km - reference) > 30.0:
        return f"{km:.0f} km against {reference:.0f} km"


def _check_passage(network, case) -> str | None:
    # The case gives a box around the passage. The route is tested every 5 km,
    # because one long straight edge can cross the box between two nodes.
    route = _find_path(
        network, case["origin"], case["destination"], with_path=True
    )
    if route is None:
        return "no sea route"
    south, west, north, east = (
        float(case[f"box_{side}"])
        for side in ("south", "west", "north", "east")
    )
    enters = False
    points = route["coordinate_path"]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        # Two points, one on each side of longitude 180, are close to each other
        lon2 += 360 if lon1 - lon2 > 180 else -360 if lon2 - lon1 > 180 else 0
        steps = max(1, math.ceil(haversine((lat1, lon1), (lat2, lon2)) / 5.0))
        for step in range(steps + 1):
            lat = lat1 + (lat2 - lat1) * step / steps
            lon = (lon1 + (lon2 - lon1) * step / steps + 180) % 360 - 180
            if south <= lat <= north and west <= lon <= east:
                enters = True
    measured = "enters" if enters else "avoids"
    if measured != case["reference"]:
        return f"the route {measured} {case['passage']}"


def _check_river_port(network, case) -> str | None:
    # The origin is the port. The destination is a point at sea, at the mouth of
    # the river. A water route much longer than the straight line makes a detour.
    join_km, port = _find_closest_node(network, case["origin"], "port")
    if join_km > 5.0:
        return f"the closest port node is {join_km:.1f} km away"
    _, sea = _find_closest_node(network, case["destination"], "sea")
    km = _find_path_km(network, port, sea)
    if km is None:
        return "no water route to the sea"
    if km > 1.8 * haversine(port, sea):
        return f"{km / haversine(port, sea):.2f} times the straight line"


def _check_route_length(network, case) -> str | None:
    km = _find_path_km(network, case["origin"], case["destination"])
    if km is None:
        return "no route"
    if abs(km / float(case["reference"]) - 1) > (case.get("tolerance") or 0.05):
        return f"{km:.1f} km against {case['reference']} km"


def _check_hub(network, case) -> str | None:
    # A hub that the pipeline left out, or a connector that it could not find, shows as
    # a route that leaves the hub by another network: two networks meet only at hubs, so
    # the first edge of the route from a hub to the closest node of a network is the
    # hub's connector to that network, when it has one.
    km, hub = _find_closest_node(network, case["origin"], case["hub_kind"])
    if km > 5.0:
        return f"the closest {case['hub_kind']} is {km:.1f} km away"
    names = [mode["name"] for mode in network.node_modes]
    for mode in case["reference"].split():
        if mode == "air":
            first_mode = "airport"
            km, end = _find_closest_node(
                network, case["destination"], "airport"
            )
            if km > 5.0:
                return f"the airport of the flight is {km:.1f} km away"
        else:
            first_mode = mode
            _, end = _find_closest_node(network, hub, mode)
        try:
            path = network.get_shortest_path(
                {"latitude": hub[0], "longitude": hub[1]},
                {"latitude": end[0], "longitude": end[1]},
                output_path=True,
            )["path"]
        except PathNotFoundError:
            return f"no route to the {mode} network"
        if len(path) < 2 or names[network.node_mode_ids[path[1]]] != first_mode:
            return f"no connector to the {mode} network"
        # A direct flight is the shortest route between two airports: a stop
        # or a road between them is longer
        if mode == "air" and len(path) != 2:
            return "no direct flight to the airport of the case"


# For each kind: the node modes that its routes may use, and its rule. An empty tuple of
# node modes means all the node modes of the network. The points of a case snap to the
# nodes of these node modes (see `validate_network`).
RULES = {
    "road_distances": (("road",), _check_road_distance),
    "crossings": (("road",), _check_crossing),
    "coverage": (("road",), _check_coverage),
    "rail_corridors": (("rail",), _check_rail_corridor),
    "sea_distances": (("port", "sea"), _check_sea_distance),
    "passages": (("sea",), _check_passage),
    "river_ports": (("port", "sea"), _check_river_port),
    "route_lengths": ((), _check_route_length),
    "hubs": ((), _check_hub),
}
# The source of the coverage cases places a few cities in the sea, and a few
# cities are on islands without a road link. Coverage passes when at most this
# share of the cities fails.
MAX_SHARE_OF_FAILED_CITIES = 0.01


# ----------------------------------------------------------------------------
# Cases, and the validation of a network
# ----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _read_all_cases() -> dict[str, dict]:
    """Return every case of `cases/` by its id. A row is disabled when its id
    starts with `#`. Two cases with the same id raise a ValueError."""
    cases = {}
    for path in sorted(CASES_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row["id"].startswith("#"):
                    continue
                if row["id"] in cases:
                    raise ValueError(
                        f"Validation case '{row['id']}' is defined twice; "
                        f"the second time in {path.name}"
                    )
                cases[row["id"]] = {
                    **row,
                    "kind": path.stem,
                    "origin": (
                        float(row["origin_lat"]),
                        float(row["origin_lon"]),
                    ),
                    "destination": (
                        float(row["destination_lat"]),
                        float(row["destination_lon"]),
                    ),
                    "tolerance": float(row["tolerance"] or 0) or None,
                    "reference_back": row.get("reference_back"),
                }
    return cases


def load_validation_cases(
    validation: dict, region: str | None = None
) -> list[dict]:
    """Return the cases that the `VALIDATION` of a pipeline lists (the module
    docstring describes the entries). For a regional pipeline, return the cases of
    `region`, and no case when the region has none. Without `region`, return the
    cases of every region.

    Raises:
        ValueError: An entry is neither the id of a case nor the name of a kind.
    """
    entries = validation["cases"]
    if isinstance(entries, dict):  # region -> entries
        entries = (
            entries.get(region, [])
            if region
            else [
                entry for of_region in entries.values() for entry in of_region
            ]
        )
    all_cases = _read_all_cases()
    cases = []
    for entry in entries:
        if isinstance(entry, dict):
            cases.append(entry)
        elif entry in RULES:
            cases += [
                case for case in all_cases.values() if case["kind"] == entry
            ]
        elif entry in all_cases:
            cases.append(all_cases[entry])
        else:
            raise ValueError(f"Unknown validation case or kind: {entry}")
    return cases


def _load_on_node_modes(network, node_modes: tuple) -> GeoGraph:
    """Load the network file `network` with the nodes and edges of `node_modes` only.
    A GeoGraph is returned unchanged. The caller must then give only cases of the
    node modes of that GeoGraph."""
    if isinstance(network, GeoGraph):
        return network
    file_modes = {
        m["name"]
        for m in GeoGraph.get_scgraph_info(network).get("node_modes", [])
    }
    restrict = bool(node_modes) and not file_modes <= set(node_modes)
    return GeoGraph.load_from_scgraph(
        str(network), node_modes=sorted(node_modes) if restrict else None
    )


def validate_network(
    network: GeoGraph | str | os.PathLike, cases: list[dict]
) -> ValidationResult:
    """Check `network` against `cases`. Each case is checked by the rule of its
    kind. A case that fails is logged and recorded in the result. The coverage
    cases are the exception: when at most `MAX_SHARE_OF_FAILED_CITIES` of them
    fail, they all count as passed.

    The points of a case snap to the nodes of the node modes of its kind: a road node
    for a road distance, any node for a hub. The node modes that the network names for
    its query points (`default_node_addition_modes`) do not count: a hub case starts at
    the node of its hub, which is not a road node.

    Args:
        network: The path of a network file, or a loaded GeoGraph. A file is read
            again for each set of node modes, one at a time, to limit the memory used.
            The coverage rule resets the cache of trees of a loaded GeoGraph. The
            function sets `default_node_addition_modes` of a loaded GeoGraph for
            its queries, and sets it back before it returns.
        cases: The cases, as `load_validation_cases` returns them.

    Returns:
        A `ValidationResult`: the number of cases that passed and failed, and one
        record (`id`, `kind`, `error`) for each case that failed.
    """
    result = ValidationResult(total=len(cases))

    def modes_of(case):
        return RULES[case["kind"]][0]

    # The cities of one landmass follow each other: see the coverage rule
    cases = sorted(cases, key=lambda case: case.get("landmass") or "")
    for node_modes, cases_on_modes in groupby(
        sorted(cases, key=modes_of), key=modes_of
    ):
        loaded = None  # the previous network is released before the next load
        loaded = _load_on_node_modes(network, node_modes)
        failures = []
        # The queries of the rules snap to the nodes of the node modes of the kind. No
        # list of node modes means every node.
        default_node_addition_modes = loaded.default_node_addition_modes
        loaded.default_node_addition_modes = list(node_modes) or None
        try:
            for case in cases_on_modes:
                reason = RULES[case["kind"]][1](loaded, case)
                if reason:
                    failures.append(
                        {
                            "id": case["id"],
                            "kind": case["kind"],
                            "error": reason,
                        }
                    )
        finally:
            loaded.default_node_addition_modes = default_node_addition_modes
        # Coverage is judged on all its cities together
        cities = sum(case["kind"] == "coverage" for case in cases)
        cities_failed = sum(
            failure["kind"] == "coverage" for failure in failures
        )
        if cities_failed <= MAX_SHARE_OF_FAILED_CITIES * cities:
            failures = [f for f in failures if f["kind"] != "coverage"]
        for failure in failures:
            logger.warning("Case %(id)s (%(kind)s) fails: %(error)s", failure)
        result.failures += failures
    result.failed = len(result.failures)
    result.passed = result.total - result.failed
    return result
