"""Turn geographic polylines (roads, railways, sea lanes) into a routable graph.

Nodes are the points where polylines end or meet, and along them the first point where the
arc since the previous node reaches `max_km`; each arc carries its length along the full
polyline and its shape (the points between its two nodes).
"""

from collections.abc import Container, Hashable, Iterable, Iterator

from scgraph.helpers.hilbert import hilbert_key
from scgraph.utils import haversine


def cut_polylines(
    polylines: Iterable[tuple[int, list[tuple[Hashable, list[float]]]]],
    junctions: Container,
    max_km_between_nodes: float,
) -> Iterator[tuple[Hashable, Hashable, float, int, list[list[float]]]]:
    """
    Cut each polyline at its ends, at its junctions and at the first point where the piece
    since the last cut reaches `max_km_between_nodes`, and yield
    `(origin_id, destination_id, km, direction, shape)` for each piece.

    `polylines` yields `(direction, points)`: `direction` is 1 (one way, along the points), -1
    (one way, against them) or 0 (both ways); `points` is a list of `(id, [latitude,
    longitude])`. `km` is the length of the full piece of polyline and `shape` holds the points
    between its two ends (none if there are none). A piece may start and end at the same
    point.
    """
    for direction, points in polylines:
        start, km = 0, 0.0
        for i in range(1, len(points)):
            km += haversine(points[i - 1][1], points[i][1])
            if (
                i == len(points) - 1
                or points[i][0] in junctions
                or km >= max_km_between_nodes
            ):
                shape = [point for _, point in points[start + 1 : i]]
                yield points[start][0], points[i][0], km, direction, shape
                start, km = i, 0.0


def polylines_to_graph(
    polylines: Iterable[tuple[int, list[tuple[Hashable, list[float]]]]],
    junctions: Container,
    max_km_between_nodes: float,
) -> tuple[
    list[dict[int, float]],
    list[list[float]],
    list[dict[int, list[list[float]]]],
    list[Hashable],
]:
    """
    Collect the `cut_polylines` of `polylines` into a graph: there are no self-loops, and parallel
    arcs keep the shortest (the first seen among arcs of equal length).

    Returns `(graph, nodes, shapes, node_ids)`, with nodes in Hilbert order and
    `node_ids` the id of each node's point.
    """
    arcs = {}  # (origin id, destination id) -> (length, shape)
    location = {}  # id -> [latitude, longitude]
    for polyline in polylines:
        where = dict(polyline[1])
        for origin, destination, km, direction, shape in cut_polylines(
            [polyline], junctions, max_km_between_nodes
        ):
            if origin == destination:
                continue  # a loop never lies on a shortest path
            location[origin] = where[origin]
            location[destination] = where[destination]
            if direction >= 0:
                _keep_shortest(arcs, (origin, destination), km, shape)
            if direction <= 0:
                _keep_shortest(arcs, (destination, origin), km, shape[::-1])

    # Ties broken by coordinates, so that the order does not depend on the input's
    order = sorted(
        location,
        key=lambda point: (
            hilbert_key(*location[point]),
            *location[point],
            point,
        ),
    )
    index = {point: i for i, point in enumerate(order)}
    graph = [{} for _ in order]
    shapes = [{} for _ in order]
    for (origin, destination), (length, shape) in arcs.items():
        graph[index[origin]][index[destination]] = length
        if shape:
            shapes[index[origin]][index[destination]] = shape
    return graph, [location[point] for point in order], shapes, order


def _keep_shortest(arcs, key, length, shape):
    if key not in arcs or length < arcs[key][0]:
        arcs[key] = (length, shape)
