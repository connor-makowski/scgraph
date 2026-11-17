"""Join hubs to the networks of several modes.

A hub is a place where goods change mode: a port, an airport or a rail terminal. Each hub
becomes one node. It joins the network of each mode it serves by one connector, an arc
in each direction:

- road or rail: a straight line to a node of that network, at most CONNECTOR_KM away.
  The line crosses less than WATER_KM of water (ROADSTEAD_WATER_KM for an open
  roadstead). Among these nodes, the hub takes the nearest one of the largest
  component, so that it does not join a road cut off from the network. The arc weighs
  CIRCUITY times the line, since a real road bends.
- sea: the shortest path over water to a sea node, at most CONNECTOR_KM["sea"] long, on
  the cells of a `LandMask`. The arc weighs the length of that path.

A port serves road and sea, and rail when its table says so. An airport serves road,
and its flights count as its second mode: two airports with regular flights between
them are joined by an arc in each direction, with the great-circle length. A rail
terminal serves road and rail.

A hub that reaches fewer than two modes stays out: a port without a road would join the
sea to nothing. Two modes never share a node, so a route changes mode only at a hub.

Example: the port of Arhus (World Port Index 30260, served by rail) lies 0.8 km from a
rail node and 4.1 km from a road node, and the water path to the nearest sea node is
1.0 km long. Its node gets three connectors, of 0.9, 4.9 and 1.0 km, each in both
directions.

The hubs come from small tables kept with scgraph (`TABLES`, in `scgraph/pipelines/data/`),
each made by `utils/build_hub_tables.py` from its source. A pipeline may name its own
table instead: a source whose URL starts with http is downloaded.
"""

import csv
import math
import os
import shutil
from array import array
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from scgraph.pipelines.steps.stage3_assembly.assembly import (
    NearNodes,
    PieceArrays,
    build_graph_from_pieces,
    strongly_connected_components,
)
from scgraph.utils import haversine

if TYPE_CHECKING:
    from scgraph.geograph import GeoGraph
    from scgraph.pipelines.steps.stage2_intermodal.landmask import LandMask

CONNECTOR_KM = {"road": 20, "rail": 10, "sea": 2500}  # longest connector
# Water a land connector may cross: 3 km, 10 km for an open roadstead
WATER_KM, ROADSTEAD_WATER_KM = 3, 10
CIRCUITY = 1.2  # of a straight land connector
DATA = Path(__file__).parents[2] / "data"


def copy_table(url: str, filename: str | os.PathLike) -> None:
    """The `download` of a hub table: copy the table kept with scgraph named by the last
    part of `url`, or download `url` if it starts with http."""
    if url.startswith(("http://", "https://")):
        from scgraph.pipelines import download_file

        download_file(url, filename)
    else:
        shutil.copyfile(DATA / Path(url).name, filename)


def _table(
    name: str, credit: str, license: str, license_url: str, version: str
):
    return {
        "url": f"scgraph/pipelines/data/{name}.csv",
        "download": copy_table,
        "credit": credit,
        "license": license,
        "license_url": license_url,
        "version": version,
    }


# The sources of the hub tables, as a pipeline lists them in its SOURCES
TABLES = {
    "ports": _table(
        "ports",
        "National Geospatial-Intelligence Agency, World Port Index (Pub. 150)",
        "NOASSERTION",
        "https://msi.nga.mil/Publications/WPI",
        "UpdatedPub150.csv, SHA-256 315644f1e7796629",
    ),
    "airports": _table(
        "airports",
        "OurAirports",
        "LicenseRef-public-domain",
        "https://ourairports.com/data/",
        "airports.csv at commit 1cdbf9cbed1e47bed8f115ec173b91aeb999e44f",
    ),
    "flights": _table(
        "flights",
        "The OpenSky Network, flight list (Strohmeier et al., Earth Syst. Sci. "
        "Data 13, 357-366, 2021); US Bureau of Transportation Statistics, "
        "T-100 Segment; Eurostat, air transport routes (avia_par, avia_gor)",
        "CC-BY-4.0",
        "https://zenodo.org/records/5815448",
        "flights of 2021: OpenSky v21.12; T-100 and Eurostat read on 2026-11-17",
    ),
    "rail_terminals": _table(
        "rail_terminals",
        "Wikidata",
        "CC0-1.0",
        "https://www.wikidata.org/wiki/Wikidata:Licensing",
        "query of 2026-11-16",
    ),
}


class Hub(NamedTuple):
    """A hub: its `kind` (port, airport or rail_terminal), its `id` in its source, its
    `point` [latitude, longitude], the `modes` it serves and whether it is an open
    roadstead (a port without shelter, whose road may be farther across water).
    """

    kind: str
    id: int
    point: list[float]
    modes: tuple[str, ...]
    open_roadstead: bool = False


def _rows(filename: str | os.PathLike) -> Iterator[dict]:
    with open(filename, newline="", encoding="utf-8") as file:
        yield from csv.DictReader(file)


def _point(row: dict) -> list[float]:
    return [float(row["latitude"]), float(row["longitude"])]


def read_ports(filename: str | os.PathLike) -> list[Hub]:
    """The ports of a ports table; a port served by rail also joins the rail network."""
    return [
        Hub(
            "port",
            int(row["id"]),
            _point(row),
            ("road", "sea", "rail") if row["rail"] == "1" else ("road", "sea"),
            row["harbor_type"] == "Open Roadstead",
        )
        for row in _rows(filename)
    ]


def read_airports(filename: str | os.PathLike) -> list[Hub]:
    """The airports of an airports table; an airport joins the road network."""
    return [
        Hub("airport", int(row["id"]), _point(row), ("road",))
        for row in _rows(filename)
    ]


def read_rail_terminals(filename: str | os.PathLike) -> list[Hub]:
    """The terminals of a rail terminals table; a terminal joins the road and rail
    networks."""
    return [
        Hub("rail_terminal", int(row["id"]), _point(row), ("road", "rail"))
        for row in _rows(filename)
    ]


def read_flights(filename: str | os.PathLike) -> list[tuple[int, int]]:
    """The two airport ids of each pair of airports with regular flights."""
    return [
        (int(row["airport_a"]), int(row["airport_b"]))
        for row in _rows(filename)
    ]


class _Layer:
    """The network of one mode, from the network file's arrays
    (`assembly.build_graph_from_pieces`'s layout) or from a GeoGraph: its node points
    in 1e-7 degree, its node ids and its arcs."""

    def __init__(self, network: "dict | GeoGraph"):
        if isinstance(network, dict):
            points = memoryview(network["node_points"])
            self.latitudes, self.longitudes = points[0::2], points[1::2]
            self.ids = array("q", network["node_ids"])
            self.offsets, self.heads = network["offsets"], network["heads"]
        else:
            self.latitudes = array(
                "i", (round(n[0] * 1e7) for n in network.nodes)
            )
            self.longitudes = array(
                "i", (round(n[1] * 1e7) for n in network.nodes)
            )
            self.ids = array("q", network.node_ids)
            graph = network.graph_object.graph
            self.offsets = array("q", [0])
            self.heads = array("i")
            for row in graph:
                self.heads.extend(row)
                self.offsets.append(len(self.heads))
        self.network = network

    def __len__(self):
        return len(self.ids)

    def release(self) -> None:
        """Drop the arrays of the network, but its node ids; empty the arrays of a
        network given as arrays."""
        self.latitudes = self.longitudes = self.offsets = self.heads = None
        if isinstance(self.network, dict):
            self.network.clear()
        self.network = None

    def point(self, u: int) -> list[float]:
        return [self.latitudes[u] * 1e-7, self.longitudes[u] * 1e-7]

    def arcs(self) -> Iterator[tuple[int, int, float, list]]:
        """(origin, destination, km, shape) of each arc, the shape's points in degrees."""
        network = self.network
        if isinstance(network, dict):
            weights = network["weights"]
            starts, line = network["shape_offsets"], network["shape_points"]
            for u in range(len(self)):
                for a in range(self.offsets[u], self.offsets[u + 1]):
                    points = line[2 * starts[a] : 2 * starts[a + 1]]
                    shape = [
                        [x * 1e-7, y * 1e-7]
                        for x, y in zip(points[::2], points[1::2])
                    ]
                    yield u, self.heads[a], weights[a], shape
        else:
            shapes = network.intermediate_nodes or [{}] * len(self)
            for u, row in enumerate(network.graph_object.graph):
                for v, km in row.items():
                    yield u, v, km, shapes[u].get(v, [])


def join(
    layers: "dict[str, dict | GeoGraph]",
    hubs: Iterable[Hub],
    land_mask: "LandMask",
    modes: Sequence[str],
    flights: Iterable[tuple[int, int]] = (),
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, dict[str, int]]:
    """Join the networks of several modes at their hubs.

    A hub becomes a node when it reaches at least two modes. A flight is kept when
    both its airports have a connector.

    Args:
        layers: The network of each mode: the network file's arrays, or a GeoGraph.
            The arrays are emptied.
        hubs: The hubs to join.
        land_mask: Land and water around the hubs. Its raster is released.
        modes: The names of the rows of the modes table: every layer and every kind
            of hub.
        flights: The two airport ids of each pair with regular flights.
        work_dir: A folder that keeps the arcs in files. None keeps them in memory.

    Returns:
        The joined network as the network file's arrays, and the number of hubs
        joined of each kind. `node_modes` gives the row of each node in `modes`.
        `node_ids` keeps each layer's ids and gives each hub its id in its table.
    """
    layers = {mode: _Layer(network) for mode, network in layers.items()}
    first, n = {}, 0  # the index of each layer's first node
    for mode, layer in layers.items():
        first[mode], n = n, n + len(layer)
    points = []  # of the hubs, in degrees, after the layers' nodes
    pieces = PieceArrays(tolerance_meters=None, work_dir=work_dir)

    def at(u):
        for mode, layer in layers.items():
            if u < first[mode] + len(layer):
                return layer.point(u - first[mode])
        return points[u - n]

    def add(u, v, km, shape):
        pieces.append(u, v, km, 1, [at(u), at(v)], shape)

    # 1. The arcs of each layer, on node indices that follow each other
    for mode, layer in layers.items():
        for u, v, km, shape in layer.arcs():
            add(first[mode] + u, first[mode] + v, km, shape)
    # 2. The connectors of each hub, and its node if it reaches two modes
    connect = {
        mode: _land_connector(layer, land_mask, CONNECTOR_KM[mode])
        for mode, layer in layers.items()
        if mode != "sea"
    }
    if "sea" in layers:
        connect["sea"] = _sea_connector(layers["sea"], land_mask)
    connectors = (
        []
    )  # each hub, with the connectors it finds: mode -> (node, km, shape)
    for hub in hubs:
        arcs = {
            mode: connect[mode](hub) for mode in hub.modes if mode in connect
        }
        connectors.append(
            (hub, {mode: arc for mode, arc in arcs.items() if arc})
        )
    # A flight counts when both its airports have a connector
    reached = {
        hub.id for hub, arcs in connectors if hub.kind == "airport" and arcs
    }
    flights = [flight for flight in flights if set(flight) <= reached]
    flying = {a for flight in flights for a in flight}
    kinds, ids, airport = [], array("q"), {}
    for hub, arcs in connectors:
        flies = hub.kind == "airport" and hub.id in flying
        if len(arcs) + flies < 2:  # the flights are a mode of an airport
            continue
        h = n + len(points)
        points.append(hub.point)
        kinds.append(hub.kind)
        ids.append(hub.id)
        if hub.kind == "airport":
            airport[hub.id] = h
        for mode, (u, km, shape) in arcs.items():
            u += first[mode]
            add(h, u, km, shape)
            add(u, h, km, shape[::-1])
    # 3. The flights, airport to airport
    for one, other in flights:
        a, b = airport[one], airport[other]
        km = haversine(at(a), at(b))
        add(a, b, km, [])
        add(b, a, km, [])
    # 4. The graph, with the mode and the source id of each node
    layer_ids = [layer.ids for layer in layers.values()]
    layer_modes = [modes.index(mode) for mode in layers]
    sizes = [len(layer) for layer in layers.values()]
    for layer in layers.values():
        layer.release()  # freed before the joined graph is built
    land_mask.bits = None
    del connect
    joined = build_graph_from_pieces(pieces)
    all_ids = array("q")
    for layer_id in layer_ids:
        all_ids += layer_id
    all_ids += ids
    node_modes = bytearray()
    for row, size in zip(layer_modes, sizes):
        node_modes += bytes([row]) * size
    node_modes += bytes(modes.index(kind) for kind in kinds)
    # build_graph_from_pieces renumbers the nodes; its node_ids are the numbers the
    # nodes had here
    old = joined["node_ids"]
    joined["node_modes"] = array("B", (node_modes[u] for u in old))
    joined["node_ids"] = array("q", (all_ids[u] for u in old))
    return joined, {kind: kinds.count(kind) for kind in dict.fromkeys(kinds)}


def _land_connector(layer: _Layer, land_mask: "LandMask", max_km: float):
    """`connect(hub)` -> (node of `layer`, km, shape) or None, by the rule of the module
    docstring for road and rail."""
    labels, sizes = strongly_connected_components(layer.offsets, layer.heads)
    components = array("i", (sizes[label] for label in labels))
    near = NearNodes(layer.latitudes, layer.longitudes, scale=1e-7)

    def connect(hub):
        water_km = ROADSTEAD_WATER_KM if hub.open_roadstead else WATER_KM
        # Largest component first, then nearest
        for _, km, u in sorted(
            (-components[u], km, u)
            for km, u in near.find_within(hub.point, max_km)
        ):
            if _water_km(land_mask, hub.point, layer.point(u), km) < water_km:
                return u, CIRCUITY * km, []
        return None

    return connect


def _sea_connector(layer: _Layer, land_mask: "LandMask"):
    """`connect(hub)` -> (sea node, km, path) or None: the shortest path over water
    from the hub to the cell of a sea node, then straight to that node."""
    cells = {}  # mask cell -> its first sea node
    for s in range(len(layer)):
        cells.setdefault(land_mask.get_cell(*layer.point(s)), s)
    cells.pop(None, None)
    targets = array("q", sorted(cells))

    def connect(hub):
        found = land_mask.find_water_path(
            hub.point, targets, CONNECTOR_KM["sea"]
        )
        if not found:
            return None
        km, path = found
        s = cells[land_mask.get_cell(*path[-1])]
        return s, km + haversine(path[-1], layer.point(s)), path

    return connect


def _water_km(land_mask, point_a, point_b, distance_km):
    """km of water along the straight line point_a-point_b (`distance_km` long),
    sampled every 0.25 km."""
    n = max(1, math.ceil(distance_km / 0.25))
    water = sum(
        not land_mask.is_on_land(
            *(x + (j + 0.5) / n * (y - x) for x, y in zip(point_a, point_b))
        )
        for j in range(n)
    )
    return distance_km * water / n
