"""Read OpenStreetMap files into a GeoGraph.

Needs the optional dependency `osmium` (`pip install scgraph[osm]`), imported only when a file
is read.
"""

from scgraph.helpers.lines import lines_to_graph

MAIN_ROADS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
}
_ONE_WAY = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}


def require_osmium():
    try:
        import osmium
    except ImportError as error:
        raise ImportError(
            "Reading OSM files needs the optional dependency osmium: pip install scgraph[osm]"
        ) from error
    return osmium


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


def _selected_ways(osmium, filename, select, keys):
    """`(direction, way)` for the ways `select` keeps; ways with none of `keys` are
    skipped in osmium, before Python sees them."""
    ways = osmium.FileProcessor(filename, osmium.osm.WAY)
    if keys:
        ways = ways.with_filter(osmium.filter.KeyFilter(*keys))
    for way in ways:
        way_direction = select(way.tags)
        if way_direction is None:
            continue
        if type(way_direction) is not int or way_direction not in (-1, 0, 1):
            raise ValueError(
                f"select returned {way_direction!r}: 1, -1, 0 or None"
            )
        yield way_direction, way


def read_osm(filename, select, keys=(), max_km_between_nodes=2):
    """
    Build the graph of the ways of `filename` that `select` keeps.

    `select(tags)` gives the direction of a way: 1 (one way along its drawing), -1
    (against it), 0 (both ways), or None to drop it. If `keys` is given, the ways that
    have none of these keys (any one of them is enough) are dropped first, in osmium.

    Returns `(graph, nodes, intermediate_nodes, ids)` in the GeoGraph layout, `ids` being
    the OSM ids of the nodes.
    """
    osmium = require_osmium()
    # First pass: OSM nodes used more than once are junctions (where ways meet,
    # or where a way crosses itself); crossings without a shared node, such as
    # bridges and tunnels, are not.
    uses = {}
    for _, way in _selected_ways(osmium, filename, select, keys):
        for node in way.nodes:
            uses[node.ref] = uses.get(node.ref, 0) + 1
    junctions = {ref for ref, count in uses.items() if count > 1}

    # Second pass: the positions of the nodes of kept ways only (the id filter
    # takes about 1.5 GB whatever the file, a node index would grow with it)
    nodes = osmium.FileProcessor(filename, osmium.osm.NODE)
    positions = {
        node.id: [node.lat, node.lon]
        for node in nodes.with_filter(osmium.filter.IdFilter(uses))
    }
    del uses

    # Third pass: one arc per piece of way between junctions
    lines = (
        (way_direction, piece)
        for way_direction, way in _selected_ways(osmium, filename, select, keys)
        for piece in _located_pieces(way.nodes, positions)
    )
    return lines_to_graph(lines, junctions, max_km_between_nodes)


def _located_pieces(way_nodes, positions):
    """Split a way where a node is missing from the file (outside an extract)."""
    piece = []
    for node in way_nodes:
        if node.ref in positions:
            piece.append((node.ref, positions[node.ref]))
            continue
        if len(piece) > 1:
            yield piece
        piece = []
    if len(piece) > 1:
        yield piece


def keep_largest_component(graph, nodes, shapes, ids):
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
        [ids[u] for u in kept],
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
