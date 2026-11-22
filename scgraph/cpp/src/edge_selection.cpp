// The selection of the edges of some node modes is explained in edge_selection.hpp. Read it first.
#include "edge_selection.hpp"
#include <stdexcept>

namespace {

// Adds the positions first to last - 1 to `runs`. They extend the last run when they start
// where it ends.
void add_run(Runs& runs, int64_t first, int64_t last) {
    if (first == last) return;
    if (!runs.empty() && runs.back().second == first) {
        runs.back().second = last;
    } else {
        runs.emplace_back(first, last);
    }
}

}  // namespace

EdgeSelection select_edges(std::span<const int32_t> offsets, std::span<const int32_t> heads,
                         std::span<const uint8_t> node_mode_ids,
                         const std::vector<bool>& is_node_mode_kept,
                         std::span<const int32_t> shape_offsets) {
    const int64_t node_count = (int64_t)offsets.size() - 1;
    const int64_t edge_count = (int64_t)heads.size();
    const size_t mode_count = is_node_mode_kept.size();
    const bool has_shapes = !shape_offsets.empty();
    if (node_count < 0 || (int64_t)node_mode_ids.size() != node_count) {
        throw std::invalid_argument("one node mode per node expected");
    }
    if (has_shapes && (int64_t)shape_offsets.size() != edge_count + 1) {
        throw std::invalid_argument("invalid shape offsets");
    }

    // 1. Find the nodes of each node mode
    std::vector<int64_t> first_node(mode_count + 1, 0);
    for (int64_t node = 0; node < node_count; ++node) {
        const uint8_t mode = node_mode_ids[node];
        if (mode >= mode_count || (node > 0 && mode < node_mode_ids[node - 1])) {
            throw std::invalid_argument("unsorted or unknown node modes");
        }
        ++first_node[mode + 1];
    }
    for (size_t mode = 0; mode < mode_count; ++mode) first_node[mode + 1] += first_node[mode];

    // The steps fill local vectors, and the result takes them at the end. Step 3 is slower
    // when it fills the fields of the result directly.
    Runs node_runs, edge_runs, shape_point_runs;
    std::vector<int32_t> new_offsets, new_heads, new_shape_offsets;

    // 2. Give their positions to the kept nodes
    std::vector<int64_t> shift(mode_count, 0);
    int64_t kept_nodes = 0;
    // The edges of the kept nodes: no selection keeps more edges
    int64_t most_edges = 0;
    for (size_t mode = 0; mode < mode_count; ++mode) {
        if (!is_node_mode_kept[mode]) continue;
        const int64_t first = first_node[mode], last = first_node[mode + 1];
        // Step 3 uses the offsets of these nodes as positions in `heads`
        if (offsets[first] < 0 || offsets[last] > edge_count) throw std::invalid_argument("invalid offsets");
        for (int64_t node = first; node < last; ++node) {
            if (offsets[node] > offsets[node + 1]) throw std::invalid_argument("invalid offsets");
        }
        add_run(node_runs, first, last);
        shift[mode] = kept_nodes - first;
        kept_nodes += last - first;
        most_edges += offsets[last] - offsets[first];
    }

    // 3. Visit the edges of each kept node
    new_offsets.reserve(kept_nodes + 1);
    new_offsets.push_back(0);
    new_heads.reserve(most_edges);
    int64_t kept_shape_points = 0;
    if (has_shapes) {
        new_shape_offsets.reserve(most_edges + 1);
        new_shape_offsets.push_back(0);
    }
    for (const auto& [first, last] : node_runs) {
        for (int64_t node = first; node < last; ++node) {
            for (int64_t edge = offsets[node]; edge < offsets[node + 1]; ++edge) {
                const int32_t head = heads[edge];
                if (head < 0 || head >= node_count) throw std::invalid_argument("edge to a missing node");
                const uint8_t mode = node_mode_ids[head];
                if (!is_node_mode_kept[mode]) continue;
                new_heads.push_back((int32_t)(head + shift[mode]));
                add_run(edge_runs, edge, edge + 1);
                if (!has_shapes) continue;
                const int32_t first_point = shape_offsets[edge], last_point = shape_offsets[edge + 1];
                if (first_point < 0 || first_point > last_point || last_point > shape_offsets[edge_count]) {
                    throw std::invalid_argument("invalid shape offsets");
                }
                add_run(shape_point_runs, first_point, last_point);
                kept_shape_points += last_point - first_point;
                // The offsets of a damaged file can count a shape point twice
                if (kept_shape_points > INT32_MAX) throw std::invalid_argument("invalid shape offsets");
                new_shape_offsets.push_back((int32_t)kept_shape_points);
            }
            new_offsets.push_back((int32_t)new_heads.size());
        }
    }
    return {std::move(new_offsets), std::move(new_heads), std::move(new_shape_offsets),
            std::move(node_runs), std::move(edge_runs), std::move(shape_point_runs)};
}
