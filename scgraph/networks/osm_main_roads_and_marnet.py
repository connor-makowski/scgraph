"""Main roads of an OpenStreetMap extract from Geofabrik joined to the sea lanes of
`eurostat_marnet` at the ports of the World Port Index, for example `region="europe/denmark"`.

- A distance is in km along the network: main roads and car ferries (directed, as
  `osm_main_roads`), sea lanes (undirected, as `eurostat_marnet`) and the two connectors
  of each joined port. There are no times, and changing mode at a port costs nothing.
- A port with a position joins when it has both connectors; the others stay out rather
  than be joined over land or across the sea.
- Road connector: a straight line to the nearest main-road node within 20 km whose line
  crosses less than 3 km of water (10 km for an open roadstead), in the largest road
  component that has such a node; it weighs 1.2 times its length.
- Sea connector: the shortest path over water to a sea node, at most 2,500 km and within
  2 degrees of the region's roads, starting within 6 km of the port, on cells of 1/240
  degree of Natural Earth 1:10m land, lakes and river centrelines; it weighs its length,
  and its shape points are the cells' centres, stored to 1e-7 degree.
- The network keeps its largest strongly connected component. Each node has its mode,
  `road`, `port` or `sea` (`node_modes`, rows of `modes`), each mode citing the source of
  its node ids.
- Not for: navigation or travel times; inland navigation between two river points.
"""

import csv
import math
from array import array
from bisect import bisect_left, bisect_right

from scgraph.geograph import GeoGraph
from scgraph.helpers.assembly import strong_components
from scgraph.helpers.landmask import LandMask
from scgraph.networks import eurostat_marnet, osm_main_roads
from scgraph.osm import keep_largest_component
from scgraph.utils import haversine

# Follows the versions of the two builds it reuses
VERSION = 1 + eurostat_marnet.VERSION + osm_main_roads.VERSION


def _natural_earth(layer):
    return {
        "url": f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/f1890d9f152c896d250a77557a5751a93d494776/geojson/ne_10m_{layer}.geojson",
        "credit": "Natural Earth (1:10m, v5.1.2)",
        "license": "LicenseRef-public-domain",
        "license_url": "https://github.com/nvkelso/natural-earth-vector/blob/f1890d9f152c896d250a77557a5751a93d494776/LICENSE.md",
    }


# Small sources first: a failure then costs no new download of the extract
SOURCES = {
    "sea": eurostat_marnet.SOURCES["lines"],
    "ports": {
        "url": "https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv",
        "credit": "National Geospatial-Intelligence Agency, World Port Index (Pub. 150)",
        "license": "NOASSERTION",
        "license_url": "https://msi.nga.mil/Publications/WPI",
    },
    "land": _natural_earth("land"),
    "lakes": _natural_earth("lakes"),
    "rivers": _natural_earth("rivers_lake_centerlines"),
    "roads": osm_main_roads.SOURCES["roads"],
}
MAX_KM = {"road": 20, "sea": 2500}
# Water a road connector may cross: 3 km, 10 km for an open roadstead
WATER_KM, ROADSTEAD_WATER_KM = 3, 10
CIRCUITY = 1.2  # of a straight road connector
MARGIN = 2  # degrees of raster around the roads, where sea connectors run

download = osm_main_roads.download  # for every source: checks osmium first


def build(files):
    graph, nodes, shapes, ids = osm_main_roads.roads(files["roads"])
    sea = eurostat_marnet.build({"lines": files["sea"]})
    lats, lons = [lat for lat, _ in nodes], [lon for _, lon in nodes]
    south, west = max(-90, min(lats) - MARGIN), max(-180, min(lons) - MARGIN)
    north, east = min(90, max(lats) + MARGIN), min(180, max(lons) + MARGIN)
    mask = LandMask.from_natural_earth(
        *(files[name] for name in ("land", "lakes", "rivers")),
        bbox=(south, west, north, east),
    )
    cells = {}  # cell -> its first sea node
    for s, node in enumerate(sea.nodes):
        cells.setdefault(mask.cell(*node), s)
    cells.pop(None, None)
    offsets, heads = array("i", [0]), array("i")
    for row in graph:
        heads.extend(row)
        offsets.append(len(heads))
    labels, sizes = strong_components(offsets, heads)
    by_lat = sorted(range(len(nodes)), key=lats.__getitem__)
    roads = (lats, lons, [sizes[label] for label in labels], by_lat)
    targets = array("q", sorted(cells))
    joined = [
        (port[:2], found)
        for port in _ports(files["ports"])
        if mask.cell(*port[:2]) is not None  # near the region
        and (found := connect(port, roads, (targets, cells, sea.nodes), mask))
    ]

    # Roads, then ports, then sea nodes
    first_sea = len(nodes) + len(joined)
    sea_shapes = sea.intermediate_nodes or [{}] * len(sea.nodes)
    graph += [{} for _ in joined] + [
        {first_sea + t: w for t, w in row.items()}
        for row in sea.graph_object.graph
    ]
    shapes += [{} for _ in joined] + [
        {first_sea + t: v for t, v in row.items()} for row in sea_shapes
    ]
    for p, (_, ((u, road_km), (s, sea_km, path))) in enumerate(
        joined, len(nodes)
    ):
        s += first_sea
        graph[u][p] = graph[p][u] = CIRCUITY * road_km
        graph[p][s] = graph[s][p] = sea_km
        shapes[p][s], shapes[s][p] = path, path[::-1]
    nodes += [point for point, _ in joined] + list(sea.nodes)
    # Port ids are scgraph's (negative), not the port index's
    keys = [(i, 0) for i in ids] + [(-1 - p, 1) for p in range(len(joined))]
    keys += [(i, 2) for i in sea.node_ids]
    graph, nodes, shapes, keys = keep_largest_component(
        graph, nodes, shapes, keys
    )
    return GeoGraph(
        graph=graph,
        nodes=nodes,
        intermediate_nodes=shapes,
        node_ids=[i for i, _ in keys],
        node_modes=[mode for _, mode in keys],
        modes=[
            {"name": "road", "source": "roads"},
            {"name": "port"},
            {"name": "sea", "source": "sea"},
        ],
        coordinate_dtype="int32",
    )


def connect(port, roads, sea, mask):
    """
    The connectors of `port` ([latitude, longitude, harbour type]) as `((road node, km),
    (sea node, km, path))`, or None if it lacks one. `roads`: (latitudes, longitudes, the
    size of each node's strongly connected component, nodes by latitude); `sea`: (the mask
    cells of the sea nodes, sorted in an array('q'), {cell: sea node}, sea nodes).
    """
    point, lats, lons, size, by_lat = port[:2], *roads
    band = MAX_KM["road"] / 111  # degrees of latitude: a little more than 20 km
    lo = bisect_left(by_lat, point[0] - band, key=lats.__getitem__)
    hi = bisect_right(by_lat, point[0] + band, key=lats.__getitem__)
    near = sorted(  # largest component first, then nearest
        (-size[i], km, i)
        for i in by_lat[lo:hi]
        if (km := haversine(point, [lats[i], lons[i]])) <= MAX_KM["road"]
    )
    roadstead = port[2] == "Open Roadstead"
    water_km = ROADSTEAD_WATER_KM if roadstead else WATER_KM
    road = next(
        (
            (i, km)
            for _, km, i in near
            if _water_km(mask, point, [lats[i], lons[i]], km) < water_km
        ),
        None,
    )
    targets, cells, sea_nodes = sea
    found = road and mask.water_path(point, targets, MAX_KM["sea"])
    if not found:
        return None
    km, path = found
    s = cells[mask.cell(*path[-1])]
    return road, (s, km + haversine(path[-1], sea_nodes[s]), path)


def _water_km(mask, a, b, km):
    """km of water along the straight line a-b (`km` long), sampled every 0.25 km."""
    n = max(1, math.ceil(km / 0.25))
    water = sum(
        not mask.on_land(*(x + (j + 0.5) / n * (y - x) for x, y in zip(a, b)))
        for j in range(n)
    )
    return km * water / n


def _ports(filename):
    """[latitude, longitude, harbour type] of each port with a position."""
    with open(filename, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if row["Latitude"] and row["Longitude"]:
                lat, lon = float(row["Latitude"]), float(row["Longitude"])
                yield [lat, lon, row["Harbor Type"]]
