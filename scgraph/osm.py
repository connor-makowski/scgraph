"""Read OpenStreetMap files into a GeoGraph.

Needs the optional dependency `osmium` (`pip install scgraph[osm]`), imported only when a file
is read.
"""

from scgraph.utils import haversine

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


def _kept_ways(osmium, filename, keep):
    """The ways whose tags match `keep`; ways without a required key are skipped in
    osmium, before Python sees them."""
    ways = osmium.FileProcessor(filename, osmium.osm.WAY)
    required = [key for key, values in keep.items() if None not in values]
    if required:
        ways = ways.with_filter(osmium.filter.KeyFilter(*required))
    return (
        way
        for way in ways
        if all(way.tags.get(key) in values for key, values in keep.items())
    )


def _direction(tags):
    """1: one way along the drawing, -1: against it, 0: both ways."""
    if tags.get("oneway") in _ONE_WAY:
        return _ONE_WAY[tags["oneway"]]
    # One way without a tag in OSM: motorways and roundabouts
    if tags.get("oneway") is None and (
        tags.get("highway") == "motorway"
        or tags.get("junction") in ("roundabout", "circular")
    ):
        return 1
    return 0


def read_osm(filename, keep, directed, max_km_between_nodes):
    """
    Build the graph of the ways of `filename` whose tags match `keep`.

    Returns `(graph, nodes, intermediate_nodes)` in the GeoGraph layout.
    """
    osmium = require_osmium()
    # First pass: OSM nodes used more than once are junctions (where ways meet,
    # or where a way crosses itself); crossings without a shared node, such as
    # bridges and tunnels, are not.
    uses = {}
    for way in _kept_ways(osmium, filename, keep):
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

    # Third pass: one arc per piece of way between junctions, with the length
    # of its full shape; parallel arcs keep the shortest; no self-loops.
    arcs = {}  # (origin ref, destination ref) -> (length, shape)
    location = {}  # ref -> [latitude, longitude] of the arc ends
    for way in _kept_ways(osmium, filename, keep):
        direction = _direction(way.tags) if directed else 0
        for piece in _located_pieces(way.nodes, positions):
            start, length = 0, 0.0
            for i in range(1, len(piece)):
                length += haversine(piece[i - 1][1], piece[i][1])
                if (
                    i == len(piece) - 1
                    or piece[i][0] in junctions
                    or length >= max_km_between_nodes
                ):
                    _add_arc(
                        arcs, location, piece[start : i + 1], length, direction
                    )
                    start, length = i, 0.0

    order = sorted(location, key=lambda ref: (*location[ref], ref))
    index = {ref: i for i, ref in enumerate(order)}
    graph = [{} for _ in order]
    shapes = [{} for _ in order]
    for (origin, destination), (length, shape) in arcs.items():
        graph[index[origin]][index[destination]] = length
        shapes[index[origin]][index[destination]] = shape
    return graph, [location[ref] for ref in order], shapes


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


def _add_arc(arcs, location, piece, length, direction):
    origin, destination = piece[0][0], piece[-1][0]
    if origin == destination:
        return  # a loop never lies on a shortest path
    location[origin], location[destination] = piece[0][1], piece[-1][1]
    shape = [point for _, point in piece]
    if direction >= 0:
        _keep_shortest(arcs, (origin, destination), length, shape)
    if direction <= 0:
        _keep_shortest(arcs, (destination, origin), length, shape[::-1])


def _keep_shortest(arcs, key, length, shape):
    if key not in arcs or length < arcs[key][0]:
        arcs[key] = (length, shape)


def keep_largest_component(graph, nodes, shapes):
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
