// The two kernels that compute a metric are explained in metric_weights.hpp. Read it first.
#include "metric_weights.hpp"
#include <limits>
#include <stdexcept>
#include <string>

std::vector<double> compute_table_weights(
    std::span<const int32_t> offsets, std::span<const int32_t> heads, std::span<const double> lengths,
    std::span<const uint8_t> edge_classes, std::span<const uint8_t> node_modes,
    std::span<const double> class_rates_per_km, std::span<const double> hub_weights) {
    constexpr double INFINITE = std::numeric_limits<double>::infinity();
    const int64_t node_count = (int64_t)offsets.size() - 1;
    const int64_t edge_count = (int64_t)heads.size();
    const size_t class_count = class_rates_per_km.size();
    if (node_count < 0 || (int64_t)node_modes.size() != node_count ||
        (int64_t)lengths.size() != edge_count || (int64_t)edge_classes.size() != edge_count) {
        throw std::invalid_argument("expected one mode per node, and one length and one class per edge");
    }
    if (class_count == 0 || hub_weights.size() % class_count != 0) {
        throw std::invalid_argument("expected one hub weight per mode and per class");
    }
    const size_t mode_count = hub_weights.size() / class_count;
    for (uint8_t mode : node_modes) {
        if (mode >= mode_count) {
            throw std::invalid_argument("an edge has a class, or a node has a mode, that the tables do not hold");
        }
    }

    std::vector<double> weights(edge_count);
    for (int64_t origin = 0; origin < node_count; ++origin) {
        const int64_t first = offsets[origin], last = offsets[origin + 1];
        if (first < 0 || last < first || last > edge_count) throw std::invalid_argument("invalid offsets");
        const double* weights_at_origin = hub_weights.data() + node_modes[origin] * class_count;
        for (int64_t edge = first; edge < last; ++edge) {
            const size_t edge_class = edge_classes[edge];
            const int32_t head = heads[edge];
            if (edge_class >= class_count) {
                throw std::invalid_argument("an edge has a class, or a node has a mode, that the tables do not hold");
            }
            if (head < 0 || head >= node_count) throw std::invalid_argument("edge to a missing node");
            // 1. The rate of the class times the km, or infinity for a closed class
            const double rate = class_rates_per_km[edge_class];
            double weight = rate == INFINITE ? INFINITE : rate * lengths[edge];
            // 2. The weight of the hub that the edge leaves
            const double out_weight = weights_at_origin[edge_class];
            if (out_weight != 0.0) weight += out_weight;
            // 3. The weight of the hub that the edge enters
            const double into_weight = hub_weights[node_modes[head] * class_count + edge_class];
            if (into_weight != 0.0) weight += into_weight;
            // 4. A comparison with a value that is not a number is false
            if (!(weight >= 0.0)) {
                throw std::invalid_argument("The weight of the edge from node " + std::to_string(origin) +
                                            " to node " + std::to_string(head) +
                                            " is below zero or not a number");
            }
            weights[edge] = weight;
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
    for (size_t edge = 0; edge < edge_count; ++edge) {
        double sum = coefficients[0] * weights_of_metrics[0][edge];
        for (size_t k = 1; k < metric_count; ++k) {
            sum += coefficients[k] * weights_of_metrics[k][edge];
        }
        sums[edge] = sum;
    }
    return sums;
}
