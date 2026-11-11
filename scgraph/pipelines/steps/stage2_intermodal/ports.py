"""Join ports to two networks: a straight road connector checked against water, and a
sea connector over water (`landmask`)."""

import csv
import math
from array import array

from scgraph.pipelines.steps.stage3_assembly.assembly import (
    NearNodes,
    PieceArrays,
    build_graph_from_pieces,
    strongly_connected_components,
)
from scgraph.utils import haversine

ROAD_KM, SEA_KM = 20, 2500  # longest road and sea connectors
# Water a road connector may cross: 3 km, 10 km for an open roadstead
WATER_KM, ROADSTEAD_WATER_KM = 3, 10
CIRCUITY = 1.2  # of a straight road connector


def world_port_index(filename):
    """[latitude, longitude, harbour type] of each port with a position in the CSV file
    of the World Port Index."""
    with open(filename, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if row["Latitude"] and row["Longitude"]:
                lat, lon = float(row["Latitude"]), float(row["Longitude"])
                yield [lat, lon, row["Harbor Type"]]


def join(graph, sea, port_rows, mask, folder=None):
    """
    `graph` (`assembly.road_graph`'s layout) joined to the sea lanes of the GeoGraph `sea`
    at the ports of `port_rows` ([latitude, longitude, harbour type]) that have both
    connectors, on node indices: the sea nodes follow the road nodes, then the ports, each
    in their order; `node_modes` 0 for a road node, 1 for a port, 2 for a sea node; the
    ports' `node_ids` are scgraph's (negative). The drawings are kept as they are (the
    roads' were simplified when cut). Returns `(graph, ports joined)`; empties `graph`
    and releases the raster of `mask`, spent.
    With a `folder`, the arcs are kept in files there (`PieceArrays`).
    """
    offsets, heads, weights = graph["offsets"], graph["heads"], graph["weights"]
    starts, line = graph["shape_offsets"], graph["shape_points"]
    labels, sizes = strongly_connected_components(offsets, heads)
    components = array("i", (sizes[label] for label in labels))
    roads, seas = len(offsets) - 1, len(sea.nodes)
    # The road nodes' coordinates at 1e-7 degree, read in place
    lats, lons = graph["latitudes"], graph["longitudes"]
    near = NearNodes(lats, lons, scale=1e-7)
    others = list(sea.nodes)  # then the ports, in degrees
    cells = {}  # mask cell -> its first sea node
    for s, node in enumerate(sea.nodes):
        cells.setdefault(mask.cell(*node), s)
    cells.pop(None, None)
    targets = array("q", sorted(cells))
    # Every arc, one way, on node indices
    pieces = PieceArrays(tolerance_m=None, folder=folder)

    def at(u):  # [latitude, longitude] of node u
        if u < roads:
            return [lats[u] * 1e-7, lons[u] * 1e-7]
        return others[u - roads]

    def add(u, v, km, shape):
        pieces.append(u, v, km, 1, [at(u), at(v)], shape)

    for u in range(roads):
        for a in range(offsets[u], offsets[u + 1]):
            points = line[2 * starts[a] : 2 * starts[a + 1]]
            shape = [
                [x * 1e-7, y * 1e-7] for x, y in zip(points[::2], points[1::2])
            ]
            add(u, heads[a], weights[a], shape)
    sea_shapes = sea.intermediate_nodes or [{}] * seas
    for u, row in enumerate(sea.graph_object.graph):
        for v, km in row.items():
            add(roads + u, roads + v, km, sea_shapes[u].get(v, []))
    for point, arcs in port_connectors(
        port_rows,
        lambda port: road_connector(port, near, components, mask),
        lambda point: sea_connector(point, targets, cells, sea.nodes, mask),
        roads + seas,
        roads,
    ):
        others.append(point)
        for a, b, km, shape in arcs:
            add(a, b, km, shape)
    ports = len(others) - seas
    ids = array("q", graph["node_ids"]) + array("q", sea.node_ids)
    graph.clear()  # freed before the joined graph is built, and the raster
    mask.bits = None
    del lats, lons, near, labels, sizes, components
    del offsets, heads, weights, starts, line
    joined = build_graph_from_pieces(pieces)
    ids += array("q", range(-1, -1 - ports, -1))  # scgraph's, for the ports
    modes = bytes(roads) + bytes([2]) * seas + bytes([1]) * ports
    joined["node_modes"] = array("B", (modes[u] for u in joined["node_ids"]))
    joined["node_ids"] = array("q", (ids[u] for u in joined["node_ids"]))
    return joined, ports


def port_connectors(ports, road, sea, first_port, first_sea):
    """`(point, arcs)` of each port of `ports` ([latitude, longitude, harbour type]) with
    a road connector, `road(port)` -> `(road node, km)`, and a sea connector, `sea(point)`
    -> `(sea node, km, path)` (None if none), ports numbered from `first_port`, sea nodes
    from `first_sea`. `arcs`: `(origin, destination, km, shape)` both ways, 1.2 times the
    straight line to the road, the water path to the sea."""
    p = first_port
    for port in ports:
        to_road = road(port)
        to_sea = to_road and sea(port[:2])
        if to_sea:
            (u, road_km), (s, sea_km, path) = to_road, to_sea
            road_km, s = CIRCUITY * road_km, first_sea + s
            yield port[:2], [
                (p, u, road_km, []),
                (u, p, road_km, []),
                (p, s, sea_km, path),
                (s, p, sea_km, path[::-1]),
            ]
            p += 1


def road_connector(port, near, components, mask):
    """
    `(road node, km)`: the road connector of `port` ([latitude, longitude, harbour type]),
    or None. `near`: the road nodes' `assembly.NearNodes`; `components`: the size of each
    node's strongly connected component.
    """
    point = port[:2]
    water_km = ROADSTEAD_WATER_KM if port[2] == "Open Roadstead" else WATER_KM
    # Largest component first, then nearest
    for _, km, i in sorted(
        (-components[i], km, i) for km, i in near.within(point, ROAD_KM)
    ):
        target = [near.lats[i] * near.scale, near.lons[i] * near.scale]
        if _water_km(mask, point, target, km) < water_km:
            return i, km
    return None


def sea_connector(point, targets, cells, sea_nodes, mask):
    """`(sea node, km, path)`: the sea connector of `point`, or None. `targets`: the mask
    cells of the sea nodes, sorted in an array('q'); `cells`: {cell: sea node}.
    """
    found = mask.water_path(point, targets, SEA_KM)
    if not found:
        return None
    km, path = found
    s = cells[mask.cell(*path[-1])]
    return s, km + haversine(path[-1], sea_nodes[s]), path


def _water_km(mask, a, b, km):
    """km of water along the straight line a-b (`km` long), sampled every 0.25 km."""
    n = max(1, math.ceil(km / 0.25))
    water = sum(
        not mask.on_land(*(x + (j + 0.5) / n * (y - x) for x, y in zip(a, b)))
        for j in range(n)
    )
    return km * water / n
