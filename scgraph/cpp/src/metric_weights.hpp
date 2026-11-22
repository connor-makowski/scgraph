#pragma once
#include <cstdint>
#include <span>
#include <vector>

// The two kernels of this file compute a "metric" of a network: one weight for each edge,
// under a name such as `hours` or `cost`. GeoGraph.create_metric calls them, and a search
// then adds up these weights in place of the lengths.
//
// WHAT THEY ANSWER
//   compute_weights_from_rates gives the weight of each edge from a rate for each class of
//   edge, and from a weight at each hub. An edge pays the weight of a hub when it leaves
//   the hub, and when it enters the hub.
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
//   - `offsets` and `heads` store the edges by origin: the edges of the node u are at the
//     positions offsets[u] to offsets[u + 1] - 1, and heads[e] is the node that the edge e
//     goes to.
//   - `lengths` gives the km of each edge.
//   - `edge_classes` gives the "class" of each edge, as a row of the classes table. A
//     class is the category of an edge: motorway, sea connector, and so on.
//   - `node_modes` gives the "mode" of each node, as a row of the modes table: road, port,
//     sea, and so on. A "hub" is a node whose mode has a weight in `hub_weights`.
//   Example: offsets = [0, 1, 3, 4], heads = [1, 0, 2, 1], lengths = [3, 3, 5, 5],
//   edge_classes = [0, 0, 1, 1] and node_modes = [0, 1, 2]. The class 0 is the road
//   connector and the class 1 is the sea connector. The mode 1 is the port.
//
// THE RATES AND THE HUB WEIGHTS
//   - `class_rates_per_km[c]` is the "rate" of the class c: the weight of 1 km of an edge of
//     this class. Infinity closes the class.
//   - `hub_weights[m * C + c]` is the weight that an edge of the class c pays when it leaves
//     a node of the mode m, and when it goes to a node of the mode m. C is the number of
//     classes.
//   Example: class_rates_per_km = [0.02, 0.04], because 1 km takes 1 / 50 = 0.02 hour by
//   road and 1 / 25 = 0.04 hour by sea. With 3 modes and 2 classes, `hub_weights` has 6
//   values: hub_weights = [0, 0, 2, 6, 0, 0]. Only the port, the mode 1, has values.
//
// HOW A WEIGHT IS COMPUTED FROM RATES
//   For the edge e of the class c, from the node u to the node v:
//   1. Start with the rate of the class times the km of the edge. For a closed class, start
//      with infinity. The kernel does not multiply an infinite rate by a length, because
//      infinity times 0 km is not a number.
//   2. Add hub_weights[node_modes[u] * C + c], if it is not zero: the edge leaves a hub.
//   3. Add hub_weights[node_modes[v] * C + c], if it is not zero: the edge enters a hub.
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
//   before it is used as a position, so a damaged file throws std::invalid_argument and no
//   memory outside the arrays is read.

std::vector<double> compute_weights_from_rates(
    std::span<const int32_t> offsets, std::span<const int32_t> heads, std::span<const double> lengths,
    std::span<const uint8_t> edge_classes, std::span<const uint8_t> node_modes,
    std::span<const double> class_rates_per_km, std::span<const double> hub_weights);

std::vector<double> compute_weighted_sum(const std::vector<std::span<const double>>& weights_of_metrics,
                                         std::span<const double> coefficients);
