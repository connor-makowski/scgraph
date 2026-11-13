#include <queue>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <tuple>
#include <limits>
#include <iostream>
#include "graph.hpp"
#include "bmssp.hpp"

// Constructor
Graph::Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate) {
    const int n = (int)graph_data.size();
    std::vector<int32_t> offsets(n + 1, 0);
    for (int i = 0; i < n; ++i) {
        if (offsets[i] + graph_data[i].size() > INT32_MAX) {
            throw std::length_error("a graph holds at most 2^31 - 1 arcs");
        }
        offsets[i + 1] = offsets[i] + (int32_t)graph_data[i].size();
    }
    std::vector<int32_t> heads;
    std::vector<double> weights;
    heads.reserve(offsets[n]);
    weights.reserve(offsets[n]);
    for (size_t i = 0; i < graph_data.size(); ++i) {
        for (const auto& [node, weight] : graph_data[i]) {
            // An edge to a node outside the graph would be indexed out of bounds
            // by every algorithm (undefined behaviour, a crash in reduce()); the
            // check is cheap here, where every edge is copied anyway. With
            // validate=True, validate() reports it with its own message.
            if (!validate && (node < 0 || node >= n)) {
                throw std::out_of_range(
                    "Destination id " + std::to_string(node) + " at origin " +
                    std::to_string(i) + " is not in the graph");
            }
            heads.push_back(node);
            weights.push_back(weight);
        }
    }
    this->set_graph(CsrGraph(std::move(offsets), std::move(heads), std::move(weights)));
    this->reset_cache();
    if (validate) {
        this->validate();
    }
}

void Graph::load_csr(const int32_t* offsets, const int32_t* heads, const double* weights, int n, int64_t m,
                     std::shared_ptr<const void> owner) {
    if (n < 0 || offsets[0] != 0 || offsets[n] != m) {
        throw std::invalid_argument("offsets must start at 0 and end at the number of arcs");
    }
    // Offsets first: heads are read only within [0, m)
    for (int u = 0; u < n; ++u) {
        if (offsets[u] > offsets[u + 1]) {
            throw std::invalid_argument("offsets must be non-decreasing");
        }
    }
    for (int u = 0; u < n; ++u) {
        for (int32_t j = offsets[u]; j < offsets[u + 1]; ++j) {
            if (heads[j] < 0 || heads[j] >= n) {
                throw std::out_of_range(
                    "Destination id " + std::to_string(heads[j]) + " at origin " +
                    std::to_string(u) + " is not in the graph");
            }
        }
    }
    if (owner) {
        this->set_graph(CsrGraph(std::move(owner), offsets, heads, weights, n, m));
    } else {
        this->set_graph(CsrGraph(std::vector<int32_t>(offsets, offsets + n + 1),
                                  std::vector<int32_t>(heads, heads + m),
                                  std::vector<double>(weights, weights + m)));
    }
    this->reset_cache();
}

// Override reset_cache
void Graph::reset_cache() {
    GraphReducer::reset_cache();
    ch_graph_ = nullptr;
    tnr_graph_ = nullptr;
    bucket_width_cache_ = -1.0;
    reduced_bucket_width_cache_ = -1.0;
}

// Width of the buckets of dijkstra_buckets and bidirectional_buckets: the given width, else
// 8 times the median edge weight of the searched graph (1 if that median is 0), and never so
// small that a bucket ring would exceed 2^16 + 1 buckets. Same rule as
// GraphUtils._get_bucket_width in graph_utils.py
double Graph::resolve_bucket_width(const CsrGraph& g,
                                   std::optional<double> bucket_width, double max_weight) {
    double width;
    if (bucket_width.has_value()) {
        width = bucket_width.value();
        if (!(std::isfinite(width) && width > 0.0)) {
            throw std::invalid_argument("bucket_width must be a finite number greater than 0.");
        }
    } else {
        double& cache = (&g == &this->reduced_graph) ? reduced_bucket_width_cache_ : bucket_width_cache_;
        if (cache < 0.0) {
            std::vector<double> weights(g.all_weights().begin(), g.all_weights().end());
            double median = 0.0;
            if (!weights.empty()) {
                auto mid = weights.begin() + weights.size() / 2;
                std::nth_element(weights.begin(), mid, weights.end());
                median = *mid;
            }
            cache = median > 0.0 ? 8.0 * median : 1.0;
        }
        width = cache;
    }
    return std::max(width, std::ceil(max_weight) / 65536.0);
}

template <typename QueryFn>
GraphResult Graph::run_query_with_reducer(
    const NodeIdVariant& origin_id,
    const NodeIdVariant& destination_id,
    QueryFn&& query_fn,
    bool bidirectional
) {
    if (!has_reduced_graph) {
        return query_fn(this->graph(), origin_id, destination_id);
    }
    if (is_same_chain(origin_id, destination_id)) {
        return query_fn(this->graph(), origin_id, destination_id);
    }

    // Bidirectional searches must start and end on non-reduced nodes: only there
    // is reduced_inverse_graph exactly the reverse of reduced_graph. Their reduced
    // origins are replaced by the boundary nodes they reach (rows of
    // reduced_graph); reduced destinations are replaced below for every search.
    // One-sided searches keep a reduced origin: they only read reduced_graph.
    NodeIdVariant search_origin = origin_id;
    std::unordered_map<int, int> origin_map;
    auto origin_entries = get_node_entries(origin_id);
    bool any_reduced_origin = false;
    if (bidirectional) {
        for (const auto& [oid, _] : origin_entries) {
            if (oid >= 0 && oid < (int)is_reduced.size() && is_reduced[oid]) {
                any_reduced_origin = true;
                break;
            }
        }
    }
    if (any_reduced_origin) {
        std::unordered_map<int, double> boundary_origins;
        for (const auto& [oid, o_start] : origin_entries) {
            std::vector<std::pair<int, double>> exits;
            if (oid >= 0 && oid < (int)is_reduced.size() && is_reduced[oid]) {
                exits = reduced_graph[oid].to_vector();
            } else {
                exits.emplace_back(oid, 0.0);
            }
            for (const auto& [exit_u, exit_dist] : exits) {
                double total = o_start + exit_dist;
                auto it = boundary_origins.find(exit_u);
                if (it == boundary_origins.end() || total < it->second) {
                    boundary_origins[exit_u] = total;
                    origin_map[exit_u] = oid;
                }
            }
        }
        if (boundary_origins.empty()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }
        search_origin = boundary_origins;
    }
    auto restore_origin = [&origin_map](std::vector<int> path) {
        if (!path.empty()) {
            auto it = origin_map.find(path.front());
            if (it != origin_map.end() && it->second != path.front()) {
                path.insert(path.begin(), it->second);
            }
        }
        return path;
    };

    auto dest_entries = get_node_entries(destination_id);
    bool any_reduced = false;
    for (const auto& [did, _] : dest_entries) {
        if (did >= 0 && did < (int)is_reduced.size() && is_reduced[did]) {
            any_reduced = true;
            break;
        }
    }
    if (!any_reduced) {
        GraphResult res = query_fn(this->reduced_graph, search_origin, destination_id);
        res.path = expand_path(restore_origin(res.path));
        return res;
    }

    std::unordered_map<int, double> boundary_dests;
    std::unordered_map<int, std::pair<int, std::vector<int>>> boundary_reconstruct;

    for (const auto& [did, d_exit] : dest_entries) {
        if (did < 0 || did >= (int)is_reduced.size() || !is_reduced[did]) {
            if (boundary_dests.find(did) == boundary_dests.end() || d_exit < boundary_dests[did]) {
                boundary_dests[did] = d_exit;
                boundary_reconstruct[did] = {did, {}};
            }
        } else {
            const auto& entries = reduced_inverse_graph[did];
            for (const auto& [entry_u, entry_dist] : entries) {
                double total_exit = d_exit + entry_dist;
                if (boundary_dests.find(entry_u) == boundary_dests.end() || total_exit < boundary_dests[entry_u]) {
                    boundary_dests[entry_u] = total_exit;
                    boundary_reconstruct[entry_u] = {did, hidden_nodes(did, entry_u, true)};
                }
            }
        }
    }

    if (boundary_dests.empty()) {
        throw PathNotFoundException("The origin and destination nodes are not connected.");
    }

    GraphResult res = query_fn(this->reduced_graph, search_origin, boundary_dests);
    std::vector<int> expanded = expand_path(restore_origin(res.path));
    if (!res.path.empty()) {
        int meeting_bound = res.path.back();
        auto it = boundary_reconstruct.find(meeting_bound);
        if (it != boundary_reconstruct.end()) {
            int orig_did = it->second.first;
            const auto& conn = it->second.second;
            if (!conn.empty()) {
                expanded.insert(expanded.end(), conn.begin(), conn.end());
            }
            if (orig_did != meeting_bound) {
                expanded.push_back(orig_did);
            }
        }
    }
    res.path = expanded;
    return res;
}

// Tree algorithms
TreeData Graph::get_shortest_path_tree(const NodeIdVariant& origin_id) {
    input_check(origin_id, 0);
    return shortest_path_tree(this->graph(), origin_id);
}

TreeData Graph::shortest_path_tree(const CsrGraph& g,
                                   const NodeIdVariant& origin_id) const {
    auto origin_entries = get_node_entries(origin_id);

    const size_t n = g.size();
    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessors(n, -1);

    using PQElement = std::pair<double, int>;
    std::priority_queue<PQElement, std::vector<PQElement>, std::greater<>> open_leaves;

    for (const auto& [oid, odist] : origin_entries) {
        distance_matrix[oid] = odist;
        open_leaves.emplace(odist, oid);
    }

    while (!open_leaves.empty()) {
        auto [current_distance, current_id] = open_leaves.top();
        open_leaves.pop();

        if (current_distance > distance_matrix[current_id]) continue;

        for (const auto& [connected_id, connected_distance] : g[current_id]) {
            const double possible_distance = current_distance + connected_distance;
            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessors[connected_id] = current_id;
                open_leaves.emplace(possible_distance, connected_id);
            }
        }
    }

    return TreeData{origin_id, predecessors, distance_matrix};
}

GraphResult Graph::get_tree_path(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, const TreeData& tree_data, bool length_only) {
    auto origin_entries = get_node_entries(origin_id);
    auto tree_origin_entries = get_node_entries(tree_data.origin_id);

    double start_dist = 0.0;
    if (tree_origin_entries.size() == 1) {
        int tree_root = tree_origin_entries[0].first;
        bool found = false;
        for (const auto& [oid, odist] : origin_entries) {
            if (oid == tree_root) {
                start_dist = odist - tree_origin_entries[0].second;
                found = true;
                break;
            }
        }
        if (!found) {
            throw std::runtime_error("The origin node must be the same as the spanning node for this function to work.");
        }
    }

    auto dest_entries = get_node_entries(destination_id);
    double best_dist = std::numeric_limits<double>::infinity();
    int best_target = -1;
    for (const auto& [did, ddist] : dest_entries) {
        if (tree_data.distance_matrix[did] != std::numeric_limits<double>::infinity()) {
            double tot = start_dist + tree_data.distance_matrix[did] + ddist;
            if (tot < best_dist) {
                best_dist = tot;
                best_target = did;
            }
        }
    }

    if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
        throw PathNotFoundException("The origin and destination nodes are not connected.");
    }

    if (length_only) {
        return GraphResult{{}, best_dist};
    }

    std::vector<int> current_path;
    int current_id = best_target;
    current_path.push_back(best_target);

    while (current_id != -1 && tree_data.predecessors[current_id] != -1) {
        current_id = tree_data.predecessors[current_id];
        current_path.push_back(current_id);
    }

    std::reverse(current_path.begin(), current_path.end());
    return GraphResult{current_path, best_dist};
}

namespace {
struct DijkstraNodeState {
    double dist;
    int pred;
    uint32_t stamp = 0;
};

thread_local std::vector<DijkstraNodeState> tl_dijkstra_state;
thread_local uint32_t tl_dijkstra_stamp = 0;
thread_local std::vector<std::pair<double, int>> tl_dijkstra_open;

struct AStarNodeState {
    double dist;
    int pred;
    uint32_t stamp = 0;
};

// An entry of the A* queue. The queue gives the entry with the smallest key
// first; equal keys are ordered by distance, then by node, as in pure Python.
struct AStarQueueEntry {
    double key;       // distance from the origin plus heuristic of the node
    double distance;  // distance from the origin when the node was queued
    int node;

    bool operator>(const AStarQueueEntry& other) const {
        return std::tie(key, distance, node) > std::tie(other.key, other.distance, other.node);
    }
};

thread_local std::vector<AStarNodeState> tl_astar_state;
thread_local uint32_t tl_astar_stamp = 0;
thread_local std::vector<AStarQueueEntry> tl_astar_open;

struct BidirNodeState {
    double forward_dist;
    double backward_dist;
    int forward_pred;
    int backward_pred;
    uint32_t forward_stamp = 0;
    uint32_t backward_stamp = 0;
};

thread_local std::vector<BidirNodeState> tl_bidir_state;
thread_local uint32_t tl_bidir_stamp = 0;
thread_local std::vector<std::pair<double, int>> tl_bidir_forward_open;
thread_local std::vector<std::pair<double, int>> tl_bidir_backward_open;

// The number of node scans of the last search in this thread. A search that counts its
// node scans writes it once, at its end. reset_node_scans empties it
thread_local std::optional<size_t> tl_node_scans;
}

void reset_node_scans() {
    tl_node_scans.reset();
}

std::optional<size_t> get_last_node_scans() {
    return tl_node_scans;
}

// Shortest path algorithms
GraphResult Graph::dijkstra(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id) {
    input_check(origin_id, destination_id);

    auto run_dijkstra = [this](const CsrGraph& g,
                               const NodeIdVariant& orig,
                               const NodeIdVariant& dest) -> GraphResult {
        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);
        std::unordered_map<int, double> dest_map;
        for (const auto& [did, ddist] : dest_entries) {
            dest_map[did] = ddist;
        }

        const size_t n = g.size();
        if (tl_dijkstra_state.size() < n) {
            tl_dijkstra_state.resize(n);
        }

        tl_dijkstra_stamp++;
        if (tl_dijkstra_stamp == 0) {
            std::fill(tl_dijkstra_state.begin(), tl_dijkstra_state.end(), DijkstraNodeState{});
            tl_dijkstra_stamp = 1;
        }
        const uint32_t stamp = tl_dijkstra_stamp;
        auto* state = tl_dijkstra_state.data();

        auto& open_leaves = tl_dijkstra_open;
        open_leaves.clear();
        const std::greater<> compare;

        double best_dist = std::numeric_limits<double>::infinity();
        int best_target = -1;

        for (const auto& [oid, odist] : origin_entries) {
            state[oid].dist = odist;
            state[oid].pred = -1;
            state[oid].stamp = stamp;
            open_leaves.emplace_back(odist, oid);
            std::push_heap(open_leaves.begin(), open_leaves.end(), compare);

            auto it = dest_map.find(oid);
            if (it != dest_map.end()) {
                double direct = odist + it->second;
                if (direct < best_dist) {
                    best_dist = direct;
                    best_target = oid;
                }
            }
        }

        size_t node_scans = 0;
        while (!open_leaves.empty()) {
            std::pop_heap(open_leaves.begin(), open_leaves.end(), compare);
            auto [current_distance, current_id] = open_leaves.back();
            open_leaves.pop_back();

            if (state[current_id].stamp == stamp && current_distance > state[current_id].dist) continue;
            if (current_distance >= best_dist) break;

            ++node_scans;
            for (const auto& [connected_id, connected_distance] : g[current_id]) {
                const double possible_distance = current_distance + connected_distance;
                if (state[connected_id].stamp != stamp || possible_distance < state[connected_id].dist) {
                    state[connected_id].dist = possible_distance;
                    state[connected_id].pred = current_id;
                    state[connected_id].stamp = stamp;
                    open_leaves.emplace_back(possible_distance, connected_id);
                    std::push_heap(open_leaves.begin(), open_leaves.end(), compare);

                    auto it = dest_map.find(connected_id);
                    if (it != dest_map.end()) {
                        double total_d = possible_distance + it->second;
                        if (total_d < best_dist) {
                            best_dist = total_d;
                            best_target = connected_id;
                        }
                    }
                }
            }
        }

        tl_node_scans = node_scans;
        if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        std::vector<int> output_path;
        int curr = best_target;
        output_path.push_back(curr);
        while (state[curr].stamp == stamp && state[curr].pred != -1) {
            curr = state[curr].pred;
            output_path.push_back(curr);
        }
        std::reverse(output_path.begin(), output_path.end());

        return GraphResult{
            output_path,
            best_dist
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_dijkstra);
}

GraphResult Graph::bidirectional_dijkstra(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id) {
    input_check(origin_id, destination_id);

    auto run_bidir = [this](
        const CsrGraph& fwd_g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        bool is_reduced_g = (&fwd_g == &this->reduced_graph);
        const auto& inv_g = is_reduced_g ? this->reduced_inverse_graph : (this->ensure_inverse_graph(), this->inverse_graph);

        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);
        std::unordered_map<int, double> orig_map(origin_entries.begin(), origin_entries.end());
        std::unordered_map<int, double> dest_map(dest_entries.begin(), dest_entries.end());

        const size_t n = fwd_g.size();
        if (tl_bidir_state.size() < n) {
            tl_bidir_state.resize(n);
        }

        tl_bidir_stamp++;
        if (tl_bidir_stamp == 0) {
            std::fill(tl_bidir_state.begin(), tl_bidir_state.end(), BidirNodeState{});
            tl_bidir_stamp = 1;
        }
        const uint32_t stamp = tl_bidir_stamp;
        auto* state = tl_bidir_state.data();

        auto& forward_open = tl_bidir_forward_open;
        auto& backward_open = tl_bidir_backward_open;
        forward_open.clear();
        backward_open.clear();
        const std::greater<> compare;

        double best_dist = std::numeric_limits<double>::infinity();
        int meeting_node = -1;

        for (const auto& [oid, odist] : origin_entries) {
            state[oid].forward_dist = odist;
            state[oid].forward_pred = -1;
            state[oid].forward_stamp = stamp;
            forward_open.emplace_back(odist, oid);
            std::push_heap(forward_open.begin(), forward_open.end(), compare);
        }

        for (const auto& [did, ddist] : dest_entries) {
            state[did].backward_dist = ddist;
            state[did].backward_pred = -1;
            state[did].backward_stamp = stamp;
            backward_open.emplace_back(ddist, did);
            std::push_heap(backward_open.begin(), backward_open.end(), compare);

            auto it = orig_map.find(did);
            if (it != orig_map.end()) {
                double cand = it->second + ddist;
                if (cand < best_dist) {
                    best_dist = cand;
                    meeting_node = did;
                }
            }
        }

        size_t node_scans = 0;
        while (!forward_open.empty() && !backward_open.empty()) {
            const double top_fwd = forward_open.front().first;
            const double top_bwd = backward_open.front().first;
            if (top_fwd + top_bwd >= best_dist) {
                break;
            }

            if (top_fwd <= top_bwd) {
                std::pop_heap(forward_open.begin(), forward_open.end(), compare);
                auto [cur_d, u] = forward_open.back();
                forward_open.pop_back();

                if (state[u].forward_stamp == stamp && cur_d == state[u].forward_dist) {
                    ++node_scans;
                    for (const auto& [v, w] : fwd_g[u]) {
                        const double new_d = cur_d + w;
                        if (state[v].forward_stamp != stamp || new_d < state[v].forward_dist) {
                            state[v].forward_dist = new_d;
                            state[v].forward_pred = u;
                            state[v].forward_stamp = stamp;
                            if (state[v].backward_stamp == stamp) {
                                const double total_d = new_d + state[v].backward_dist;
                                if (total_d < best_dist) {
                                    best_dist = total_d;
                                    meeting_node = v;
                                }
                            }
                            if (new_d + top_bwd < best_dist) {
                                forward_open.emplace_back(new_d, v);
                                std::push_heap(forward_open.begin(), forward_open.end(), compare);
                            }
                        }
                    }
                }
            } else {
                std::pop_heap(backward_open.begin(), backward_open.end(), compare);
                auto [cur_d, v] = backward_open.back();
                backward_open.pop_back();

                if (state[v].backward_stamp == stamp && cur_d == state[v].backward_dist) {
                    ++node_scans;
                    for (const auto& [u, w] : inv_g[v]) {
                        const double new_d = cur_d + w;
                        if (state[u].backward_stamp != stamp || new_d < state[u].backward_dist) {
                            state[u].backward_dist = new_d;
                            state[u].backward_pred = v;
                            state[u].backward_stamp = stamp;
                            if (state[u].forward_stamp == stamp) {
                                const double total_d = state[u].forward_dist + new_d;
                                if (total_d < best_dist) {
                                    best_dist = total_d;
                                    meeting_node = u;
                                }
                            }
                            if (new_d + top_fwd < best_dist) {
                                backward_open.emplace_back(new_d, u);
                                std::push_heap(backward_open.begin(), backward_open.end(), compare);
                            }
                        }
                    }
                }
            }
        }

        tl_node_scans = node_scans;
        if (meeting_node == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        std::vector<int> forward_path;
        int curr = meeting_node;
        while (curr != -1) {
            forward_path.push_back(curr);
            if (orig_map.find(curr) != orig_map.end() && (state[curr].forward_stamp != stamp || state[curr].forward_pred == -1)) {
                break;
            }
            curr = (state[curr].forward_stamp == stamp) ? state[curr].forward_pred : -1;
        }
        std::reverse(forward_path.begin(), forward_path.end());

        std::vector<int> backward_path;
        curr = meeting_node;
        while (curr != -1) {
            if (dest_map.find(curr) != dest_map.end() && (state[curr].backward_stamp != stamp || state[curr].backward_pred == -1)) {
                break;
            }
            curr = (state[curr].backward_stamp == stamp) ? state[curr].backward_pred : -1;
            if (curr != -1) {
                backward_path.push_back(curr);
            }
        }

        forward_path.insert(forward_path.end(), backward_path.begin(), backward_path.end());
        return GraphResult{forward_path, best_dist};
    };

    return run_query_with_reducer(origin_id, destination_id, run_bidir, true);
}

GraphResult Graph::dijkstra_buckets(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id,
                                     std::optional<double> max_edge_weight,
                                     std::optional<double> bucket_width) {
    input_check(origin_id, destination_id);

    auto run_buckets = [this, max_edge_weight, bucket_width](
        const CsrGraph& g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);
        std::unordered_map<int, double> dest_map(dest_entries.begin(), dest_entries.end());

        double max_weight = 0.0;
        if (max_edge_weight.has_value()) {
            max_weight = max_edge_weight.value();
        } else if (&g == &this->reduced_graph) {
            max_weight = this->reduced_max_edge_weight;
        } else {
            max_weight = this->get_max_edge_weight();
        }
        const double width = this->resolve_bucket_width(g, bucket_width, max_weight);
        int num_buckets = static_cast<int>(std::ceil(max_weight / width)) + 1;

        const size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> predecessor(n, -1);
        std::vector<std::vector<int>> buckets(num_buckets);

        int min_orig_dist = std::numeric_limits<int>::max();
        for (const auto& [oid, odist] : origin_entries) {
            distance_matrix[oid] = odist;
            int ob = static_cast<int>(odist / width);
            buckets[ob % num_buckets].push_back(oid);
            if (ob < min_orig_dist) {
                min_orig_dist = ob;
            }
        }

        int current_dist = origin_entries.empty() ? 0 : min_orig_dist;
        size_t nodes_in_buckets = origin_entries.size();

        double best_dist = std::numeric_limits<double>::infinity();
        int best_target = -1;

        for (const auto& [did, ddist] : dest_entries) {
            if (distance_matrix[did] != std::numeric_limits<double>::infinity()) {
                double direct = distance_matrix[did] + ddist;
                if (direct < best_dist) {
                    best_dist = direct;
                    best_target = did;
                }
            }
        }

        // The current bucket is relaxed as one batch; nodes re-inserted into it wait for the
        // next batch
        std::vector<int> batch;
        size_t node_scans = 0;
        while (nodes_in_buckets > 0) {
            int bucket_idx = current_dist % num_buckets;
            while (buckets[bucket_idx].empty()) {
                current_dist++;
                bucket_idx = current_dist % num_buckets;
                if (nodes_in_buckets == 0) break;
                if (best_dist < current_dist * width) break;
            }

            if (nodes_in_buckets == 0 || best_dist < current_dist * width) break;

            batch.swap(buckets[bucket_idx]);
            nodes_in_buckets -= batch.size();

            for (int current_id : batch) {
                if (static_cast<int>(distance_matrix[current_id] / width) < current_dist) {
                    continue;
                }

                ++node_scans;
                for (const auto& [connected_id, connected_distance] : g[current_id]) {
                    double possible_distance = distance_matrix[current_id] + connected_distance;
                    if (possible_distance < distance_matrix[connected_id]) {
                        distance_matrix[connected_id] = possible_distance;
                        predecessor[connected_id] = current_id;
                        buckets[static_cast<int>(possible_distance / width) % num_buckets].push_back(connected_id);
                        nodes_in_buckets++;

                        auto it = dest_map.find(connected_id);
                        if (it != dest_map.end()) {
                            double tot = possible_distance + it->second;
                            if (tot < best_dist) {
                                best_dist = tot;
                                best_target = connected_id;
                            }
                        }
                    }
                }
            }
            batch.clear();
        }

        tl_node_scans = node_scans;
        if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(best_target, predecessor),
            best_dist
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_buckets);
}

GraphResult Graph::bidirectional_buckets(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id,
                                         std::optional<double> max_edge_weight,
                                         std::optional<double> bucket_width) {
    input_check(origin_id, destination_id);

    auto run_bidir_buckets = [this, max_edge_weight, bucket_width](
        const CsrGraph& fwd_g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        bool is_reduced_g = (&fwd_g == &this->reduced_graph);
        const auto& inv_g = is_reduced_g ? this->reduced_inverse_graph : (this->ensure_inverse_graph(), this->inverse_graph);

        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);
        std::unordered_map<int, double> orig_map(origin_entries.begin(), origin_entries.end());
        std::unordered_map<int, double> dest_map(dest_entries.begin(), dest_entries.end());

        double max_weight = 0.0;
        if (max_edge_weight.has_value()) {
            max_weight = max_edge_weight.value();
        } else if (is_reduced_g) {
            max_weight = this->reduced_max_edge_weight;
        } else {
            max_weight = this->get_max_edge_weight();
        }
        const double width = this->resolve_bucket_width(fwd_g, bucket_width, max_weight);
        int num_buckets = static_cast<int>(std::ceil(max_weight / width)) + 1;

        const size_t n = fwd_g.size();
        if (tl_bidir_state.size() < n) {
            tl_bidir_state.resize(n);
        }

        tl_bidir_stamp++;
        if (tl_bidir_stamp == 0) {
            std::fill(tl_bidir_state.begin(), tl_bidir_state.end(), BidirNodeState{});
            tl_bidir_stamp = 1;
        }
        const uint32_t stamp = tl_bidir_stamp;
        auto* state = tl_bidir_state.data();

        std::vector<std::vector<int>> forward_buckets(num_buckets);
        std::vector<std::vector<int>> backward_buckets(num_buckets);

        double best_dist = std::numeric_limits<double>::infinity();
        int meeting_node = -1;

        int min_fwd = std::numeric_limits<int>::max();
        for (const auto& [oid, odist] : origin_entries) {
            state[oid].forward_dist = odist;
            state[oid].forward_pred = -1;
            state[oid].forward_stamp = stamp;
            int ob = static_cast<int>(odist / width);
            forward_buckets[ob % num_buckets].push_back(oid);
            if (ob < min_fwd) {
                min_fwd = ob;
            }
        }

        int min_bwd = std::numeric_limits<int>::max();
        for (const auto& [did, ddist] : dest_entries) {
            state[did].backward_dist = ddist;
            state[did].backward_pred = -1;
            state[did].backward_stamp = stamp;
            int db = static_cast<int>(ddist / width);
            backward_buckets[db % num_buckets].push_back(did);
            if (db < min_bwd) {
                min_bwd = db;
            }

            auto it = orig_map.find(did);
            if (it != orig_map.end()) {
                double cand = it->second + ddist;
                if (cand < best_dist) {
                    best_dist = cand;
                    meeting_node = did;
                }
            }
        }

        int fwd_current_dist = origin_entries.empty() ? 0 : min_fwd;
        int bwd_current_dist = dest_entries.empty() ? 0 : min_bwd;
        size_t fwd_nodes_in_buckets = origin_entries.size();
        size_t bwd_nodes_in_buckets = dest_entries.size();

        std::vector<int> batch;
        size_t node_scans = 0;
        while (fwd_nodes_in_buckets > 0 && bwd_nodes_in_buckets > 0) {
            int fwd_bucket_idx = fwd_current_dist % num_buckets;
            while (forward_buckets[fwd_bucket_idx].empty()) {
                fwd_current_dist++;
                fwd_bucket_idx = fwd_current_dist % num_buckets;
                if (fwd_nodes_in_buckets == 0) break;
                if ((fwd_current_dist + bwd_current_dist) * width >= best_dist) break;
            }

            int bwd_bucket_idx = bwd_current_dist % num_buckets;
            while (backward_buckets[bwd_bucket_idx].empty()) {
                bwd_current_dist++;
                bwd_bucket_idx = bwd_current_dist % num_buckets;
                if (bwd_nodes_in_buckets == 0) break;
                if ((fwd_current_dist + bwd_current_dist) * width >= best_dist) break;
            }

            if (fwd_nodes_in_buckets == 0 || bwd_nodes_in_buckets == 0 ||
                (fwd_current_dist + bwd_current_dist) * width >= best_dist) {
                break;
            }

            // The current bucket of the side with the lower cursor is relaxed as one batch;
            // nodes re-inserted into it wait for the next batch
            if (fwd_current_dist <= bwd_current_dist) {
                batch.swap(forward_buckets[fwd_bucket_idx]);
                fwd_nodes_in_buckets -= batch.size();

                for (int u : batch) {
                    if (state[u].forward_stamp == stamp && static_cast<int>(state[u].forward_dist / width) < fwd_current_dist) {
                        continue;
                    }

                    double cur_d = state[u].forward_dist;
                    ++node_scans;
                    for (const auto& [v, w] : fwd_g[u]) {
                        double new_d = cur_d + w;
                        if (state[v].forward_stamp != stamp || new_d < state[v].forward_dist) {
                            state[v].forward_dist = new_d;
                            state[v].forward_pred = u;
                            state[v].forward_stamp = stamp;
                            if (state[v].backward_stamp == stamp) {
                                double total_d = new_d + state[v].backward_dist;
                                if (total_d < best_dist) {
                                    best_dist = total_d;
                                    meeting_node = v;
                                }
                            }
                            if (new_d + bwd_current_dist * width < best_dist) {
                                forward_buckets[static_cast<int>(new_d / width) % num_buckets].push_back(v);
                                fwd_nodes_in_buckets++;
                            }
                        }
                    }
                }
            } else {
                batch.swap(backward_buckets[bwd_bucket_idx]);
                bwd_nodes_in_buckets -= batch.size();

                for (int v : batch) {
                    if (state[v].backward_stamp == stamp && static_cast<int>(state[v].backward_dist / width) < bwd_current_dist) {
                        continue;
                    }

                    double cur_d = state[v].backward_dist;
                    ++node_scans;
                    for (const auto& [u, w] : inv_g[v]) {
                        double new_d = cur_d + w;
                        if (state[u].backward_stamp != stamp || new_d < state[u].backward_dist) {
                            state[u].backward_dist = new_d;
                            state[u].backward_pred = v;
                            state[u].backward_stamp = stamp;
                            if (state[u].forward_stamp == stamp) {
                                double total_d = state[u].forward_dist + new_d;
                                if (total_d < best_dist) {
                                    best_dist = total_d;
                                    meeting_node = u;
                                }
                            }
                            if (new_d + fwd_current_dist * width < best_dist) {
                                backward_buckets[static_cast<int>(new_d / width) % num_buckets].push_back(u);
                                bwd_nodes_in_buckets++;
                            }
                        }
                    }
                }
            }
            batch.clear();
        }

        tl_node_scans = node_scans;
        if (meeting_node == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        std::vector<int> forward_path;
        int curr = meeting_node;
        while (curr != -1) {
            forward_path.push_back(curr);
            if (orig_map.find(curr) != orig_map.end() && (state[curr].forward_stamp != stamp || state[curr].forward_pred == -1)) {
                break;
            }
            curr = (state[curr].forward_stamp == stamp) ? state[curr].forward_pred : -1;
        }
        std::reverse(forward_path.begin(), forward_path.end());

        std::vector<int> backward_path;
        curr = meeting_node;
        while (curr != -1) {
            if (dest_map.find(curr) != dest_map.end() && (state[curr].backward_stamp != stamp || state[curr].backward_pred == -1)) {
                break;
            }
            curr = (state[curr].backward_stamp == stamp) ? state[curr].backward_pred : -1;
            if (curr != -1) {
                backward_path.push_back(curr);
            }
        }

        forward_path.insert(forward_path.end(), backward_path.begin(), backward_path.end());
        return GraphResult{forward_path, best_dist};
    };

    return run_query_with_reducer(origin_id, destination_id, run_bidir_buckets, true);
}

GraphResult Graph::dijkstra_negative(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id,
                                     std::optional<int> cycle_check_iterations) {
    input_check(origin_id, destination_id);

    auto run_negative = [this, cycle_check_iterations](
        const CsrGraph& g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);

        size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> predecessor(n, -1);

        using PQElement = std::pair<double, int>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

        for (const auto& [oid, odist] : origin_entries) {
            distance_matrix[oid] = odist;
            open_leaves.push({odist, oid});
        }

        int cycle_iteration = 0;
        int check_iterations = cycle_check_iterations.value_or(n);

        while (!open_leaves.empty()) {
            auto [current_distance, current_id] = open_leaves.top();
            open_leaves.pop();

            if (current_distance == distance_matrix[current_id]) {
                cycle_iteration++;
                if (cycle_iteration >= check_iterations) {
                    cycle_iteration = 0;
                    this->cycle_check(predecessor, current_id);
                }

                for (const auto& [connected_id, connected_distance] : g[current_id]) {
                    double possible_distance = current_distance + connected_distance;
                    if (possible_distance < distance_matrix[connected_id]) {
                        distance_matrix[connected_id] = possible_distance;
                        predecessor[connected_id] = current_id;
                        open_leaves.push({possible_distance, connected_id});
                    }
                }
            }
        }

        double best_dist = std::numeric_limits<double>::infinity();
        int best_target = -1;
        for (const auto& [did, ddist] : dest_entries) {
            if (distance_matrix[did] != std::numeric_limits<double>::infinity()) {
                double tot = distance_matrix[did] + ddist;
                if (tot < best_dist) {
                    best_dist = tot;
                    best_target = did;
                }
            }
        }

        if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(best_target, predecessor),
            best_dist
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_negative);
}

// One heuristic of A* costs one call of heuristic_fn per destination node. Above
// this number of destination nodes, A* was slower than Dijkstra on the built-in
// networks. The heuristic is then the smallest exit distance, and the search
// scans the nodes in the order of Dijkstra.
constexpr size_t MAX_DESTINATION_NODES_WITH_HEURISTIC = 4;

GraphResult Graph::a_star(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id,
                          std::function<double(int, int)> heuristic_fn) {
    if (!heuristic_fn) {
        return dijkstra(origin_id, destination_id);
    }

    input_check(origin_id, destination_id);

    auto run_astar = [this, heuristic_fn](
        const CsrGraph& g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);
        std::unordered_map<int, double> dest_map(dest_entries.begin(), dest_entries.end());

        size_t n = g.size();
        if (tl_astar_state.size() < n) {
            tl_astar_state.resize(n);
        }

        tl_astar_stamp++;
        if (tl_astar_stamp == 0) {
            std::fill(tl_astar_state.begin(), tl_astar_state.end(), AStarNodeState{});
            tl_astar_stamp = 1;
        }
        const uint32_t stamp = tl_astar_stamp;
        auto* state = tl_astar_state.data();

        auto& open_leaves = tl_astar_open;
        open_leaves.clear();
        const std::greater<> compare;

        // The heuristic of a node estimates its distance to the destination
        // point. It is the smallest sum of the estimate to a destination node
        // and the exit distance of that node.
        double smallest_exit_distance = std::numeric_limits<double>::infinity();
        for (const auto& [did, ddist] : dest_entries) {
            smallest_exit_distance = std::min(smallest_exit_distance, ddist);
        }
        const bool calls_heuristic = dest_entries.size() <= MAX_DESTINATION_NODES_WITH_HEURISTIC;
        auto h_to_dest = [&](int u) -> double {
            if (!calls_heuristic) {
                return smallest_exit_distance;
            }
            double min_h = std::numeric_limits<double>::infinity();
            for (const auto& [did, ddist] : dest_entries) {
                min_h = std::min(min_h, heuristic_fn(u, did) + ddist);
            }
            return min_h;
        };

        double best_dist = std::numeric_limits<double>::infinity();
        int best_target = -1;

        for (const auto& [oid, odist] : origin_entries) {
            state[oid].dist = odist;
            state[oid].pred = -1;
            state[oid].stamp = stamp;
            open_leaves.push_back({odist + h_to_dest(oid), odist, oid});
            std::push_heap(open_leaves.begin(), open_leaves.end(), compare);

            auto it = dest_map.find(oid);
            if (it != dest_map.end()) {
                double cand = odist + it->second;
                if (cand < best_dist) {
                    best_dist = cand;
                    best_target = oid;
                }
            }
        }

        size_t node_scans = 0;
        while (!open_leaves.empty()) {
            std::pop_heap(open_leaves.begin(), open_leaves.end(), compare);
            const auto [key, current_distance, current_id] = open_leaves.back();
            open_leaves.pop_back();

            // No route through a node left in the queue is shorter than its key.
            if (key >= best_dist) {
                break;
            }
            // A shorter distance to this node was found after this entry.
            if (current_distance > state[current_id].dist) {
                continue;
            }

            ++node_scans;
            for (const auto& [connected_id, connected_distance] : g[current_id]) {
                double possible_distance = current_distance + connected_distance;
                if (state[connected_id].stamp != stamp || possible_distance < state[connected_id].dist) {
                    state[connected_id].dist = possible_distance;
                    state[connected_id].pred = current_id;
                    state[connected_id].stamp = stamp;

                    auto it = dest_map.find(connected_id);
                    if (it != dest_map.end()) {
                        double tot = possible_distance + it->second;
                        if (tot < best_dist) {
                            best_dist = tot;
                            best_target = connected_id;
                        }
                    }

                    double connected_key = possible_distance + h_to_dest(connected_id);
                    if (connected_key < best_dist) {
                        open_leaves.push_back({connected_key, possible_distance, connected_id});
                        std::push_heap(open_leaves.begin(), open_leaves.end(), compare);
                    }
                }
            }
        }

        tl_node_scans = node_scans;
        if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        std::vector<int> path;
        int path_node = best_target;
        path.push_back(path_node);
        while (state[path_node].stamp == stamp && state[path_node].pred != -1) {
            path_node = state[path_node].pred;
            path.push_back(path_node);
        }
        std::reverse(path.begin(), path.end());
        return GraphResult{path, best_dist};
    };

    return run_query_with_reducer(origin_id, destination_id, run_astar);
}

GraphResult Graph::bellman_ford(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id) {
    input_check(origin_id, destination_id);

    auto run_bf = [this](
        const CsrGraph& g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);

        size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> predecessor(n, -1);

        for (const auto& [oid, odist] : origin_entries) {
            distance_matrix[oid] = odist;
        }

        for (size_t i = 0; i < n; ++i) {
            bool updated = false;
            for (size_t current_id = 0; current_id < n; ++current_id) {
                double current_distance = distance_matrix[current_id];
                if (current_distance == std::numeric_limits<double>::infinity()) {
                    continue;
                }

                for (const auto& [connected_id, connected_distance] : g[current_id]) {
                    double possible_distance = current_distance + connected_distance;
                    if (possible_distance < distance_matrix[connected_id]) {
                        distance_matrix[connected_id] = possible_distance;
                        predecessor[connected_id] = current_id;
                        updated = true;
                        if (i == n - 1) {
                            throw NegativeCycleException("Graph contains a negative weight cycle");
                        }
                    }
                }
            }
            if (!updated) {
                break;
            }
        }

        double best_dist = std::numeric_limits<double>::infinity();
        int best_target = -1;
        for (const auto& [did, ddist] : dest_entries) {
            if (distance_matrix[did] != std::numeric_limits<double>::infinity()) {
                double tot = distance_matrix[did] + ddist;
                if (tot < best_dist) {
                    best_dist = tot;
                    best_target = did;
                }
            }
        }

        if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(best_target, predecessor),
            best_dist
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_bf);
}

GraphResult Graph::bmssp(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id) {
    input_check(origin_id, destination_id);

    auto run_bmssp = [](
        const CsrGraph& g,
        const NodeIdVariant& orig,
        const NodeIdVariant& dest
    ) -> GraphResult {
        auto origin_entries = get_node_entries(orig);
        auto dest_entries = get_node_entries(dest);
        const size_t n = g.size();

        const bool multi_source = (origin_entries.size() > 1 || (!origin_entries.empty() && origin_entries.front().second != 0.0));

        std::vector<double> distances;
        std::vector<int>    preds;

        if (!multi_source && origin_entries.size() == 1) {
            spp_expected::bmssp<double> solver(g.to_rows());
            solver.prepare_graph(false);

            int src = origin_entries.front().first;
            auto [dist, pred] = solver.execute(src);
            distances = std::move(dist);
            preds     = std::move(pred);
        } else {
            std::vector<std::vector<std::pair<int, double>>> augmented = g.to_rows();
            std::vector<std::pair<int, double>> super_edges;
            super_edges.reserve(origin_entries.size());
            for (const auto& [oid, odist] : origin_entries) {
                super_edges.emplace_back(oid, odist);
            }
            augmented.push_back(std::move(super_edges));

            spp_expected::bmssp<double> aug_solver(augmented);
            aug_solver.prepare_graph(false);

            int super_src = static_cast<int>(augmented.size()) - 1;
            auto [dist, pred] = aug_solver.execute(super_src);

            dist.resize(n);
            pred.resize(n);

            for (size_t i = 0; i < n; ++i) {
                if (pred[i] == super_src) {
                    pred[i] = -1;
                }
            }

            distances = std::move(dist);
            preds     = std::move(pred);
        }

        const double solver_inf = std::numeric_limits<double>::max() / 10.0;
        double best_dist = std::numeric_limits<double>::infinity();
        int best_target = -1;

        for (const auto& [did, ddist] : dest_entries) {
            if (distances[did] < solver_inf) {
                double tot = distances[did] + ddist;
                if (tot < best_dist) {
                    best_dist = tot;
                    best_target = did;
                }
            }
        }

        if (best_target == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw PathNotFoundException("The origin and destination nodes are not connected.");
        }

        std::vector<int> path;
        {
            int cur = best_target;
            while (true) {
                path.push_back(cur);
                int p = preds[cur];
                if (p == cur || p == -1) break;
                cur = p;
            }
            std::reverse(path.begin(), path.end());
        }

        return GraphResult{path, best_dist};
    };

    return run_query_with_reducer(origin_id, destination_id, run_bmssp);
}

GraphResult Graph::cached_shortest_path(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) {
    input_check(origin_id, destination_id);
    int orig = -1;
    bool is_single_origin = false;

    if (std::holds_alternative<int>(origin_id)) {
        orig = std::get<int>(origin_id);
        is_single_origin = true;
    } else if (std::holds_alternative<std::unordered_map<int, double>>(origin_id)) {
        const auto& map = std::get<std::unordered_map<int, double>>(origin_id);
        if (map.size() == 1) {
            orig = map.begin()->first;
            is_single_origin = true;
        }
    } else if (std::holds_alternative<std::set<int>>(origin_id)) {
        const auto& s = std::get<std::set<int>>(origin_id);
        if (s.size() == 1) {
            orig = *s.begin();
            is_single_origin = true;
        }
    }

    if (is_single_origin) {
        // After reduce(), the tree is built on the reduced graph, as the other searches
        auto run_cached = [this, orig, length_only, &origin_id, &destination_id](
                              const CsrGraph& g,
                              const NodeIdVariant& orig_v,
                              const NodeIdVariant& dest) -> GraphResult {
            if (has_reduced_graph && is_same_chain(origin_id, destination_id)) {
                // Same chain: solved on the original graph, not cached
                auto res = dijkstra(orig_v, dest);
                if (length_only) {
                    res.path = {};
                }
                return res;
            }
            if (cache[orig].predecessors.empty()) {
                cache[orig] = shortest_path_tree(g, orig);
            }
            return get_tree_path(orig_v, dest, cache[orig], length_only);
        };
        return run_query_with_reducer(origin_id, destination_id, run_cached);
    }

    auto res = dijkstra(origin_id, destination_id);
    if (length_only) {
        res.path = {};
    }
    return res;
}

std::shared_ptr<CHGraph> Graph::create_contraction_hierarchy(std::function<double(CHGraph*, int)> heuristic_fn, int settled_limit) {
    if (ch_graph_ == nullptr) {
        ch_graph_ = create_ch_graph(heuristic_fn, settled_limit);
    }
    return ch_graph_;
}

GraphResult Graph::contraction_hierarchy(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) {
    if (is_same_chain(origin_id, destination_id)) {
        auto res = dijkstra(origin_id, destination_id);
        if (length_only) {
            res.path = {};
        }
        return res;
    }
    if (ch_graph_ == nullptr) {
        create_contraction_hierarchy();
    }
    auto res = ch_graph_->search(origin_id, destination_id, length_only);
    if (has_reduced_graph && !length_only) {
        res.path = expand_path(res.path);
    }
    return res;
}

std::shared_ptr<TNRGraph> Graph::create_tnr_hierarchy(int num_transit_nodes, std::function<double(CHGraph*, int)> heuristic_fn, int settled_limit) {
    if (tnr_graph_ == nullptr) {
        tnr_graph_ = create_tnr_graph(num_transit_nodes, heuristic_fn, settled_limit);
    }
    return tnr_graph_;
}

void Graph::set_tnr_graph(std::shared_ptr<TNRGraph> tnr_graph) {
    tnr_graph_ = tnr_graph;
}

GraphResult Graph::tnr(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) {
    if (is_same_chain(origin_id, destination_id)) {
        auto res = dijkstra(origin_id, destination_id);
        if (length_only) {
            res.path = {};
        }
        return res;
    }
    if (tnr_graph_ == nullptr) {
        create_tnr_hierarchy();
    }
    auto res = tnr_graph_->search(origin_id, destination_id, length_only);
    if (has_reduced_graph && !length_only) {
        res.path = expand_path(res.path);
    }
    return res;
}

