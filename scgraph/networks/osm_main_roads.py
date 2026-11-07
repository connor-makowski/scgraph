"""Main roads (motorway, trunk, primary and their links) and car ferries of an OpenStreetMap
extract from Geofabrik, for example `region="europe/luxembourg"`.

A car ferry (`route=ferry`, unless `motor_vehicle=no` or `motorcar=no`) is an arc both ways
between the road nodes nearest its two ends, with the length of its route, if both lie
within 2 km; otherwise it is left out, as is each piece of a ferry drawn as several ways
that meet at sea.
"""

import math

from scgraph.geograph import GeoGraph, SnapIndex
from scgraph.networks import download_file
from scgraph.osm import (
    keep_largest_component,
    main_roads,
    read_osm,
    require_osmium,
)
from scgraph.utils import haversine

VERSION = 1

SOURCES = {
    "roads": {
        "url": "https://download.geofabrik.de/{region}-latest.osm.pbf",
        "credit": "© OpenStreetMap contributors",
        "license": "ODbL-1.0",
        "license_url": "https://www.openstreetmap.org/copyright",
    }
}
FERRY_END_KM = 2


def download(url, filename):
    require_osmium()  # before downloading a large extract it could not read
    download_file(url, filename)


def build(files):
    graph, nodes, shapes, ids = keep_largest_component(*roads(files["roads"]))
    return GeoGraph(
        graph=graph,
        nodes=nodes,
        intermediate_nodes=shapes,
        node_ids=ids,
        coordinate_dtype="int32",  # OSM's own: 1e-7 degree
    )


def roads(filename):
    """`(graph, nodes, shapes, ids)` of the main roads and ferries, every component."""
    graph, nodes, shapes, ids = read_osm(filename, main_roads, ("highway",))
    if not nodes:
        raise ValueError(f"No main road in {filename}")
    # Read apart: the graph does not tell which arcs come from ferries
    ferries, ends, ferry_shapes, _ = read_osm(
        filename, car_ferries, ("route",), math.inf
    )
    if not ends:
        return graph, nodes, shapes, ids
    index = SnapIndex(nodes)

    def nearest(point):
        u = index.closest_idx(point)
        return u, haversine(point, nodes[u])

    for u, v, km, shape in ferry_arcs(ferries, ends, ferry_shapes, nearest):
        if km < graph[u].get(v, math.inf):  # parallel arcs: the shortest
            graph[u][v], shapes[u][v] = km, shape
    return graph, nodes, shapes, ids


def car_ferries(tags):
    """Both ways (0) for a ferry not closed to cars, None for any other way."""
    if tags.get("route") == "ferry" and "no" not in (
        tags.get("motor_vehicle"),
        tags.get("motorcar"),
    ):
        return 0
    return None


def ferry_arcs(ferries, ends, shapes, nearest):
    """`(u, v, km, shape)` of each ferry arc (`read_osm`'s layout) whose ends lie within
    2 km of road nodes u and v (`nearest(point)` gives `(node, km)`); the shape keeps the
    ferry's ends unless they are u and v."""
    road = [nearest(end) for end in ends]
    for a, row in enumerate(ferries):
        for b, km in row.items():
            (u, to_u), (v, to_v) = road[a], road[b]
            if u != v and max(to_u, to_v) <= FERRY_END_KM:
                shape = [ends[a]] * (to_u > 0) + shapes[a].get(b, [])
                yield u, v, km, shape + [ends[b]] * (to_v > 0)
