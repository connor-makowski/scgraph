// The search for every Pareto path is explained in pareto_paths.hpp. Read it first.
#include "pareto_paths.hpp"
#include <algorithm>
#include <deque>
#include <functional>
#include <limits>
#include <queue>
#include <stdexcept>
#include <string>

namespace {

constexpr double INFINITE = std::numeric_limits<double>::infinity();

// Whether a point of `front` is not above `last_totals` times `tolerance_factor` in any
// metric after the first. `front` holds the last `total_count` totals of each point, point
// after point, in the order of their first total. With two metrics, the last point decides.
bool is_dominated(const std::vector<double>& front, const double* last_totals, size_t total_count,
                  double tolerance_factor) {
    if (front.empty()) return false;
    if (total_count == 1) return front.back() <= last_totals[0] * tolerance_factor;
    for (size_t first_total_id = 0; first_total_id < front.size(); first_total_id += total_count) {
        size_t total_id = 0;
        while (total_id < total_count && front[first_total_id + total_id] <= last_totals[total_id] * tolerance_factor) {
            ++total_id;
        }
        if (total_id == total_count) return true;
    }
    return false;
}

// Step 1 for one metric: Dijkstra's algorithm on the reversed edges, from every destination
// node at 0. Writes the smallest total from each node to a destination, or infinity, at
// lower_bounds[node * metric_count + metric_id].
void find_distances_to_destinations(const std::vector<int64_t>& destination_node_ids, std::span<const double> weights,
                                    const std::vector<int64_t>& reverse_first_edge_ids,
                                    const std::vector<int32_t>& reverse_edge_ids,
                                    const std::vector<int32_t>& edge_origin_node_ids, size_t metric_count,
                                    size_t metric_id, std::vector<double>& lower_bounds) {
    const size_t node_count = reverse_first_edge_ids.size() - 1;
    std::vector<double> distances(node_count, INFINITE);
    using Entry = std::pair<double, int32_t>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
    for (int64_t node_id : destination_node_ids) {
        distances[node_id] = 0.0;
        queue.emplace(0.0, (int32_t)node_id);
    }
    while (!queue.empty()) {
        const auto [distance, node_id] = queue.top();
        queue.pop();
        if (distance > distances[node_id]) continue;
        for (int64_t reverse_id = reverse_first_edge_ids[node_id]; reverse_id < reverse_first_edge_ids[node_id + 1]; ++reverse_id) {
            const int32_t edge_id = reverse_edge_ids[reverse_id];
            const int32_t origin_id = edge_origin_node_ids[edge_id];
            const double next_distance = distance + weights[edge_id];
            if (next_distance < distances[origin_id]) {
                distances[origin_id] = next_distance;
                queue.emplace(next_distance, origin_id);
            }
        }
    }
    for (size_t node_id = 0; node_id < node_count; ++node_id) {
        lower_bounds[node_id * metric_count + metric_id] = distances[node_id];
    }
}

}  // namespace

std::vector<ParetoPath> find_pareto_paths(std::span<const int32_t> node_first_edge_ids,
                                          std::span<const int32_t> edge_destination_node_ids,
                                          const std::vector<std::span<const double>>& weights_of_metrics,
                                          const std::vector<int64_t>& origin_node_ids,
                                          const std::vector<int64_t>& destination_node_ids,
                                          int64_t max_paths, double relative_tolerance, int64_t max_labels) {
    const int64_t node_count = (int64_t)node_first_edge_ids.size() - 1;
    const size_t edge_count = edge_destination_node_ids.size();
    const size_t metric_count = weights_of_metrics.size();
    // The checks of the Python version, in the same order and with the same messages. The
    // caller checks max_paths, relative_tolerance and max_labels
    if (metric_count < 2) throw std::invalid_argument("expected two metrics at least, and one weight per edge");
    for (const auto& weights : weights_of_metrics) {
        if (weights.size() != edge_count) throw std::invalid_argument("expected two metrics at least, and one weight per edge");
    }
    if (node_count < 0 || node_first_edge_ids[0] != 0 || (size_t)node_first_edge_ids[node_count] != edge_count) {
        throw std::invalid_argument("invalid node_first_edge_ids");
    }
    for (int64_t node_id = 0; node_id < node_count; ++node_id) {
        if (node_first_edge_ids[node_id + 1] < node_first_edge_ids[node_id]) throw std::invalid_argument("invalid node_first_edge_ids");
    }
    for (int32_t node_id : edge_destination_node_ids) {
        if (node_id < 0 || node_id >= node_count) throw std::invalid_argument("edge to a missing node");
    }
    for (const auto* node_ids : {&origin_node_ids, &destination_node_ids}) {
        for (int64_t node_id : *node_ids) {
            if (node_id < 0 || node_id >= node_count) throw std::invalid_argument("an origin or a destination id is not a node");
        }
    }

    // 1. The lower bound of each node in each metric, from the edges sorted by the node that
    // they go to, then by edge id
    std::vector<int32_t> edge_origin_node_ids(edge_count), reverse_edge_ids(edge_count);
    std::vector<int64_t> reverse_first_edge_ids(node_count + 1, 0);
    for (int64_t node_id = 0; node_id < node_count; ++node_id) {
        for (int32_t edge_id = node_first_edge_ids[node_id]; edge_id < node_first_edge_ids[node_id + 1]; ++edge_id) {
            edge_origin_node_ids[edge_id] = (int32_t)node_id;
        }
    }
    for (int32_t node_id : edge_destination_node_ids) ++reverse_first_edge_ids[node_id + 1];
    for (int64_t node_id = 0; node_id < node_count; ++node_id) reverse_first_edge_ids[node_id + 1] += reverse_first_edge_ids[node_id];
    std::vector<int64_t> next_reverse_ids(reverse_first_edge_ids.begin(), reverse_first_edge_ids.end() - 1);
    for (size_t edge_id = 0; edge_id < edge_count; ++edge_id) {
        reverse_edge_ids[next_reverse_ids[edge_destination_node_ids[edge_id]]++] = (int32_t)edge_id;
    }
    std::vector<double> lower_bounds(node_count * metric_count);
    for (size_t metric_id = 0; metric_id < metric_count; ++metric_id) {
        find_distances_to_destinations(destination_node_ids, weights_of_metrics[metric_id], reverse_first_edge_ids,
                                       reverse_edge_ids, edge_origin_node_ids, metric_count, metric_id, lower_bounds);
    }
    // The weights of each edge together, one for each metric
    std::vector<double> edge_weights(edge_count * metric_count);
    for (size_t edge_id = 0; edge_id < edge_count; ++edge_id) {
        for (size_t metric_id = 0; metric_id < metric_count; ++metric_id) {
            edge_weights[edge_id * metric_count + metric_id] = weights_of_metrics[metric_id][edge_id];
        }
    }

    // The labels, by label id, and the queue, smallest keys first, then the smallest id. The
    // comparison computes the keys again from the totals: the same sums give the same doubles,
    // and a label takes 8 bytes less for each metric. A deque grows without a copy of the labels.
    std::deque<int32_t> label_node_ids;
    std::deque<int64_t> label_predecessor_ids;
    std::deque<double> label_totals;
    auto comes_after = [&](int64_t label_id, int64_t other_id) {
        const double* node_lower_bounds = &lower_bounds[label_node_ids[label_id] * metric_count];
        const double* other_lower_bounds = &lower_bounds[label_node_ids[other_id] * metric_count];
        for (size_t metric_id = 0; metric_id < metric_count; ++metric_id) {
            const double key = label_totals[label_id * metric_count + metric_id] + node_lower_bounds[metric_id];
            const double other_key = label_totals[other_id * metric_count + metric_id] + other_lower_bounds[metric_id];
            if (key != other_key) return key > other_key;
        }
        return label_id > other_id;
    };
    std::priority_queue<int64_t, std::vector<int64_t>, decltype(comes_after)> queue(comes_after);
    auto add_label = [&](int32_t node_id, int64_t predecessor_id, const double* totals) {
        label_node_ids.push_back(node_id);
        label_predecessor_ids.push_back(predecessor_id);
        label_totals.insert(label_totals.end(), totals, totals + metric_count);
        queue.push((int64_t)label_node_ids.size() - 1);
        if (max_labels > 0 && (int64_t)label_node_ids.size() > max_labels) {
            throw label_limit_error("the search made more than max_labels=" + std::to_string(max_labels) + " labels");
        }
    };

    // 2. One label at each origin node, with zero totals
    const std::vector<double> zero_totals(metric_count, 0.0);
    for (int64_t node_id : origin_node_ids) {
        const double* keys = &lower_bounds[node_id * metric_count];
        bool is_reached = true;
        for (size_t metric_id = 0; metric_id < metric_count; ++metric_id) is_reached = is_reached && keys[metric_id] != INFINITE;
        if (is_reached) add_label((int32_t)node_id, -1, zero_totals.data());
    }

    // 3. to 5. Take the smallest keys, make the label permanent, extend it
    std::vector<char> is_destination(node_count, 0);
    for (int64_t node_id : destination_node_ids) is_destination[node_id] = 1;
    const double tolerance_factor = 1.0 + relative_tolerance;
    // The totals of the permanent labels of each node, and of the found paths, without their
    // first total
    std::vector<std::vector<double>> permanent_totals(node_count);
    std::vector<double> found_totals;
    std::vector<int64_t> found_label_ids;
    std::vector<double> totals(metric_count), keys(metric_count), next_totals(metric_count), next_keys(metric_count);
    while (!queue.empty()) {
        const int64_t label_id = queue.top();
        queue.pop();
        const int32_t node_id = label_node_ids[label_id];
        for (size_t metric_id = 0; metric_id < metric_count; ++metric_id) {
            totals[metric_id] = label_totals[label_id * metric_count + metric_id];
            keys[metric_id] = totals[metric_id] + lower_bounds[node_id * metric_count + metric_id];
        }
        std::vector<double>& front = permanent_totals[node_id];
        if (is_dominated(front, &totals[1], metric_count - 1, 1.0)) continue;
        if (is_dominated(found_totals, &keys[1], metric_count - 1, tolerance_factor)) continue;
        front.insert(front.end(), totals.begin() + 1, totals.end());
        if (is_destination[node_id]) {
            found_label_ids.push_back(label_id);
            found_totals.insert(found_totals.end(), totals.begin() + 1, totals.end());
            if ((int64_t)found_label_ids.size() == max_paths) break;
            continue;
        }
        for (int32_t edge_id = node_first_edge_ids[node_id]; edge_id < node_first_edge_ids[node_id + 1]; ++edge_id) {
            const int32_t next_node_id = edge_destination_node_ids[edge_id];
            bool is_open = true;
            for (size_t metric_id = 0; metric_id < metric_count; ++metric_id) {
                next_totals[metric_id] = totals[metric_id] + edge_weights[edge_id * metric_count + metric_id];
                next_keys[metric_id] = next_totals[metric_id] + lower_bounds[next_node_id * metric_count + metric_id];
                is_open = is_open && next_keys[metric_id] != INFINITE;
            }
            // A closed edge, or a node from which no path reaches a destination
            if (!is_open) continue;
            if (is_dominated(permanent_totals[next_node_id], &next_totals[1], metric_count - 1, 1.0)) continue;
            if (is_dominated(found_totals, &next_keys[1], metric_count - 1, tolerance_factor)) continue;
            add_label(next_node_id, label_id, next_totals.data());
        }
    }

    // 6. The node ids of each path, from its predecessor labels
    std::vector<ParetoPath> paths;
    for (int64_t label_id : found_label_ids) {
        const auto first_total = label_totals.begin() + label_id * metric_count;
        ParetoPath path{{}, std::vector<double>(first_total, first_total + metric_count)};
        for (int64_t id = label_id; id != -1; id = label_predecessor_ids[id]) path.first.push_back(label_node_ids[id]);
        std::reverse(path.first.begin(), path.first.end());
        paths.push_back(std::move(path));
    }
    return paths;
}
