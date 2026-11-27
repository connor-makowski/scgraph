#pragma once
#include <cstdint>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>

// A network file stores the shape of a two-way road once. This file gives the two
// functions of that rule: remove_second_edge_shapes for a write, find_pair_shape for a read.
//
// WHAT THEY ANSWER
//   The "shape" of an edge is the list of its shape points: the points between its two
//   nodes. A "pair" is two edges u -> v and v -> u. A road that goes both ways is a pair,
//   and the shape of v -> u is often the shape of u -> v in the reverse order. The
//   "second edge" of such a pair is the edge whose origin id is the higher one. The file
//   stores no shape point for a second edge. A reader reads the shape of its pair
//   backwards.
//   remove_second_edge_shapes takes the shape of each edge and finds the second edges. It
//   returns the arrays of the file, without the shape points of the second edges.
//   find_pair_shape gives the shape points of the pair of one second edge.
//   Example, used in every part: a network near Le Havre. The node 1 is Le Havre and the
//   node 2 is Rouen. The edge 1, from Le Havre to Rouen, has the shape points
//   (49.53, 0.45) and (49.52, 0.80). The edge 4, from Rouen to Le Havre, has the same two
//   points in the reverse order. Its origin id, 2, is higher than 1, so the edge 4 is the
//   second edge of the pair.
//
// HOW THE SHAPES ARE STORED
//   - `node_first_edge_ids` and `edge_destination_node_ids` store the edges by origin. The
//     edges of the node u have the ids node_first_edge_ids[u] to node_first_edge_ids[u + 1] - 1.
//   - `shape_points` holds the latitude, then the longitude, of each shape point:
//     float64 degrees, or int32 units of 1e-7 degree.
//   - The shape of the edge e is the shape points edge_first_shape_point_ids[e] to
//     edge_first_shape_point_ids[e + 1] - 1.
//   - `edge_has_reversed_shape` holds one byte for each edge: 1 for a second edge, 0 for
//     any other edge. A second edge has no shape point of its own.
//   Example: the network has 6 nodes and 10 edges. node_first_edge_ids =
//   [0, 1, 4, 5, 6, 8, 10] and edge_destination_node_ids = [1, 2, 0, 5, 1, 4, 5, 3, 1, 4].
//   With the shape of each edge, edge_first_shape_point_ids =
//   [0, 0, 2, 2, 2, 4, 4, 4, 4, 4, 4], and shape_points holds 4 points. The file holds
//   edge_first_shape_point_ids = [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2], 2 points, and
//   edge_has_reversed_shape = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0].
//
// HOW A WRITE RUNS
//   remove_second_edge_shapes visits each edge e, from u to v, in the order of the ids.
//   1. The edge e is a second edge if all of these are true:
//      - v is lower than u, so a loop u -> u is never a second edge;
//      - e has at least one shape point;
//      - the node v has exactly one edge to u, the "pair edge";
//      - the pair edge has the same number of points, and its point i is the point
//        count - 1 - i of e, for each i.
//   2. The function writes 1 or 0 in `edge_has_reversed_shape`. It copies the shape points
//      of e only if e is not a second edge. Then it writes the next first shape point id.
//   Example: the edge 4 goes from 2 to 1, and 1 is lower than 2. The node 1 has one
//   edge to the node 2, the edge 1. Its points, read backwards, are the points of the
//   edge 4. So the edge 4 is a second edge, and its two points are not copied.
//
// HOW A READ FINDS THE SHAPE OF A SECOND EDGE
//   find_pair_shape takes a second edge e, from u to v. It visits the edges of v and
//   stops at the first edge to u. It returns the range of the shape points of that edge.
//   The caller reads them from the last one to the first one.
//   Example: the edge 4 goes from 2 to 1. The edges of the node 1 are the edges 1 to 3.
//   The edge 1 goes to the node 2, and its range is (0, 2). The caller reads the point 1,
//   then the point 0: (49.52, 0.80), then (49.53, 0.45).
//
// WHY THE RESULT IS RIGHT
//   The pair edge of a second edge goes from a lower origin to a higher destination. So
//   it is never a second edge itself, and it keeps its shape points in the file.
//   A write flags an edge only if v has exactly one edge to u. So a read finds the right
//   pair edge, the first and only edge from v to u.
//   A load of some node modes keeps each edge whose two nodes it keeps. It keeps both
//   edges of a pair, or neither of them. So the pair edge of a kept second edge is kept.
//   A shape that differs from the shape of its pair edge is stored in full. Example: two
//   roads of different lengths between the same two nodes.
//   A damaged file or a mapped file that nothing has checked may give a flag to a wrong
//   edge. find_pair_shape then throws std::invalid_argument, for a second edge with shape
//   points of its own, and for a second edge without a pair edge that has shape points.
//
// THE PURE-PYTHON VERSION
//   helpers/second_edges.py has the same two functions, with the same results and the same
//   errors.

// The message of the error of a damaged second edge, the same in both versions
inline constexpr const char* SECOND_EDGE_ERROR =
    "invalid edge_has_reversed_shape: a second edge has shape points, or no pair edge with shape points";

// The arrays of the shapes as a file stores them (see HOW THE SHAPES ARE STORED)
template <typename T>
struct StoredShapes {
    std::vector<int32_t> edge_first_shape_point_ids;
    std::vector<uint8_t> edge_has_reversed_shape;
    std::vector<T> shape_points;
};

// The range (first, last) of the shape points of the pair edge of the second edge
// `edge_id`, which goes from `origin_id`. The caller has checked `edge_id` and the length
// of `edge_first_shape_point_ids`.
inline std::pair<int64_t, int64_t> find_pair_shape(std::span<const int32_t> node_first_edge_ids,
                                                   std::span<const int32_t> edge_destination_node_ids,
                                                   std::span<const int32_t> edge_first_shape_point_ids,
                                                   int64_t origin_id, int64_t edge_id) {
    const int64_t node_count = (int64_t)node_first_edge_ids.size() - 1;
    const int64_t edge_count = (int64_t)edge_destination_node_ids.size();
    const int64_t destination_id = edge_destination_node_ids[edge_id];
    if (edge_first_shape_point_ids[edge_id] != edge_first_shape_point_ids[edge_id + 1] ||
        destination_id < 0 || destination_id >= node_count)
        throw std::invalid_argument(SECOND_EDGE_ERROR);
    const int64_t first_edge = node_first_edge_ids[destination_id];
    const int64_t last_edge = node_first_edge_ids[destination_id + 1];
    if (first_edge < 0 || first_edge > last_edge || last_edge > edge_count)
        throw std::invalid_argument("invalid node_first_edge_ids");
    for (int64_t pair_edge_id = first_edge; pair_edge_id < last_edge; ++pair_edge_id) {
        if (edge_destination_node_ids[pair_edge_id] != origin_id) continue;
        const int64_t first = edge_first_shape_point_ids[pair_edge_id];
        const int64_t last = edge_first_shape_point_ids[pair_edge_id + 1];
        if (first >= last) break;
        return {first, last};
    }
    throw std::invalid_argument(SECOND_EDGE_ERROR);
}

// The arrays of the shapes without the shape points of the second edges (see HOW A WRITE
// RUNS). The arrays hold the shape of each edge. network_file.write checks them first, as
// a read checks a file, so each id here is inside its array.
template <typename T>
StoredShapes<T> remove_second_edge_shapes(std::span<const int32_t> node_first_edge_ids,
                                          std::span<const int32_t> edge_destination_node_ids,
                                          std::span<const int32_t> edge_first_shape_point_ids,
                                          std::span<const T> shape_points) {
    const int64_t node_count = (int64_t)node_first_edge_ids.size() - 1;
    StoredShapes<T> stored;
    stored.edge_has_reversed_shape.assign(edge_destination_node_ids.size(), 0);
    stored.edge_first_shape_point_ids.reserve(edge_first_shape_point_ids.size());
    stored.edge_first_shape_point_ids.push_back(0);
    stored.shape_points.reserve(shape_points.size());
    // Step 1: whether the edge `edge_id` from `origin_id` is a second edge
    auto is_second_edge = [&](int64_t origin_id, int64_t edge_id) {
        const int64_t destination_id = edge_destination_node_ids[edge_id];
        const int64_t first = edge_first_shape_point_ids[edge_id];
        const int64_t count = edge_first_shape_point_ids[edge_id + 1] - first;
        if (destination_id >= origin_id || count == 0) return false;
        int64_t pair_edge_id = -1;
        for (int64_t e = node_first_edge_ids[destination_id]; e < node_first_edge_ids[destination_id + 1]; ++e) {
            if (edge_destination_node_ids[e] != origin_id) continue;
            if (pair_edge_id >= 0) return false;  // two edges from v to u
            pair_edge_id = e;
        }
        if (pair_edge_id < 0) return false;
        const int64_t pair_first = edge_first_shape_point_ids[pair_edge_id];
        if (edge_first_shape_point_ids[pair_edge_id + 1] - pair_first != count) return false;
        for (int64_t i = 0; i < count; ++i) {
            const int64_t point = first + i, pair_point = pair_first + count - 1 - i;
            if (shape_points[2 * point] != shape_points[2 * pair_point] ||
                shape_points[2 * point + 1] != shape_points[2 * pair_point + 1])
                return false;
        }
        return true;
    };
    // Step 2: the flag, the kept shape points and the first shape point ids
    for (int64_t origin_id = 0; origin_id < node_count; ++origin_id) {
        for (int64_t edge_id = node_first_edge_ids[origin_id]; edge_id < node_first_edge_ids[origin_id + 1]; ++edge_id) {
            if (is_second_edge(origin_id, edge_id)) {
                stored.edge_has_reversed_shape[edge_id] = 1;
            } else {
                stored.shape_points.insert(stored.shape_points.end(),
                                           shape_points.begin() + 2 * edge_first_shape_point_ids[edge_id],
                                           shape_points.begin() + 2 * edge_first_shape_point_ids[edge_id + 1]);
            }
            stored.edge_first_shape_point_ids.push_back((int32_t)(stored.shape_points.size() / 2));
        }
    }
    return stored;
}
