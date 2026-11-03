"""Turn lines into a GeoGraph layout: arcs between the points where lines meet, with their
shape."""

from scgraph.utils import haversine


def lines_to_graph(lines, junctions, max_km_between_nodes):
    """
    Cut each line at its ends, at its junctions and at least every `max_km_between_nodes`.

    `lines` yields `(direction, points)`: `direction` is 1 (one way, along the points), -1
    (one way, against them) or 0 (both ways); `points` is a list of `(id, [latitude,
    longitude])`. Each arc has the length of its full shape; parallel arcs keep the
    shortest; there are no self-loops.

    Returns `(graph, nodes, intermediate_nodes)`, with nodes sorted by coordinates.
    """
    arcs = {}  # (origin id, destination id) -> (length, shape)
    location = {}  # id -> [latitude, longitude]
    for direction, points in lines:
        start, length = 0, 0.0
        for i in range(1, len(points)):
            length += haversine(points[i - 1][1], points[i][1])
            if (
                i == len(points) - 1
                or points[i][0] in junctions
                or length >= max_km_between_nodes
            ):
                _add_arc(
                    arcs, location, points[start : i + 1], length, direction
                )
                start, length = i, 0.0

    order = sorted(location, key=lambda point: (*location[point], point))
    index = {point: i for i, point in enumerate(order)}
    graph = [{} for _ in order]
    shapes = [{} for _ in order]
    for (origin, destination), (length, shape) in arcs.items():
        graph[index[origin]][index[destination]] = length
        shapes[index[origin]][index[destination]] = shape
    return graph, [location[point] for point in order], shapes


def _add_arc(arcs, location, points, length, direction):
    origin, destination = points[0][0], points[-1][0]
    if origin == destination:
        return  # a loop never lies on a shortest path
    location[origin], location[destination] = points[0][1], points[-1][1]
    shape = [point for _, point in points]
    if direction >= 0:
        _keep_shortest(arcs, (origin, destination), length, shape)
    if direction <= 0:
        _keep_shortest(arcs, (destination, origin), length, shape[::-1])


def _keep_shortest(arcs, key, length, shape):
    if key not in arcs or length < arcs[key][0]:
        arcs[key] = (length, shape)
