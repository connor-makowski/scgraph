"""Read OpenStreetMap files into a GeoGraph.

Needs the optional dependency `osmium` (`pip install scgraph[osm]`), imported only when a file
is read.
"""

import os
from array import array
from bisect import bisect_left

from scgraph.helpers.polylines import polylines_to_graph
from scgraph.pipelines import download_file

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


def keep_largest_component(graph, nodes, shapes, node_ids):
    """Keep the largest strongly connected component, the part where every node can reach
    every other, so that no origin or destination is placed on a one-way dead end or on a
    fragment cut by the border of an extract."""
    kept = _largest_strongly_connected(graph)
    index = {old: new for new, old in enumerate(kept)}
    return (
        [
            {index[v]: w for v, w in graph[u].items() if v in index}
            for u in kept
        ],
        [nodes[u] for u in kept],
        [
            {index[v]: s for v, s in shapes[u].items() if v in index}
            for u in kept
        ],
        [node_ids[u] for u in kept],
    )


def _largest_strongly_connected(graph):
    """Nodes of the largest strongly connected component, in increasing order (Kosaraju:
    order the nodes by the end of a depth-first search, then search the reverse graph).
    """
    n = len(graph)
    finished, seen = [], [False] * n
    for start in range(n):
        if seen[start]:
            continue
        seen[start] = True
        stack = [(start, iter(graph[start]))]
        while stack:
            node, successors = stack[-1]
            successor = next(successors, None)
            if successor is None:
                stack.pop()
                finished.append(node)
            elif not seen[successor]:
                seen[successor] = True
                stack.append((successor, iter(graph[successor])))
    reverse = [[] for _ in range(n)]
    for origin, row in enumerate(graph):
        for destination in row:
            reverse[destination].append(origin)
    component, sizes = [-1] * n, []
    for start in reversed(finished):
        if component[start] != -1:
            continue
        component[start], stack, size = len(sizes), [start], 0
        while stack:
            node = stack.pop()
            size += 1
            for predecessor in reverse[node]:
                if component[predecessor] == -1:
                    component[predecessor] = len(sizes)
                    stack.append(predecessor)
        sizes.append(size)
    if not sizes:
        return []
    largest = sizes.index(max(sizes))
    return [node for node in range(n) if component[node] == largest]
