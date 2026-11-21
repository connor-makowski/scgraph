"""Turn polylines into a graph for routing.

A "polyline" is a road, a railway or a sea lane, given as a list of "vertices". A vertex
is a pair (id, point). A point is [latitude, longitude]. The id names the vertex in its
source, for example an OSM node id. Two vertices with the same id have the same point.

WHAT IT ANSWERS
    `build_graph_from_polylines` builds a graph from the polylines. A path in the graph
    goes from one node to another node along the polylines, in the directions that they
    allow. Its length is the length along the polylines, in kilometers. Thus the shortest
    path between two nodes is the shortest route between them along the polylines.
    A path can go from one polyline to another only at a node. So each place where two
    polylines meet must be a node. Such a place is a "junction". The caller gives the ids
    of the junctions.
    `cut_polylines` gives the "pieces" of the polylines. A piece is the part of a polyline
    between two consecutive nodes. Each piece becomes an edge.

HOW A POLYLINE IS CUT
    A walk along a polyline cuts it at a vertex in three cases:
    1. the vertex is the last vertex of the polyline;
    2. the vertex is a junction;
    3. the piece since the last cut is `max_km_between_nodes` long or longer.
    The first vertex starts the first piece. Each vertex where a piece starts or ends
    becomes a node. The vertices inside a piece become its "shape points". They give the
    shape of the edge, but a route cannot start or end there.
    Case 3 keeps a node every few kilometers. GeoGraph snaps an origin or a destination to
    a node, so a long edge with no node would make it snap far from the road. A piece cut
    in case 3 can be longer than the limit, by less than the length of its last segment.
    Example, with `max_km_between_nodes` = 2. Road A goes both ways. Its vertices 1 to 5
    are on the equator, at the longitudes 0, 0.01, 0.02, 0.03 and 0.04. Two consecutive
    vertices are 1.112 km apart. Road B goes one way, from vertex 2 north to vertex 6, at
    [0.01, 0.01]. Vertex 2 is the only junction.
    - Road A. Vertex 2 is a junction, so the walk cuts there: piece 1 -> 2, 1.112 km. At
      vertex 3, the new piece is 1.112 km long, so there is no cut. At vertex 4, it is
      2.224 km long, so the walk cuts there: piece 2 -> 4, 2.224 km, with the shape point
      [0, 0.02]. Vertex 5 is the last vertex: piece 4 -> 5, 1.112 km.
    - Road B. Vertex 6 is the last vertex: piece 2 -> 6, 1.112 km.
    The nodes are the vertices 1, 2, 4, 5 and 6. Vertex 3 is a shape point.

HOW THE PIECES BECOME A GRAPH
    1. A piece that starts and ends at the same node is dropped. Such an edge is never
       part of a shortest path.
    2. A piece of a two-way polyline gives an edge in each direction. A piece of a one-way
       polyline gives one edge. The reverse edge has the shape points in reverse order.
    3. The graph keeps one edge from a node to another node: the shortest one. Among edges
       of equal length, it keeps the first one.
    4. Each node gets an "index": its position in the lists that describe the graph,
       from 0. The indexes follow a Hilbert curve (`scgraph.helpers.hilbert`). Nodes
       that are close on the globe then get close indexes. `SnapIndex`, which finds the
       node closest to a point, needs this order. Two nodes at the same position on the
       curve are ordered by their point, then by their id. Thus the indexes do not
       depend on the order of the polylines.
    Example, with the roads above. The nodes get the indexes 0 to 4, in this order: the
    vertices 1, 2, 6, 4 and 5. The graph has seven edges: 0 <-> 1 (1.112 km), 1 <-> 3
    (2.224 km, with the shape point [0, 0.02]), 3 <-> 4 (1.112 km), and 1 -> 2 (1.112 km,
    one way).
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
    Cut each polyline into pieces, as *How a polyline is cut* in the module docstring
    says.

    Args:
        polylines: Pairs `(direction, vertices)`. `direction` is 1 for one way along the
            vertices, -1 for one way against them, and 0 for both ways. `vertices` is a
            list of pairs `(id, point)`.
        junctions: The ids of the vertices where polylines meet.
        max_km_between_nodes: The length in kilometers at which a piece ends, at the
            next vertex.

    Yields:
        `(origin_id, destination_id, km, direction, shape)` for each piece, in the order
        of the polylines. `km` is the length of the piece along the polyline. `shape` is
        the list of its shape points, empty if it has none. `direction` is the direction
        of its polyline. The origin and the destination can be the same vertex.
    """
    for direction, vertices in polylines:
        start, km = 0, 0.0
        for i in range(1, len(vertices)):
            km += haversine(vertices[i - 1][1], vertices[i][1])
            if (
                i == len(vertices) - 1
                or vertices[i][0] in junctions
                or km >= max_km_between_nodes
            ):
                shape = [point for _, point in vertices[start + 1 : i]]
                yield vertices[start][0], vertices[i][0], km, direction, shape
                start, km = i, 0.0


def build_graph_from_polylines(
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
    Build a graph from the pieces of `polylines`, as *How the pieces become a graph* in
    the module docstring says.

    Args:
        polylines: As in `cut_polylines`.
        junctions: As in `cut_polylines`.
        max_km_between_nodes: As in `cut_polylines`.

    Returns:
        `(graph, nodes, shapes, node_ids)`, where `i` and `j` are node indexes. `graph[i]`
        maps each node `j` that an edge from node `i` reaches to the length of that edge,
        in kilometers. `nodes[i]` is the point of node `i`. `shapes[i][j]` is the list of
        shape points of the edge from `i` to `j`, if the edge has any. `node_ids[i]` is the
        id of the vertex that became node `i`.
    """
    edges = {}  # (origin id, destination id) -> (km, shape)
    points = {}  # id of a node -> its point
    for polyline in polylines:
        vertex_points = dict(polyline[1])
        for origin_id, destination_id, km, direction, shape in cut_polylines(
            [polyline], junctions, max_km_between_nodes
        ):
            # 1. Drop a loop
            if origin_id == destination_id:
                continue
            points[origin_id] = vertex_points[origin_id]
            points[destination_id] = vertex_points[destination_id]
            # 2. One edge for each direction of travel. 3. Keep the shortest.
            if direction >= 0:
                _keep_shortest(edges, (origin_id, destination_id), km, shape)
            if direction <= 0:
                _keep_shortest(
                    edges, (destination_id, origin_id), km, shape[::-1]
                )

    # 4. Give each node its index, along the Hilbert curve
    node_ids = sorted(
        points,
        key=lambda node_id: (
            hilbert_key(*points[node_id]),
            *points[node_id],
            node_id,
        ),
    )
    node_index = {node_id: i for i, node_id in enumerate(node_ids)}
    graph = [{} for _ in node_ids]
    shapes = [{} for _ in node_ids]
    for (origin_id, destination_id), (km, shape) in edges.items():
        graph[node_index[origin_id]][node_index[destination_id]] = km
        if shape:
            shapes[node_index[origin_id]][node_index[destination_id]] = shape
    return graph, [points[node_id] for node_id in node_ids], shapes, node_ids


def _keep_shortest(edges, key, km, shape):
    if key not in edges or km < edges[key][0]:
        edges[key] = (km, shape)
