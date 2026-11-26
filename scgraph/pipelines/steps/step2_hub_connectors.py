"""Join hubs to the road, rail and sea networks.

A hub is a place where goods change from one kind of transport to another: a port, an
airport or a rail terminal. Each hub becomes one node. It joins each network that it
serves by one connector, an edge in each direction:

- road or rail: a straight line to a node of that network, at most CONNECTOR_KM away.
  The line crosses less than WATER_KM of water (ROADSTEAD_WATER_KM for an open
  roadstead). Among these nodes, the hub takes the closest one of the largest
  component, so that it does not join a road cut off from the network. The edge weighs
  CIRCUITY times the line, since a real road bends.
- sea: the shortest path over water to a sea node, at most CONNECTOR_KM["sea"] long, on
  the cells of a `LandMask`. The edge weighs the length of that path, plus the short
  line from its last cell to the sea node.

A port serves road and sea, and rail when its table says so. An airport serves road.
Its flights count as a second network: two airports with regular flights between them
are joined by an edge in each direction, with the great-circle length. A rail terminal
serves road and rail.

A hub that reaches fewer than two networks stays out: a port without a road would join
the sea to nothing. Two networks never share a node, so a route goes from one network
to another only through a hub.

When the networks have the class of each edge (`edge_class_ids`), the joined network has
it too. A connector then has the class of the network that it reaches, for example
`road_connector`, and a flight has the class `flight`.

Example: the port of Arhus (World Port Index 30260, served by rail) lies 0.76 km from a
rail node and 4.08 km from a road node, and the water path to the closest sea node is
0.99 km long. Its node gets three connectors, each in both directions: 0.91 km to the
railway (1.2 times 0.76), 4.90 km to the road (1.2 times 4.08) and 0.99 km to the sea.

The hubs come from small tables kept with scgraph (`HUB_TABLES`, in `scgraph/pipelines/data/`),
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

from scgraph.pipelines import CLASS_IDS
from scgraph.helpers.near_nodes import NearNodes
from scgraph.helpers.polylines import PieceArrays
from scgraph.network_assembly import (
    build_graph_from_pieces,
    find_strongly_connected_components,
)
from scgraph.utils import haversine

if TYPE_CHECKING:
    from scgraph.pipelines.steps.step2_land_mask import LandMask

# The longest connector to each network, in km: the straight line to a road or rail node,
# and the water path to a sea node
CONNECTOR_KM = {"road": 20, "rail": 10, "sea": 2500}
# The most water that the line of a land connector may cross, in km. An open
# roadstead has no shelter and its ships anchor off the coast, so its limit is higher.
WATER_KM, ROADSTEAD_WATER_KM = 3, 10
# A land connector weighs this many times its straight line, because a real road bends
CIRCUITY = 1.2
DATA = Path(__file__).parents[1] / "data"


def copy_table(url: str, filename: str | os.PathLike) -> None:
    """The `download` of a hub table: copy the table kept with scgraph named by the last
    part of `url`, or download `url` if it starts with http."""
    if url.startswith(("http://", "https://")):
        from scgraph.pipelines import download_file

        download_file(url, filename)
    else:
        shutil.copyfile(DATA / Path(url).name, filename)


def _describe_table(
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
HUB_TABLES = {
    "ports": _describe_table(
        "ports",
        "National Geospatial-Intelligence Agency, World Port Index (Pub. 150)",
        "LicenseRef-US-Government-Work",
        "https://msi.nga.mil/Publications/WPI",
        "UpdatedPub150.csv, SHA-256 315644f1e7796629",
    ),
    "airports": _describe_table(
        "airports",
        "OurAirports",
        "LicenseRef-public-domain",
        "https://ourairports.com/data/",
        "airports.csv at commit 1cdbf9cbed1e47bed8f115ec173b91aeb999e44f",
    ),
    "flights": _describe_table(
        "flights",
        "The OpenSky Network, flight list (Strohmeier et al., Earth Syst. Sci. "
        "Data 13, 357-366, 2021); US Bureau of Transportation Statistics, "
        "T-100 Segment; Eurostat, air transport routes (avia_par, avia_gor)",
        "CC-BY-4.0",
        "https://zenodo.org/records/5815448",
        "flights of 2021: OpenSky v21.12; T-100 and Eurostat read on 2026-11-17",
    ),
    "rail_terminals": _describe_table(
        "rail_terminals",
        "Wikidata",
        "CC0-1.0",
        "https://www.wikidata.org/wiki/Wikidata:Licensing",
        "query of 2026-11-16",
    ),
}


class Hub(NamedTuple):
    """A hub. `node_mode` is `port`, `airport` or `rail_terminal`. `id` is its id in its
    source. `point` is `[latitude, longitude]`. `joined_node_modes` lists the networks
    that it serves. `open_roadstead` is true for a port without shelter, where ships anchor off
    the coast. The road connector of such a port may cross up to ROADSTEAD_WATER_KM of
    water.
    """

    node_mode: str
    id: int
    point: list[float]
    joined_node_modes: tuple[str, ...]
    open_roadstead: bool = False


def _read_rows(filename: str | os.PathLike) -> Iterator[dict]:
    with open(filename, newline="", encoding="utf-8") as file:
        yield from csv.DictReader(file)


def _get_point(row: dict) -> list[float]:
    return [float(row["latitude"]), float(row["longitude"])]


def read_ports(filename: str | os.PathLike) -> list[Hub]:
    """The ports of a ports table; a port served by rail also joins the rail network."""
    return [
        Hub(
            "port",
            int(row["id"]),
            _get_point(row),
            ("road", "sea", "rail") if row["rail"] == "1" else ("road", "sea"),
            row["harbor_type"] == "Open Roadstead",
        )
        for row in _read_rows(filename)
    ]


def read_airports(filename: str | os.PathLike) -> list[Hub]:
    """The airports of an airports table; an airport joins the road network."""
    return [
        Hub("airport", int(row["id"]), _get_point(row), ("road",))
        for row in _read_rows(filename)
    ]


def read_rail_terminals(filename: str | os.PathLike) -> list[Hub]:
    """The terminals of a rail terminals table; a terminal joins the road and rail
    networks."""
    return [
        Hub("rail_terminal", int(row["id"]), _get_point(row), ("road", "rail"))
        for row in _read_rows(filename)
    ]


def read_flights(filename: str | os.PathLike) -> list[tuple[int, int]]:
    """The two airport ids of each pair of airports with regular flights."""
    return [
        (int(row["airport_a"]), int(row["airport_b"]))
        for row in _read_rows(filename)
    ]


class _Network:
    """One network, such as the road network, from the network file's arrays
    (`network_assembly.build_graph_from_pieces`'s layout): its node points in 1e-7 degree, its
    node ids and its edges, each with its class.
    """

    def __init__(self, network: dict):
        points = memoryview(network["node_points"])
        self.latitudes, self.longitudes = points[0::2], points[1::2]
        self.ids = array("q", network["external_node_ids"])
        self.node_first_edge_ids, self.edge_destination_node_ids = (
            network["node_first_edge_ids"],
            network["edge_destination_node_ids"],
        )
        self.network = network

    def __len__(self):
        return len(self.ids)

    def release(self) -> None:
        """Free the arrays of the network, and keep only its node ids. The function
        empties the dict of arrays that the caller gave.
        """
        self.latitudes = self.longitudes = self.node_first_edge_ids = (
            self.edge_destination_node_ids
        ) = None
        self.network.clear()
        self.network = None

    def point(self, u: int) -> list[float]:
        return [self.latitudes[u] * 1e-7, self.longitudes[u] * 1e-7]

    def edges(self) -> Iterator[tuple[int, int, float, list, int | None]]:
        """(origin, destination, km, shape, class id) of each edge. The points of the
        shape are in degrees.
        """
        network = self.network
        weights = network["metric_length"]
        starts, line = (
            network["edge_first_shape_point_ids"],
            network["shape_points"],
        )
        edge_class_ids = network["edge_class_ids"]
        for u in range(len(self)):
            for a in range(
                self.node_first_edge_ids[u], self.node_first_edge_ids[u + 1]
            ):
                points = line[2 * starts[a] : 2 * starts[a + 1]]
                shape = [
                    [x * 1e-7, y * 1e-7]
                    for x, y in zip(points[::2], points[1::2])
                ]
                yield u, self.edge_destination_node_ids[a], weights[
                    a
                ], shape, edge_class_ids[a]


def join_networks_at_hubs(
    layers: dict[str, dict],
    hubs: Iterable[Hub],
    land_mask: "LandMask",
    node_modes: Sequence[str],
    flights: Iterable[tuple[int, int]] = (),
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, dict[str, int]]:
    """Join several networks at their hubs.

    A hub becomes a node when it reaches at least two networks. A flight is kept when
    both its airports have a connector.

    Args:
        layers: Each network, by its node mode, as the network file's arrays, with
            `edge_class_ids`. The arrays are emptied.
        hubs: The hubs to join.
        land_mask: Land and water around the hubs. Its raster is released.
        node_modes: The names of the node modes: every layer and every kind
            of hub.
        flights: The two airport ids of each pair with regular flights.
        work_dir: A folder that keeps the edges in files. None keeps them in memory.

    Returns:
        The joined network as the network file's arrays, and the number of hubs
        joined of each kind. `node_mode_ids` gives the position of the node mode of each
        node in `node_modes`. `external_node_ids` keeps each layer's ids and gives each
        hub its id in its table. `edge_class_ids` gives the id of the class of each edge
        in `scgraph.pipelines.CLASSES`.
    """
    layers = {mode: _Network(network) for mode, network in layers.items()}
    # The class id of a connector, by the network that it reaches, and of a flight
    connector_class_id = {
        mode: CLASS_IDS[f"{mode}_connector"] for mode in layers
    }
    flight_class_id = CLASS_IDS["flight"]
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

    def add(u, v, km, shape, class_id):
        pieces.append(u, v, km, 1, [at(u), at(v)], shape, class_id)

    # 1. The edges of each layer, on node indices that follow each other
    for mode, layer in layers.items():
        for u, v, km, shape, class_id in layer.edges():
            add(first[mode] + u, first[mode] + v, km, shape, class_id)
    # 2. The connectors of each hub, and its node if it reaches two networks
    connect = {
        mode: _build_land_connector(layer, land_mask, CONNECTOR_KM[mode])
        for mode, layer in layers.items()
        if mode != "sea"
    }
    if "sea" in layers:
        connect["sea"] = _build_sea_connector(layers["sea"], land_mask)
    connectors = (
        []
    )  # each hub, with the connectors it finds: network -> (node, km, shape)
    for hub in hubs:
        edges = {
            mode: connect[mode](hub)
            for mode in hub.joined_node_modes
            if mode in connect
        }
        connectors.append(
            (hub, {mode: edge for mode, edge in edges.items() if edge})
        )
    # A flight is kept when both its airports have a road connector
    reached = {
        hub.id
        for hub, edges in connectors
        if hub.node_mode == "airport" and edges
    }
    flights = [flight for flight in flights if set(flight) <= reached]
    flying = {a for flight in flights for a in flight}
    kinds, ids, airport = [], array("q"), {}
    for hub, edges in connectors:
        flies = hub.node_mode == "airport" and hub.id in flying
        if (
            len(edges) + flies < 2
        ):  # the flights count as a network of an airport
            continue
        h = n + len(points)
        points.append(hub.point)
        kinds.append(hub.node_mode)
        ids.append(hub.id)
        if hub.node_mode == "airport":
            airport[hub.id] = h
        for mode, (u, km, shape) in edges.items():
            u += first[mode]
            add(h, u, km, shape, connector_class_id[mode])
            add(u, h, km, shape[::-1], connector_class_id[mode])
    # 3. The flights, airport to airport
    for one, other in flights:
        a, b = airport[one], airport[other]
        km = haversine(at(a), at(b))
        add(a, b, km, [], flight_class_id)
        add(b, a, km, [], flight_class_id)
    # 4. The graph, with the node mode and the source id of each node
    layer_ids = [layer.ids for layer in layers.values()]
    layer_node_mode_ids = [node_modes.index(mode) for mode in layers]
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
    node_mode_ids = bytearray()
    for node_mode_id, size in zip(layer_node_mode_ids, sizes):
        node_mode_ids += bytes([node_mode_id]) * size
    node_mode_ids += bytes(node_modes.index(kind) for kind in kinds)
    # build_graph_from_pieces renumbers the nodes; its external_node_ids are the numbers
    # the nodes had here
    old = joined["external_node_ids"]
    joined["node_mode_ids"] = array("B", (node_mode_ids[u] for u in old))
    joined["external_node_ids"] = array("q", (all_ids[u] for u in old))
    return joined, {kind: kinds.count(kind) for kind in dict.fromkeys(kinds)}


def _build_land_connector(
    layer: _Network, land_mask: "LandMask", max_km: float
):
    """`connect(hub)` -> (node of `layer`, km, shape) or None, by the rule of the module
    docstring for road and rail."""
    labels, sizes = find_strongly_connected_components(
        layer.node_first_edge_ids, layer.edge_destination_node_ids
    )
    components = array("i", (sizes[label] for label in labels))
    near = NearNodes(layer.latitudes, layer.longitudes, scale=1e-7)

    def connect(hub):
        water_km = ROADSTEAD_WATER_KM if hub.open_roadstead else WATER_KM
        # Largest component first, then closest
        for _, km, u in sorted(
            (-components[u], km, u)
            for km, u in near.find_within(hub.point, max_km)
        ):
            if (
                _measure_water_km(land_mask, hub.point, layer.point(u), km)
                < water_km
            ):
                return u, CIRCUITY * km, []
        return None

    return connect


def _build_sea_connector(layer: _Network, land_mask: "LandMask"):
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


def _measure_water_km(land_mask, point_a, point_b, distance_km):
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
