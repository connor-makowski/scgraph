#pragma once
#include <cstdint>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>

// find_pareto_paths finds every best trade-off between two places of a network, for two
// metrics or more: hours and euros, for example. GeoGraph.get_pareto_paths calls it.
//
// WHAT IT ANSWERS
//   A path "dominates" another path when its total is not above the other's in any
//   metric, and below it in one metric at least. A "Pareto path" is a path that no other
//   path dominates. The totals of the Pareto paths form the "Pareto front".
//   find_pareto_paths returns every Pareto path from a set of origin nodes to a set of
//   destination nodes, with its total in each metric. The paths are sorted by their total
//   of the first metric, then of the second, and so on. Of several paths with the same
//   totals, it returns one.
//   Example, used in every part: four nodes and six edges, with two metrics, hours and
//   euros.
//     edge     hours  euros
//     0 -> 1   0.5    5
//     0 -> 2   3      3
//     0 -> 3   10     1
//     1 -> 2   2      2
//     1 -> 3   0.5    5
//     2 -> 3   3      3
//   From node 0 to node 3, the paths are A = 0-1-3 (1 hour, 10 euros), B = 0-2-3 (6, 6),
//   C = 0-3 (10, 1) and D = 0-1-2-3 (5.5, 10). A dominates D. A, B and C are the Pareto
//   paths, returned in this order.
//   No weighted sum of the two metrics finds B: for any coefficient c, the score
//   c * hours + euros of A or of C is below the score of B. A search by a weighted sum
//   finds only the Pareto paths on the convex hull of the front: the line of straight
//   segments that joins some points of the front and has every other point above it.
//
// HOW THE DATA IS STORED
//   - The network: the edges by origin, read in place. The edges of the node u have the
//     ids node_first_edge_ids[u] to node_first_edge_ids[u + 1] - 1, and
//     edge_destination_node_ids[e] is the node that the edge e goes to. Each metric is one
//     float64 array of weights by edge id; infinity closes an edge. Below, k is the count
//     of metrics (metric_count in the code). The kernel copies the weights into one array
//     with the k weights of each edge together, so that the search reads an edge at one
//     place.
//   - The "lower bound" of a node in a metric: the smallest total of this metric from the
//     node to a destination node. lower_bounds[v * k + i] holds it for the node v and the
//     metric i.
//     Example: the lower bounds of node 0 are (1, 1), of node 1 (0.5, 5), of node 2 (3, 3)
//     and of node 3 (0, 0).
//   - A "label" is a path from an origin node to a node, with its total in each metric. A
//     label is stored in arrays by label id: its node, the id of the label before it on
//     the path (its predecessor) and its k totals. The "key" of a label in a metric is its
//     total plus the lower bound of its node: no path that continues the label has a
//     smaller total. The kernel computes the keys when it needs them, and does not store
//     them.
//     Example: the label of the path 0-1 has the totals (0.5, 5) and the keys (1, 10).
//   - The queue holds the ids of the labels to take, smallest keys first: the keys are
//     compared in the order of the metrics, then the label ids.
//   - A label taken from the queue and kept is "permanent". For each node, the kernel keeps
//     the totals of its permanent labels, except their first total. It keeps the totals
//     of the Pareto paths found so far in the same way.
//
// HOW A RUN GOES
//   1. Run Dijkstra's algorithm once for each metric, on the reversed edges, from every
//      destination node. This gives the lower bounds. A path through a node that some
//      search does not reach cannot end at a destination: the kernel creates no label there.
//   2. Put one label at each origin node, with zero totals.
//   3. Take the label with the smallest keys from the queue. Drop it if a permanent label
//      of its node dominates it, or has the same totals. Drop it also if a Pareto path
//      found so far has a total not above its key in every metric (see the tolerance
//      below). Otherwise, the label becomes permanent.
//   4. A permanent label at a destination node is a Pareto path. Stop when max_paths paths
//      are found.
//   5. Otherwise, extend the label along each edge of its node, in the order of the edge
//      ids. Drop a new label at once with the rules of step 3. Put the others in the queue.
//      Stop with label_limit_error when the search has made more than max_labels labels.
//   6. When the queue is empty, rebuild each path from the predecessors of its label.
//   Example: the run from node 0 to node 3, with (hours, euros).
//     step  label taken           keys       result
//     1     node 0, (0, 0)        (1, 1)     permanent; adds node 1 (0.5, 5), node 2
//                                            (3, 3) and node 3 (10, 1)
//     2     node 1, (0.5, 5)      (1, 10)    permanent; adds node 2 (2.5, 7) and
//                                            node 3 (1, 10)
//     3     node 3, (1, 10)       (1, 10)    path A
//     4     node 2, (2.5, 7)      (5.5, 10)  dropped: A has 10 euros, not above 10
//     5     node 2, (3, 3)        (6, 6)     permanent; adds node 3 (6, 6)
//     6     node 3, (6, 6)        (6, 6)     path B
//     7     node 3, (10, 1)       (10, 1)    path C; the queue is empty
//
// WHY THE RESULT IS RIGHT
//   - A lower bound is never above the real rest of a path, and the lower bound of a node
//     is at most the weight of an edge plus the lower bound at its end: each one comes
//     from an exact search. So a label that extends another has keys not below the keys
//     of the other, and the queue gives the labels of each node in the order of their
//     totals. A label taken later cannot dominate a permanent label of the same node.
//   - A label dropped at its node: a permanent label of the node dominates it, or has its
//     totals. Each path that continues the dropped label is dominated by the same path
//     after the permanent label, or has its totals.
//     Example: no label of this run is dropped by this rule.
//   - A label dropped by a Pareto path P: each path that continues the label has totals
//     not below its keys, so P dominates it or has its totals.
//     Example: in step 4, each path through the label (2.5, 7) has at least 5.5 hours and
//     10 euros. A has 1 hour and 10 euros.
//   - The first total needs no test. A permanent label of the node, and a Pareto path
//     found so far, came from the queue first, so their first total is not above the one
//     of the new label. With two metrics, the second totals of the permanent labels of a
//     node decrease, so only the last one needs a test.
//     Example: in step 7, the found paths are A (1, 10) and B (6, 6). Only B is tested:
//     6 euros is above 1 euro, so C is kept.
//   - The Pareto paths reach the destination in the order of their totals, because the
//     lower bound of a destination node is 0. So max_paths keeps the paths with the
//     smallest totals of the first metric.
//
// THE TOLERANCE
//   With relative_tolerance t, a label is also dropped when a Pareto path found so far has
//   in each metric a total at most (1 + t) times the key of the label. Each Pareto path
//   then has a returned path within 1 + t of it in every metric. The tolerance is applied
//   against the returned paths only, never between two labels of a node, so its error does
//   not grow along a path.
//   Example: in step 5, the label (3, 3) with the keys (6, 6) is tested against A (1, 10).
//   With t = 0.5, A has 10 euros, above 1.5 * 6 = 9 euros, so the label stays and B is
//   returned. With t = 1, 10 euros is not above 2 * 6 = 12 euros, so the label is dropped:
//   the result is A and C.
//
// THE COST
//   The k searches of step 1 take O(k (m + n log n)) for n nodes and m edges. The search
//   takes O(L log L) for L labels, plus the tests of dominance: one comparison for two
//   metrics, and k - 1 comparisons for each permanent label of the node for more. A label
//   takes 8 k + 12 bytes, and 8 more bytes in the queue. The count of labels, not the
//   count of Pareto paths, sets the cost: a network with many paths of nearly the same
//   totals keeps many labels at its inner nodes. On a network of roads and of other edge
//   modes, each road node keeps the labels of many combinations of edge modes, and a path
//   across a continent makes tens of millions of labels. max_labels bounds this memory.
//
// THE SOURCES
//   The search is the label-setting algorithm of E. Q. V. Martins, "On a multicriteria
//   shortest path problem", European Journal of Operational Research 16(2), 1984. With one
//   metric, it is Dijkstra's algorithm. The keys with lower bounds come from NAMOA*: L.
//   Mandow and J. L. Perez de la Cruz, "Multiobjective A* search with consistent
//   heuristics", Journal of the ACM 57(5), 2010. The test without the first total is the
//   "t-discarding" of F.-J. Pulido, L. Mandow and J. L. Perez de la Cruz, "Dimensionality
//   reduction in multiobjective shortest path search", Computers & Operations Research,
//   2015. The test of one comparison for two metrics is that of BOA*: C. Hernandez, W.
//   Yeoh, J. A. Baier, H. Zhang, L. Suazo, S. Koenig and O. Salzman, "Simple and efficient
//   bi-objective search algorithms via fast dominance checks", Artificial Intelligence 314,
//   2023.
//
// THE PURE-PYTHON VERSION
//   scgraph.helpers.pareto_paths gives the same paths in the same order. Both versions
//   order the queue by the same keys and label ids, visit the edges in the same order, and
//   add the weights in the same order. This file is compiled without fused multiply-add
//   (CMakeLists.txt), so both versions compute the same doubles.
//   The arrays may come from a mapped file that nothing has checked. The kernel checks
//   them first, and throws std::invalid_argument with the message of the Python version.

// One Pareto path: the ids of its nodes, from the origin, and its total in each metric
using ParetoPath = std::pair<std::vector<int32_t>, std::vector<double>>;

// Thrown when the search makes more than max_labels labels. The binding raises it as a
// MemoryError, with its message.
struct label_limit_error : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// max_paths is the largest count of paths to return, and max_labels the largest count of
// labels that the search makes; 0 means no limit for each. The caller checks max_paths,
// relative_tolerance and max_labels. Throws std::invalid_argument for fewer than two
// metrics, for an array of a wrong length or with a wrong value, and for an origin or a
// destination that is not a node.
std::vector<ParetoPath> find_pareto_paths(std::span<const int32_t> node_first_edge_ids,
                                          std::span<const int32_t> edge_destination_node_ids,
                                          const std::vector<std::span<const double>>& weights_of_metrics,
                                          const std::vector<int64_t>& origin_node_ids,
                                          const std::vector<int64_t>& destination_node_ids,
                                          int64_t max_paths, double relative_tolerance, int64_t max_labels);
