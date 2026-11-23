#pragma once
#include <cstdint>
#include <span>
#include <utility>
#include <vector>

// select_edges prepares the load of some node modes of a network file. It finds the nodes and
// the edges that the load keeps, and it gives the place of each one in the smaller network.
//
// WHAT IT ANSWERS
//   The "node mode" of a node is the kind of place where the node is: road, rail, port, and
//   so on. A load of some node modes keeps the nodes of these node modes, the "kept nodes".
//   It keeps the edges whose origin and whose destination are both kept nodes, the "kept edges". The
//   kept nodes and the kept edges stay in the order of the file. They are the "selection".
//   The "position" of a node, of an edge or of a shape point is its rank in the arrays: the
//   first one has the position 0. Each has a position in the file, and each kept one has a
//   position in the selection.
//   Example, used in every part: a file of five nodes. The nodes 0 and 1 are road nodes
//   (node mode 0), the node 2 is a port (node mode 1), the nodes 3 and 4 are sea nodes (node
//   mode 2). The edges are 0 -> 1, 1 -> 0, 1 -> 2, 2 -> 3, 3 -> 4, 4 -> 2 and 4 -> 3, at the
//   positions 0 to 6. A load of the road and of the sea keeps the nodes 0, 1, 3 and 4. In the
//   selection, they have the positions 0, 1, 2 and 3. The load keeps the edges 0 -> 1,
//   1 -> 0, 3 -> 4 and 4 -> 3. It drops the three edges that leave or reach the port.
//
// WHAT IT READS
//   The arrays of the file, in place. The function does not copy them.
//   - `node_first_edge_ids` and `edge_destination_ids` store the edges by origin. The edges of
//     the node u are at the positions node_first_edge_ids[u] to node_first_edge_ids[u + 1] - 1,
//     and edge_destination_ids[a] is the destination id of the edge a.
//   - `node_mode_ids` gives the node mode of each node. Its values do not decrease: the nodes
//     of one node mode are consecutive.
//   - `is_node_mode_kept` is true for each node mode of the file that the load keeps.
//   - `edge_first_shape_point_ids` is empty for a file without edge shapes. In a file with shapes, the
//     shape of the edge a is the shape points at the positions edge_first_shape_point_ids[a] to
//     edge_first_shape_point_ids[a + 1] - 1.
//   Example: node_first_edge_ids = [0, 1, 3, 4, 5, 7], edge_destination_ids = [1, 0, 2, 3, 4, 2, 3],
//   node_mode_ids = [0, 0, 1, 2, 2], is_node_mode_kept = [true, false, true] and
//   edge_first_shape_point_ids = [0, 1, 3, 5, 7, 7, 8, 9]. The shape of the edge 1 is the shape points
//   1 and 2. The edge 4 has no shape point.
//
// WHAT IT RETURNS
//   An EdgeSelection, in two parts.
//   - Three new arrays, for the values that change. `node_first_edge_ids` and `edge_first_shape_point_ids` count
//     kept edges and kept shape points. `edge_destination_ids` gives each destination id as a position in the
//     selection.
//   - Three lists of "runs", for the arrays whose values do not change: the points, the
//     ids and the node modes of the nodes, the weights and the classes of the edges, the
//     shape points. A run (first, last) is a range of consecutive positions of the file, from
//     first to last - 1, that the load keeps. A run that starts where the run before it
//     ends is joined to it. The caller takes the runs from an array of the file. When
//     there is one run, the caller can read it in place, without a copy.
//   Example: the selection of the road and of the sea has node_first_edge_ids = [0, 1, 2, 3, 4],
//   edge_destination_ids = [1, 0, 3, 2] and edge_first_shape_point_ids = [0, 1, 3, 3, 4]. Its node runs are (0, 2)
//   and (3, 5). Its edge runs are (0, 2), (4, 5) and (6, 7): the weights of the selection
//   are the weights 0, 1, 4 and 6 of the file. Its shape point runs are (0, 3) and (8, 9).
//   Example: a load of the road alone has one node run, (0, 2), one edge run, (0, 2), and
//   one shape point run, (0, 3). The caller reads every array of the road in place.
//
// HOW IT RUNS
//   1. Find the nodes of each node mode. One pass over `node_mode_ids` counts the nodes of
//      each node mode. The first node of a node mode is the number of nodes of the node modes
//      before it.
//   2. Give their positions to the kept nodes. For each kept node mode, in the order of the
//      file, add its nodes to the node runs. Compute the "shift" of the node mode: the
//      position of its first node in the selection, minus the position of that node in the
//      file.
//   3. Visit the edges of each kept node, in the order of the file. An edge is kept when the
//      node mode of its destination is kept. For a kept edge, write the destination id plus the shift of the
//      node mode of the destination id, add the position of the edge to the edge runs, and add the
//      positions of its shape points to the shape point runs. After the edges of a node,
//      write the number of kept edges so far as the next first edge id.
//   Example: step 1 finds that the road starts at the node 0, the port at the node 2 and
//   the sea at the node 3. Step 2 gives the shift 0 to the road and the shift -1 to the
//   sea: the sea follows 2 kept nodes, and it starts at the position 3 of the file. Step 3
//   drops the edge 1 -> 2, because the port is not kept. It keeps the edge 3 -> 4 and writes
//   the destination id 4 - 1 = 3.
//
// WHY THE RESULT IS RIGHT
//   The nodes of a kept node mode are consecutive in the file, and they are all kept. They
//   are consecutive in the selection too. One shift therefore moves every node of the node
//   mode to its position in the selection.
//   Example: the sea nodes are at the positions 3 and 4 of the file, and at the positions 2
//   and 3 of the selection. The shift -1 is right for both.
//   The visit follows the order of the file. The kept edges of a node are written together,
//   in their order, and the values of `node_first_edge_ids` written after each node delimit them.
//   The arrays may come from a mapped file that nothing has checked. Each value is checked
//   before it is used as a position, so a damaged file throws std::invalid_argument and
//   no memory outside the arrays is read. The caller checks the lengths of the other
//   arrays, and that the last value of edge_first_shape_point_ids is the number of shape points of the file.
//   Example: with edge_destination_ids = [1, 0, 9, 3, 4, 2, 3], a load of the road throws at the edge 2,
//   because the file has no node 9.

// A list of runs. The run (first, last) holds the positions first to last - 1.
using Runs = std::vector<std::pair<int64_t, int64_t>>;

struct EdgeSelection {
    // The kept edges of the node at the position u of the selection are at the positions
    // node_first_edge_ids[u] to node_first_edge_ids[u + 1] - 1 of the selection
    std::vector<int32_t> node_first_edge_ids;
    // The destination id of each kept edge, as a position in the selection
    std::vector<int32_t> edge_destination_ids;
    // The shape of each kept edge, as positions in the kept shape points; empty for a file
    // without shapes
    std::vector<int32_t> edge_first_shape_point_ids;
    // The positions in the file of the kept nodes, of the kept edges and of their shape points
    Runs node_runs;
    Runs edge_runs;
    Runs shape_point_runs;
};

EdgeSelection select_edges(std::span<const int32_t> node_first_edge_ids, std::span<const int32_t> edge_destination_ids,
                         std::span<const uint8_t> node_mode_ids,
                         const std::vector<bool>& is_node_mode_kept,
                         std::span<const int32_t> edge_first_shape_point_ids);
