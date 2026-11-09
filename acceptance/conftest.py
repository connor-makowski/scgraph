"""
Acceptance tests of a network file: does it give the distances of the real world?

    pytest acceptance --network FILE|NAME [--modes MODE] [--results FILE]

`--network` is a network file (.scgraph), or the name of a network in the scgraph cache,
loaded with `GeoGraph.load_geograph` or built with `GeoGraph.build_geograph` beforehand:
the tests never download. Each test module routes on its `MODES` only, and is skipped
when the file lacks one; a file without node modes (a published conversion or a
single-mode file) holds the one mode that `--modes` names. Modules on the same modes run
in a row on one loaded network, and one network is loaded at a time. Each case appends
its measured values to `--results` (JSON lines), whether it passes or fails, so that
releases can be compared without running again.
"""

import csv
import gc
import json
from pathlib import Path

import pytest
from scgraph import GeoGraph
from scgraph.utils import haversine

LOADED = (
    {}
)  # modes -> the network on them: one at a time (memory at world scale)


def pytest_addoption(parser):
    group = parser.getgroup("acceptance")
    group.addoption("--network", help="a .scgraph file or a cached network")
    group.addoption("--modes", help="the mode of a file without node modes")
    group.addoption("--results", help="JSON lines file of measured values")


def pytest_collection_modifyitems(items):
    items.sort(key=lambda item: sorted(item.module.MODES))  # stable


def cases(kind):
    """The rows of cases/<kind>.csv but those whose id starts with '#', with
    `origin` and `destination` as (lat, lon) and `tolerance` a float or None."""
    path = Path(__file__).with_name("cases") / f"{kind}.csv"
    with open(path, newline="", encoding="utf-8") as file:
        rows = [
            row for row in csv.DictReader(file) if not row["id"].startswith("#")
        ]
    for row in rows:
        for end in ("origin", "destination"):
            row[end] = float(row[f"{end}_lat"]), float(row[f"{end}_lon"])
        row["tolerance"] = float(row["tolerance"]) if row["tolerance"] else None
    return rows


def route_km(network, origin, destination, **options):
    """The length of the shortest route between two (lat, lon) points, each snapped to
    its nearest node, or None when no route joins them; `options` go to
    `get_shortest_path`."""
    try:
        return network.get_shortest_path(
            {"latitude": origin[0], "longitude": origin[1]},
            {"latitude": destination[0], "longitude": destination[1]},
            length_only=True,
            silent=True,
            **options,
        )["length"]
    # Not connected: the C++ backend raises a RuntimeError, the Python one a bare
    # Exception, so nothing narrower catches both
    except Exception:
        return None


def nearest_km(network, point, mode=None):
    """(km, (lat, lon)) of the node nearest to a (lat, lon) point: the node scgraph
    snaps it to, or the nearest node of `mode`."""
    if mode is None:
        node = network.nodes[network.snap_index.closest_idx(point=list(point))]
        return haversine(point, node), tuple(node)
    rows = [row for row, m in enumerate(network.modes) if m["name"] == mode]
    return min(
        (haversine(point, node), tuple(node))
        for node, row in zip(network.nodes, network.node_modes)
        if row in rows
    )


@pytest.fixture(scope="session")
def network_file(pytestconfig):
    """The path of `--network` and its header (`GeoGraph.scgraph_info`)."""
    path = pytestconfig.getoption("--network")
    if not path:
        pytest.skip("no --network given")
    if not path.endswith(".scgraph"):
        cached = [
            entry["file"]
            for entry in GeoGraph.get_cache_info()
            if entry["name"] == path and entry["file"].endswith(".scgraph")
        ]
        if len(cached) != 1:
            pytest.exit(
                f"--network {path}: {len(cached)} matches in the cache; give a file"
            )
        path = cached[0]
    if not Path(path).is_file():
        pytest.exit(f"--network {path}: no such file")
    try:
        return path, GeoGraph.get_scgraph_info(path)
    except ValueError as error:  # not a network file, or another format version
        pytest.exit(f"--network {error}")


@pytest.fixture(scope="module")
def network(request, network_file):
    """The network on the test module's MODES."""
    path, info = network_file
    wanted = request.module.MODES
    have = [m["name"] for m in info.get("modes", []) if m["name"]]
    have = have or [request.config.getoption("--modes")]
    missing = [mode for mode in wanted if mode not in have]
    if missing:
        pytest.skip(f"no {' and '.join(missing)} mode in {path}")
    # No other mode in the file: loaded whole, mapped instead of copied
    modes = None if set(have) <= set(wanted) else tuple(sorted(wanted))
    if modes not in LOADED:
        LOADED.clear()
        gc.collect()  # the previous network is freed before the next one loads
        LOADED[modes] = GeoGraph.load_from_scgraph(path, modes=modes)
    return LOADED[modes]


@pytest.fixture
def record(request, network_file):
    """record(case, measured): append a case's measured values (a dict) to --results."""
    results = request.config.getoption("--results")

    def write(case, measured):
        if results:
            line = {
                "test": request.node.nodeid,
                "network": request.config.getoption("--network"),
                "content_sha256": network_file[1]["content_sha256"],
                "case": case["id"],
                **measured,
            }
            with open(results, "a", encoding="utf-8") as file:
                file.write(json.dumps(line) + "\n")

    return write
