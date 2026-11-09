"""Read OpenStreetMap files into a GeoGraph.

Needs the optional dependency `osmium` (`pip install scgraph[osm]`), imported only when a file
is read.
"""

import math
import os
from array import array
from bisect import bisect_left

from scgraph.helpers.polylines import cut_polylines, polylines_to_graph
from scgraph.pipelines import download_file
from scgraph.pipelines.steps.stage3_assembly.assembly import (
    NearNodes,
    PieceArrays,
)

# The OpenStreetMap extracts of Geofabrik, `{region}` being the path of an extract
GEOFABRIK = {
    "url": "https://download.geofabrik.de/{region}-latest.osm.pbf",
    "credit": "© OpenStreetMap contributors",
    "license": "ODbL-1.0",
    "license_url": "https://www.openstreetmap.org/copyright",
}

MAIN_ROADS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
}
# Length in kilometers at which a way is cut into a new arc (at the next point), so that
# origins and destinations attach close to where they are
MAX_KM = 2
FERRY_END_KM = 2  # farthest a ferry end may lie from the road node it joins
_ONE_WAY = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}
# origins and destinations attach close to where they are
MAX_KM = 2
_ONE_WAY = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}


def require_osmium():
    try:
        import osmium
    except ImportError as error:
        raise ImportError(
            "Reading OSM files needs the optional dependency osmium: pip install scgraph[osm]"
        ) from error
    return osmium


def download(url, filename):
    """Download an OSM file; return its `version`, the time its data is up to (the
    `osmosis_replication_timestamp` of its header, as Geofabrik writes it), if it has one.
    """
    # Checked before downloading a large extract it could not read
    osmium = require_osmium()
    download_file(url, filename)
    try:
        reader = osmium.io.Reader(filename, osmium.osm.osm_entity_bits.NOTHING)
    except RuntimeError:  # not an OSM file: another source of the same network
        return {}
    try:
        version = reader.header().get("osmosis_replication_timestamp")
    finally:
        reader.close()
    return {"version": version} if version else {}


def direction(tags):
    """The direction of a way from its tags: 1 (one way, along its drawing) for
    `oneway=yes`, `true` or `1`, and for motorways and roundabouts without `oneway`; -1
    (one way, against it) for `oneway=-1` or `reverse`; 0 (both ways) otherwise.
    """
    if tags.get("oneway") in _ONE_WAY:
        return _ONE_WAY[tags["oneway"]]
    # One way without a tag in OSM: motorways and roundabouts
    if tags.get("oneway") is None and (
        tags.get("highway") == "motorway"
        or tags.get("junction") in ("roundabout", "circular")
    ):
        return 1
    return 0


def main_roads(tags):
    """The direction of a main road (`MAIN_ROADS`), None for any other way."""
    return direction(tags) if tags.get("highway") in MAIN_ROADS else None


def _input(source):
    # A path, or what the source gives for one pass (see locate_ways)
    return source if isinstance(source, (str, os.PathLike)) else source.file()


def _selected_ways(osmium, source, selects, tag_keys, *filters):
    """`(kind, direction, way)` for the ways one of `selects` keeps (the first, in their
    order); ways with none of `tag_keys` are skipped in osmium, before Python sees them,
    and so are `filters`."""
    ways = osmium.FileProcessor(_input(source), osmium.osm.WAY)
    if tag_keys:
        ways = ways.with_filter(osmium.filter.KeyFilter(*tag_keys))
    for osmium_filter in filters:
        ways = ways.with_filter(osmium_filter)
    for way in ways:
        for kind, select in selects.items():
            way_direction = select(way.tags)
            if way_direction is not None:
                break
        else:
            continue
        if type(way_direction) is not int or way_direction not in (-1, 0, 1):
            raise ValueError(
                f"select returned {way_direction!r}: 1, -1, 0 or None"
            )
        yield kind, way_direction, way


class _Junctions:
    """Node ids, sorted, looked up by bisection: 8 bytes per junction once built. While
    it is built (after the id tracker is freed), the sorted list of repeated uses takes
    about 40 B per repeat (a node used k times appears k - 1 times), with no set; with
    the location store still alive, a planet's ~10.8 M repeats would take about 0.43 GB
    next to a ~1.46 GB file store (an estimate, not measured together)."""

    def __init__(self, ids):
        self.ids = array("q")
        for ref in sorted(ids):
            if not self.ids or self.ids[-1] != ref:
                self.ids.append(ref)

    def __contains__(self, ref):
        i = bisect_left(self.ids, ref)
        return i < len(self.ids) and self.ids[i] == ref


def locate_ways(source, selects, tag_keys=(), node_store=None):
    """
    Locate the ways of `source` that `selects` keep, in one set of passes for every kind
    of way (roads and ferries, for example).

    `selects` maps a kind of way to its `select(tags)`, which gives the direction of a way:
    1 (one way along its drawing), -1 (against it), 0 (both ways), or None to leave it to
    the next select; a way goes to the first select that keeps it, in the mapping's order.
    If `tag_keys` is given, the ways that have none of these keys are dropped first, in
    osmium.

    `source` is the path of an OSM file, or an object whose `file()` returns what
    `osmium.FileProcessor` reads (an `osmium.io.File` or `FileBuffer`), fresh at each call:
    the file is read in three passes (ways, their nodes, ways again), so a source that is
    not on disk, such as a stream, supplies one input per pass.

    The locations of the nodes of kept ways are kept in osmium's `node_store`, an
    `osmium.index.create_map` type: in memory by default (`flex_mem`), or in a file for a
    planet (`"sparse_file_array,<path>"`, emptied first and left for the caller to delete).
    The node ids of kept ways take about 1.5 GB in any case (one bit per possible id),
    and the ids of kept ways about 0.2 GB (one bit per possible way id).

    Returns `(junctions, polylines)`: the OSM ids of the nodes where kept ways meet or a way
    crosses itself, whatever their kind (`in junctions` tests one), and a generator of
    `(kind, direction, points)`, `points` being `[(id, [latitude, longitude]), ...]` and
    `(direction, points)` a polyline as `cut_polylines` takes it, a way being split where
    one of its nodes is missing from the file.
    """
    osmium = require_osmium()
    # First pass: the nodes of kept ways; a node seen again is a junction (where ways
    # meet, or where a way crosses itself); crossings without a shared node, such as
    # bridges and tunnels, are not.
    tracker, kept = osmium.IdTracker(), osmium.IdTracker()
    seen, repeats = tracker.node_ids(), array("q")
    for _, _, way in _selected_ways(osmium, source, selects, tag_keys):
        kept.add_way(way.id)
        for node in way.nodes:
            if seen.get(node.ref):
                repeats.append(node.ref)
            else:
                seen.set(node.ref)

    # Second pass, in osmium: the locations of those nodes, into the store
    node_store = node_store or "flex_mem"
    if "," in node_store:  # osmium would read the locations a previous run left
        open(node_store.partition(",")[2], "wb").close()
    store = osmium.index.create_map(node_store)
    with osmium.io.Reader(_input(source), osmium.osm.NODE) as nodes:
        osmium.apply(
            nodes, tracker.id_filter(), osmium.NodeLocationsForWays(store)
        )
    del tracker, seen  # before the junctions are sorted
    junctions = _Junctions(repeats)
    del repeats

    # Third pass, as the polylines are read: the located pieces of the kept ways (only
    # those are located: the way filter comes first)
    def polylines(locations):
        locations.ignore_errors()  # a node missing from the file: invalid location
        for kind, way_direction, way in _selected_ways(
            osmium, source, selects, tag_keys, kept.id_filter(), locations
        ):
            for piece in _located_pieces(way.nodes):
                yield kind, way_direction, piece

    return junctions, polylines(osmium.NodeLocationsForWays(store))


def read_osm(source, select, tag_keys=(), max_km=MAX_KM):
    """
    Build the graph of the ways of `source` that `select` keeps (`locate_ways`, then
    `polylines_to_graph`), a way being also cut where a piece reaches `max_km`
    (`cut_polylines`).

    Returns `(graph, nodes, shapes, node_ids)` in the GeoGraph layout, `node_ids` being
    the OSM ids of the nodes.
    """
    junctions, polylines = locate_ways(source, {"ways": select}, tag_keys)
    polylines = (
        (way_direction, points) for _, way_direction, points in polylines
    )
    return polylines_to_graph(polylines, junctions, max_km)


def build_way_pieces(source, selects, tag_keys, max_km, folder=None):
    """
    The pieces (`assembly.PieceArrays`) of the ways of `source` that `selects` keep
    (`locate_ways`, one read for every kind), cut at their junctions and where a piece
    reaches `max_km` (`cut_polylines`). The ways of the kind "ferries" are not cut: each
    joins the road nodes nearest its two ends if both lie within FERRY_END_KM
    (`build_ferry_arcs`). Returns `(pieces, steps)`; no way kept raises a ValueError.
    With a `folder`, the node locations and the pieces are kept in files there.
    """
    nodes = folder is not None and os.path.join(folder, "nodes")
    store = nodes and "sparse_file_array," + nodes
    junctions, ways = locate_ways(source, selects, tag_keys, store)
    pieces, ferries = PieceArrays(folder=folder), []
    for kind, direction, points in ways:
        if kind == "ferries":
            ferries.append((direction, points))
            continue
        where = dict(points)
        for origin, destination, km, way, shape in cut_polylines(
            [(direction, points)], junctions, max_km
        ):
            ends = where[origin], where[destination]
            pieces.append(origin, destination, km, way, ends, shape)
    pieces.flush()
    if not len(pieces.km):
        raise ValueError(f"No way of {source} is kept by {', '.join(selects)}")
    steps = [{"step": "read", "pieces": len(pieces.km)}]
    if "ferries" in selects:
        # The road nodes: the pieces' ends at 1e-7 degree, read in place, end u being
        # piece u // 2's origin or destination (ties in nearest: the first end)
        lats, lons = pieces.ends[0::2], pieces.ends[1::2]
        ids = (pieces.origins, pieces.destinations)
        near = NearNodes(lats, lons, scale=1e-7)
        rows, ends, shapes, _ = polylines_to_graph(ferries, junctions, math.inf)
        arcs = list(
            build_ferry_arcs(
                rows, ends, shapes, lambda p: near.nearest(p, FERRY_END_KM)
            )
        )
        for u, v, km, shape in arcs:
            road = [[lats[w] * 1e-7, lons[w] * 1e-7] for w in (u, v)]
            pieces.append(
                ids[u % 2][u // 2], ids[v % 2][v // 2], km, 1, road, shape
            )
        steps.append({"step": "ferries", "arcs": len(arcs)})
    return pieces, steps


def _located_pieces(way_nodes):
    """Split a way where a node is missing from the file (outside an extract) or has no
    location."""
    piece = []
    for node in way_nodes:
        if node.location.valid():
            piece.append((node.ref, [node.lat, node.lon]))
            continue
        if len(piece) > 1:
            yield piece
        piece = []
    if len(piece) > 1:
        yield piece


def vehicle_ferries(tags):
    """Both ways (0) for a ferry not closed to motor vehicles, None for any other way."""
    if tags.get("route") == "ferry" and "no" not in (
        tags.get("motor_vehicle"),
        tags.get("motorcar"),
    ):
        return 0
    return None


def build_ferry_arcs(ferries, ends, shapes, nearest):
    """`(u, v, km, shape)` of each ferry arc (`polylines_to_graph`'s layout) whose ends
    lie within FERRY_END_KM of road nodes u and v (`nearest(point)` gives `(node, km)`);
    the shape keeps the ferry's ends unless they are u and v."""
    road = [nearest(end) for end in ends]
    for a, row in enumerate(ferries):
        for b, km in row.items():
            (u, to_u), (v, to_v) = road[a], road[b]
            if u != v and max(to_u, to_v) <= FERRY_END_KM:
                shape = [ends[a]] * (to_u > 0) + shapes[a].get(b, [])
                yield u, v, km, shape + [ends[b]] * (to_v > 0)
