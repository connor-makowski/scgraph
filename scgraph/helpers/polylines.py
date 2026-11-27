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
    `PieceArrays` stores the pieces of a large network as arrays.

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
       An edge has the class of its polyline, if the caller gave one.
    3. The graph keeps one edge from a node to another node: the shortest one, with its
       shape and its class. Among edges of equal length, it keeps the first one.
    4. Each node gets an "index": its position in the lists that describe the graph,
       from 0. The indexes follow a Hilbert curve (`scgraph.helpers.hilbert`). Nodes
       that are close on the globe then get close indexes. `OrderedSnapIndex`, which finds the
       node closest to a point, needs this order. Two nodes at the same position on the
       curve are ordered by their point, then by their id. Thus the indexes do not
       depend on the order of the polylines.
    Example, with the roads above. The nodes get the indexes 0 to 4, in this order: the
    vertices 1, 2, 6, 4 and 5. The graph has seven edges: 0 <-> 1 (1.112 km), 1 <-> 3
    (2.224 km, with the shape point [0, 0.02]), 3 <-> 4 (1.112 km), and 1 -> 2 (1.112 km,
    one way).
"""

import mmap
import os
from array import array
from collections.abc import Container, Hashable, Iterable, Iterator, Sequence

# The C++ kernel takes typed buffers only, so each call chooses its kernel.
try:
    from scgraph.cpp import simplify_shapes as _cpp_simplify_shapes
except ImportError:
    _cpp_simplify_shapes = None

from scgraph.helpers.douglas_peucker import (
    simplify_shapes as simplify_shapes_python,
)
from scgraph.helpers.hilbert import hilbert_key
from scgraph.coordinates import encode_coordinates
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
    list[dict[int, str]],
]:
    """
    Build a graph from the pieces of `polylines`, as *How the pieces become a graph* in
    the module docstring says.

    Args:
        polylines: As in `cut_polylines`. A polyline may have a third item, the name
            of its class: `(direction, vertices, class_name)`.
        junctions: As in `cut_polylines`.
        max_km_between_nodes: As in `cut_polylines`.

    Returns:
        `(graph, nodes, shapes, external_node_ids, edge_class_names)`, where `i` and `j`
        are node ids. `graph[i]` maps each node `j` that an edge from node `i` reaches
        to the length of that edge, in kilometers. `nodes[i]` is the point of node `i`.
        `shapes[i][j]` is the list of shape points of the edge from `i` to `j`, if the
        edge has any. `external_node_ids[i]` is the id of the vertex that became node `i`.
        `edge_class_names[i][j]` is the class of the edge from `i` to `j`, if its polyline
        has one.
    """
    edges = {}  # (origin id, destination id) -> (km, shape, class name)
    points = {}  # id of a node -> its point
    for polyline in polylines:
        class_name = polyline[2] if len(polyline) > 2 else None
        vertex_points = dict(polyline[1])
        for origin_id, destination_id, km, direction, shape in cut_polylines(
            [polyline[:2]], junctions, max_km_between_nodes
        ):
            # 1. Drop a loop
            if origin_id == destination_id:
                continue
            points[origin_id] = vertex_points[origin_id]
            points[destination_id] = vertex_points[destination_id]
            # 2. One edge for each direction of travel. 3. Keep the shortest.
            if direction >= 0:
                key = (origin_id, destination_id)
                _keep_shortest(edges, key, km, shape, class_name)
            if direction <= 0:
                key = (destination_id, origin_id)
                _keep_shortest(edges, key, km, shape[::-1], class_name)

    # 4. Give each node its id, along the Hilbert curve
    external_node_ids = sorted(
        points,
        key=lambda node_id: (
            hilbert_key(*points[node_id]),
            *points[node_id],
            node_id,
        ),
    )
    node_id_of_vertex = {
        node_id: i for i, node_id in enumerate(external_node_ids)
    }
    graph = [{} for _ in external_node_ids]
    shapes = [{} for _ in external_node_ids]
    edge_class_names = [{} for _ in external_node_ids]
    for (origin_id, destination_id), (km, shape, class_name) in edges.items():
        origin, destination = (
            node_id_of_vertex[origin_id],
            node_id_of_vertex[destination_id],
        )
        graph[origin][destination] = km
        if shape:
            shapes[origin][destination] = shape
        if class_name is not None:
            edge_class_names[origin][destination] = class_name
    nodes = [points[node_id] for node_id in external_node_ids]
    return graph, nodes, shapes, external_node_ids, edge_class_names


def _keep_shortest(edges, key, km, shape, class_name):
    if key not in edges or km < edges[key][0]:
        edges[key] = (km, shape, class_name)


def simplify_shapes(
    shape_points: array | memoryview,
    edge_first_shape_point_ids: array | memoryview,
    endpoint_coords: array | memoryview,
    tolerance_meters: float,
) -> tuple[array | memoryview, array | memoryview]:
    """Simplify the shape of each edge with the Douglas-Peucker algorithm.

    A shape point is dropped when it is within `tolerance_meters` of the line between the
    two kept points around it. Distances are measured on a flat map around each edge.

    Args:
        shape_points: The shape points of all the edges (int32 pairs, 1e-7 degree).
        edge_first_shape_point_ids: Where the points of each edge start.
        endpoint_coords: The latitude and the longitude of the two ends of each edge
            (int32, four values per edge).
        tolerance_meters: The tolerance, in meters.

    Returns:
        `(shape_points, edge_first_shape_point_ids)` of the simplified shapes.
    """
    if _cpp_simplify_shapes is not None and isinstance(
        shape_points, (array, memoryview)
    ):
        return _cpp_simplify_shapes(
            shape_points,
            edge_first_shape_point_ids,
            endpoint_coords,
            tolerance_meters,
        )
    return simplify_shapes_python(
        shape_points,
        edge_first_shape_point_ids,
        endpoint_coords,
        tolerance_meters,
    )


class PieceArrays:
    """The pieces of the cut ways, stored as arrays that grow.

    A piece is the part of a way between two consecutive nodes (`cut_polylines`). Entry
    `i` of each array describes piece `i`:

    - `origins`, `destinations` (int64): the ids of its two ends in the source;
    - `ends` (int32, four values per piece): the latitude and the longitude of its two
      ends, in units of 1e-7 degree;
    - `km` (float64): its length;
    - `directions` (int8): its direction, as in a polyline (1, -1 or 0);
    - `points` (int32 pairs) and `piece_first_shape_point_ids`: its shape points. The points of piece `i` are
      `points[2 * piece_first_shape_point_ids[i]:2 * piece_first_shape_point_ids[i + 1]]`;
    - `class_ids` (uint8): the id of its class in `scgraph.pipelines.CLASSES`. The
      array is empty when the pieces have no class;
    - `way_ids` (int64): the id of its way in the OpenStreetMap file, or 0 for a
      piece of no way. The array is empty when the pieces do not come from ways. A
      turn restriction names its ways by these ids.

    `flush` simplifies the shapes of the new pieces to within `tolerance_meters`
    (`simplify_shapes`) and stores them. `append` calls it every BATCH pieces.
    `tolerance_meters=None` stores the shapes as they are.

    Without `work_dir`, the arrays are `array`s in memory. With `work_dir`, each array
    is a file of that folder, read through a memory map. The arrays hold the pieces up to
    the last `flush`.
    """

    BATCH = 10_000
    COLUMNS = dict(origins="q", destinations="q", ends="i", km="d")
    COLUMNS.update(
        directions="b",
        points="i",
        piece_first_shape_point_ids="q",
        class_ids="B",
        way_ids="q",
    )

    def __init__(self, tolerance_meters=50, work_dir=None, truncate=True):
        self.tolerance_meters, self.work_dir = tolerance_meters, work_dir
        if work_dir is not None:
            os.makedirs(work_dir, exist_ok=True)
        for name, code in self.COLUMNS.items():
            path = (
                os.path.join(work_dir, name) if work_dir is not None else None
            )
            if (
                not truncate
                and path is not None
                and os.path.isfile(path)
                and os.path.getsize(path) > 0
            ):
                with open(path, "rb") as file:
                    view = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
                setattr(self, name, memoryview(view).cast(code))
            else:
                setattr(self, name, array(code))
                if work_dir is not None and truncate:
                    open(path, "wb").close()
        self._new = {name: array(code) for name, code in self.COLUMNS.items()}
        self._new["piece_first_shape_point_ids"].append(0)
        self._starts = [0]

    def append(
        self,
        origin_id: int,
        destination_id: int,
        length_km: float,
        direction: int,
        endpoint_coords: Iterable[Sequence[float]],
        shape_points: Iterable[Sequence[float]],
        class_id: int | None = None,
        way_id: int | None = None,
    ) -> None:
        """Add one piece. `endpoint_coords` and `shape_points` are `[latitude, longitude]`
        points in degrees. `class_id` is the id of the class of the piece in
        `scgraph.pipelines.CLASSES`. It is None for pieces without a class. `way_id`
        is the id of the way of the piece in the OpenStreetMap file. It is None for
        pieces that do not come from ways.
        """
        new = self._new
        new["origins"].append(origin_id)
        new["destinations"].append(destination_id)
        new["km"].append(length_km)
        new["directions"].append(direction)
        flat = [
            [x for point in points for x in point]
            for points in (endpoint_coords, shape_points)
        ]
        ends, points = encode_coordinates(flat, "int32")
        new["ends"].extend(ends)
        new["points"].extend(points)
        if class_id is not None:
            new["class_ids"].append(class_id)
        if way_id is not None:
            new["way_ids"].append(way_id)
        self._starts.append(len(new["points"]) // 2)
        if len(self._starts) > self.BATCH:
            self.flush()

    def flush(self) -> None:
        """Simplify and store the shapes of the pieces added since the last call."""
        new, starts = self._new, self._starts
        if self.tolerance_meters is not None:
            new["points"], starts = simplify_shapes(
                new["points"],
                array("i", starts),
                new["ends"],
                self.tolerance_meters,
            )
        stored = len(self.points) // 2
        new["piece_first_shape_point_ids"].extend(
            stored + start for start in starts[1:]
        )
        for name, column in new.items():
            if self.work_dir is None:
                getattr(self, name).extend(column)
                continue
            with open(os.path.join(self.work_dir, name), "ab+") as file:
                file.write(column)
                file.flush()
                if file.tell():
                    view = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
                    setattr(
                        self, name, memoryview(view).cast(self.COLUMNS[name])
                    )
        self._new = {name: array(code) for name, code in self.COLUMNS.items()}
        self._starts = [0]
