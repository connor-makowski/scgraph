#pragma once
#include <cstdint>
#include <span>
#include <vector>

// The two kernels of this file compute a "metric" of a network: one weight for each edge,
// under a name such as `hours` or `cost`. GeoGraph.create_metric calls them, and a search
// then adds these weights in place of the lengths.
//
// WHAT THEY ANSWER
//   compute_weights_from_km gives the weight of each edge from its km, from a weight per km
//   for each class of edge, and from a weight at each hub. The weight of a hub is added
//   to an edge that leaves the hub, and to an edge that enters the hub.
//   compute_weighted_sum gives the weight of each edge as a sum of other metrics, each one
//   times a coefficient.
//   Both return one float64 value for each edge, in the order of the edges. An edge that no
//   route may take is "closed": its weight is infinity.
//   Example, used in every part: a network of three nodes. The node 0 is a road node, the
//   node 1 is a port and the node 2 is a sea node. A road connector of 3 km joins the nodes
//   0 and 1. A sea connector of 5 km joins the nodes 1 and 2. A truck drives at 50 km/h. It
//   waits 2 hours at the port, on its way in and on its way out. A ship sails at 25 km/h.
//   It needs 6 hours at the port, to enter it and to leave it.
//   The metric `hours` of the four edges is 0 -> 1: 2.06, 1 -> 0: 2.06, 1 -> 2: 6.2 and
//   2 -> 1: 6.2.
//
// WHAT THEY READ
//   The arrays of the network, in place. The kernels do not copy them.
//   - `node_first_edge_ids` and `edge_destination_ids` store the edges by origin. The edges of
//     the node u have the ids node_first_edge_ids[u] to node_first_edge_ids[u + 1] - 1, and
//     edge_destination_ids[e] is the node that the edge of id e goes to. The id of an edge is
//     its position in `edge_destination_ids`.
//   - `lengths_km` gives the km of each edge.
//   - `edge_class_ids` gives the "class" of each edge, as the id of the class: its position
//     in the list of the classes. A class is the category of an edge, such as motorway.
//   - `node_mode_ids` gives the "node mode" of each node, as the id of the node mode: its
//     position in the list of the node modes. The node mode of a node is the kind of place
//     where the node is: road, port, sea, and so on. A "hub" is a node whose node mode has
//     a weight in `hub_weights`.
//   Example: node_first_edge_ids = [0, 1, 3, 4], edge_destination_ids = [1, 0, 2, 1], lengths_km = [3, 3, 5, 5],
//   edge_class_ids = [0, 0, 1, 1] and node_mode_ids = [0, 1, 2]. The class 0 is the road
//   connector and the class 1 is the sea connector. The node mode 1 is the port.
//
// THE WEIGHTS PER KM AND THE HUB WEIGHTS
//   - `class_weights_per_km[c]` is the "weight per km" of the class c: the weight of 1 km of
//     an edge of this class. Infinity closes the class.
//   - `hub_weights[m * C + c]` is the weight that is added to an edge of the class c when
//     it leaves a node of the node mode m, and when it goes to a node of the node mode m.
//     C is the number of classes.
//   Example: class_weights_per_km = [0.02, 0.04], because 1 km takes 1 / 50 = 0.02 hour by
//   road and 1 / 25 = 0.04 hour by sea. With 3 node modes and 2 classes, `hub_weights` has 6
//   values: hub_weights = [0, 0, 2, 6, 0, 0]. Only the port, the node mode 1, has values.
//
// AN EDGE WITHOUT A CLASS
//   The class id 255 is the id of no class. The kernels have no rule for it: the caller
//   gives it a weight per km and hub weights, as to a class. GeoGraph.create_metric gives
//   C = 256 values, one for each value of a class id. class_weights_per_km[255] is the
//   weight of 1 km between a query point and its node, and hub_weights[m * 256 + 255] is
//   zero for every node mode m. A value that is the id of no class has a weight per km that
//   is not a number, so step 4 below refuses an edge with such an id.
//   Example: with the 2 classes above and 0.1 hour for 1 km off the graph,
//   class_weights_per_km holds 0.02, 0.04, then 253 values that are not a number, then 0.1.
//   The weight of an edge of 4 km without a class is 0.1 * 4 = 0.4 hour, also at the port.
//
// HOW A WEIGHT IS COMPUTED FROM THE KM
//   For the edge e of the class c, from the node u to the node v:
//   1. Start with the weight per km of the class times the km of the edge. For a closed
//      class, start with infinity. The kernel does not multiply an infinite weight per km by
//      a length, because infinity times 0 km is not a number.
//   2. Add hub_weights[node_mode_ids[u] * C + c], if it is not zero: the edge leaves a hub.
//   3. Add hub_weights[node_mode_ids[v] * C + c], if it is not zero: the edge enters a hub.
//   4. Refuse a weight that is below zero or not a number: a search needs weights of zero or
//      more. The kernel throws std::invalid_argument, and the message names u and v.
//   Example: the edge 0 -> 1 is a road connector of 3 km. Step 1 gives 0.02 * 3 = 0.06.
//   Step 2 adds nothing: the node 0 is a road node. Step 3 adds hub_weights[1 * 2 + 0] = 2.
//   The weight is 2.06 hours. The edge 1 -> 2 is a sea connector of 5 km: 0.04 * 5 = 0.2,
//   plus hub_weights[1 * 2 + 1] = 6 in step 2, is 6.2 hours.
//
// HOW A WEIGHTED SUM IS COMPUTED
//   `weights_of_metrics[k]` holds the weights of the metric k, and `coefficients[k]` is its
//   coefficient, a finite number above zero. The weight of the edge e is
//   coefficients[0] * weights_of_metrics[0][e], plus the same product of the metric 1, and
//   so on in the order of the metrics. An edge that is closed in one metric is closed in
//   the sum: a coefficient times infinity is infinity.
//   Example: `cost` is 30 times `hours` plus 0.5 times the length. For the edge 0 -> 1,
//   30 * 2.06 + 0.5 * 3 = 61.8 + 1.5 = 63.3.
//
// WHY BOTH BUILDS GIVE THE SAME WEIGHTS
//   scgraph.helpers.metric_weights holds the pure-Python version of the two kernels. Both
//   versions compute each weight in float64, with the same operations in the same order:
//   the steps 1, 2 and 3 above, and the sum in the order of the metrics. This file is
//   compiled without fused multiply-add (CMakeLists.txt), because a fused product and sum
//   rounds once where Python rounds twice. The two versions therefore return the same
//   arrays, bit for bit.
//   The arrays may come from a mapped file that nothing has checked. Each value is checked
//   before it is used as an id, so a damaged file throws std::invalid_argument and no memory
//   outside the arrays is read.

std::vector<double> compute_weights_from_km(
    std::span<const int32_t> node_first_edge_ids, std::span<const int32_t> edge_destination_ids,
    std::span<const double> lengths_km,
    std::span<const uint8_t> edge_class_ids, std::span<const uint8_t> node_mode_ids,
    std::span<const double> class_weights_per_km, std::span<const double> hub_weights);

std::vector<double> compute_weighted_sum(const std::vector<std::span<const double>>& weights_of_metrics,
                                         std::span<const double> coefficients);
