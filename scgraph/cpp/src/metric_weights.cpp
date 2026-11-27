// The two kernels that compute a metric are explained in metric_weights.hpp. Read it first.
#include "metric_weights.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <string>

// The one message of a refused weight, for the two kernels that refuse one
[[noreturn]] static void throw_refused_weight(int64_t origin_id, int64_t destination_id) {
    throw std::invalid_argument("The weight of the edge from node " + std::to_string(origin_id) +
                                " to node " + std::to_string(destination_id) +
                                " is below zero or not a number");
}

void check_edge_weights(std::span<const int32_t> node_first_edge_ids,
                        std::span<const int32_t> edge_destination_node_ids,
                        std::span<const double> weights) {
    if (weights.size() != edge_destination_node_ids.size()) {
        throw std::invalid_argument("expected one weight per edge");
    }
    for (size_t edge_id = 0; edge_id < weights.size(); ++edge_id) {
        if (is_refused_weight(weights[edge_id])) {
            // The origin is the last node whose first edge id is not above edge_id
            const int64_t origin_id =
                std::upper_bound(node_first_edge_ids.begin(), node_first_edge_ids.end(), (int64_t)edge_id) -
                node_first_edge_ids.begin() - 1;
            throw_refused_weight(origin_id, edge_destination_node_ids[edge_id]);
        }
    }
}

std::vector<double> compute_weights_from_km(
    std::span<const int32_t> node_first_edge_ids, std::span<const int32_t> edge_destination_node_ids, std::span<const double> lengths_km,
    std::span<const uint8_t> edge_class_ids, std::span<const uint8_t> node_mode_ids,
    std::span<const double> class_weights_per_km, std::span<const double> hub_weights) {
    constexpr double INFINITE = std::numeric_limits<double>::infinity();
    const int64_t node_count = (int64_t)node_first_edge_ids.size() - 1;
    const int64_t edge_count = (int64_t)edge_destination_node_ids.size();
    const size_t class_count = class_weights_per_km.size();
    if (node_count < 0 || (int64_t)node_mode_ids.size() != node_count ||
        (int64_t)lengths_km.size() != edge_count || (int64_t)edge_class_ids.size() != edge_count) {
        throw std::invalid_argument("expected one node mode per node, and one length and one class per edge");
    }
    if (class_count == 0 || hub_weights.size() % class_count != 0) {
        throw std::invalid_argument("expected one hub weight per node mode and per class");
    }
    const size_t node_mode_count = hub_weights.size() / class_count;
    for (uint8_t node_mode_id : node_mode_ids) {
        if (node_mode_id >= node_mode_count) {
            throw std::invalid_argument("an edge has a class without a weight per km, or a node has a node mode without hub weights");
        }
    }

    std::vector<double> weights(edge_count);
    for (int64_t origin_id = 0; origin_id < node_count; ++origin_id) {
        const int64_t first = node_first_edge_ids[origin_id], last = node_first_edge_ids[origin_id + 1];
        if (first < 0 || last < first || last > edge_count) throw std::invalid_argument("invalid node_first_edge_ids");
        const double* hub_weights_of_origin = hub_weights.data() + node_mode_ids[origin_id] * class_count;
        for (int64_t edge_id = first; edge_id < last; ++edge_id) {
            const size_t class_id = edge_class_ids[edge_id];
            const int32_t destination_id = edge_destination_node_ids[edge_id];
            if (class_id >= class_count) {
                throw std::invalid_argument("an edge has a class without a weight per km, or a node has a node mode without hub weights");
            }
            if (destination_id < 0 || destination_id >= node_count) throw std::invalid_argument("edge to a missing node");
            // 1. The weight per km of the class times the km, or infinity for a closed class
            const double weight_per_km = class_weights_per_km[class_id];
            double weight = weight_per_km == INFINITE ? INFINITE : weight_per_km * lengths_km[edge_id];
            // 2. The weight of the hub that the edge leaves
            const double weight_leaving_hub = hub_weights_of_origin[class_id];
            if (weight_leaving_hub != 0.0) weight += weight_leaving_hub;
            // 3. The weight of the hub that the edge enters
            const double weight_entering_hub = hub_weights[node_mode_ids[destination_id] * class_count + class_id];
            if (weight_entering_hub != 0.0) weight += weight_entering_hub;
            // 4. A weight below zero or not a number
            if (is_refused_weight(weight)) throw_refused_weight(origin_id, destination_id);
            weights[edge_id] = weight;
        }
    }
    return weights;
}

std::vector<double> compute_weighted_sum(const std::vector<std::span<const double>>& weights_of_metrics,
                                         std::span<const double> coefficients) {
    const size_t metric_count = weights_of_metrics.size();
    if (metric_count == 0 || coefficients.size() != metric_count) {
        throw std::invalid_argument("expected one coefficient per metric, and one metric at least");
    }
    const size_t edge_count = weights_of_metrics[0].size();
    for (const auto& weights : weights_of_metrics) {
        if (weights.size() != edge_count) throw std::invalid_argument("expected one weight per edge in each metric");
    }
    std::vector<double> sums(edge_count);
    for (size_t edge_id = 0; edge_id < edge_count; ++edge_id) {
        double sum = coefficients[0] * weights_of_metrics[0][edge_id];
        for (size_t k = 1; k < metric_count; ++k) {
            sum += coefficients[k] * weights_of_metrics[k][edge_id];
        }
        sums[edge_id] = sum;
    }
    return sums;
}
