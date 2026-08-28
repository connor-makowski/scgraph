#include <queue>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <limits>
#include <iostream>
#include "graph.hpp"
#include "bmssp.hpp"

// Constructor
Graph::Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate) {
    this->graph.resize(graph_data.size());
    for (size_t i = 0; i < graph_data.size(); ++i) {
        for (const auto& [node, weight] : graph_data[i]) {
            this->graph[i].push_back({node, weight});
        }
    }
    this->reset_cache();
    if (validate) {
        this->validate();
    }
}

// Override reset_cache
void Graph::reset_cache() {
    GraphReducer::reset_cache();
    __ch_graph__ = nullptr;
    __tnr_graph__ = nullptr;
}

template <typename QueryFn>
GraphResult Graph::run_query_with_reducer(
    const std::variant<int, std::set<int>>& origin_id,
    int destination_id,
    QueryFn&& query_fn
) {
    if (!has_reduced_graph) {
        return query_fn(this->graph, origin_id, destination_id);
    }
    if (is_same_chain(origin_id, destination_id)) {
        return query_fn(this->graph, origin_id, destination_id);
    }
    if (!is_reduced[destination_id]) {
        GraphResult res = query_fn(this->reduced_graph, origin_id, destination_id);
        res.path = expand_path(res.path);
        return res;
    }
    const auto& entries = reduced_inverse_graph[destination_id];
    if (entries.empty()) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }
    double best_length = std::numeric_limits<double>::infinity();
    std::vector<int> best_path;
    int best_entry = -1;
    for (const auto& [entry_u, entry_dist] : entries) {
        try {
            GraphResult res_u = query_fn(this->reduced_graph, origin_id, entry_u);
            double total_dist = res_u.length + entry_dist;
            if (total_dist < best_length) {
                best_length = total_dist;
                best_path = std::move(res_u.path);
                best_entry = entry_u;
            }
        } catch (...) {
            continue;
        }
    }
    if (best_entry == -1 || best_length == std::numeric_limits<double>::infinity()) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }
    std::vector<int> expanded = expand_path(best_path);
    if (destination_id < (int)reduced_inverse_graph_connections.size()) {
        auto it = reduced_inverse_graph_connections[destination_id].find(best_entry);
        if (it != reduced_inverse_graph_connections[destination_id].end()) {
            expanded.insert(expanded.end(), it->second.begin(), it->second.end());
        }
    }
    expanded.push_back(destination_id);
    return GraphResult{expanded, best_length};
}

// Tree algorithms
TreeData Graph::get_shortest_path_tree(const std::variant<int, std::set<int>>& origin_id) {
    input_check(origin_id, 0);
    auto origin_ids = get_origin_ids(origin_id);

    const auto& g = this->graph;
    const size_t n = g.size();
    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessors(n, -1);

    using PQElement = std::pair<double, int>;
    std::priority_queue<PQElement, std::vector<PQElement>, std::greater<>> open_leaves;

    for (int oid : origin_ids) {
        distance_matrix[oid] = 0.0;
        open_leaves.emplace(0.0, oid);
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

GraphResult Graph::get_tree_path(int origin_id, int destination_id, const TreeData& tree_data, bool length_only) {
    bool origin_matches = false;
    if (std::holds_alternative<int>(tree_data.origin_id)) {
        origin_matches = (std::get<int>(tree_data.origin_id) == origin_id);
    } else {
        const auto& origins = std::get<std::set<int>>(tree_data.origin_id);
        origin_matches = (origins.find(origin_id) != origins.end());
    }

    if (!origin_matches) {
        throw std::runtime_error("The origin node must be the same as the spanning node for this function to work.");
    }

    const double destination_distance = tree_data.distance_matrix[destination_id];
    if (destination_distance == std::numeric_limits<double>::infinity()) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }

    if (length_only) {
        return GraphResult{{}, destination_distance};
    }

    std::vector<int> current_path;
    int current_id = destination_id;
    current_path.push_back(destination_id);

    while (current_id != origin_id && current_id != -1) {
        current_id = tree_data.predecessors[current_id];
        current_path.push_back(current_id);
    }

    std::reverse(current_path.begin(), current_path.end());
    return GraphResult{current_path, destination_distance};
}

namespace {
struct DijkstraNodeState {
    double dist;
    int pred;
    uint32_t stamp = 0;
};

thread_local std::vector<DijkstraNodeState> tl_dijkstra_state;
thread_local uint32_t tl_dijkstra_stamp = 0;

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
}

// Shortest path algorithms
GraphResult Graph::dijkstra(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    input_check(origin_id, destination_id);

    auto run_dijkstra = [this](const std::vector<std::vector<std::pair<int, double>>>& g,
                               const std::variant<int, std::set<int>>& orig,
                               int dest) -> GraphResult {
        auto origin_ids = get_origin_ids(orig);
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

        using PQElement = std::pair<double, int>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<>> open_leaves;

        for (int oid : origin_ids) {
            state[oid].dist = 0.0;
            state[oid].pred = -1;
            state[oid].stamp = stamp;
            open_leaves.emplace(0.0, oid);
        }

        while (!open_leaves.empty()) {
            auto [current_distance, current_id] = open_leaves.top();
            open_leaves.pop();

            if (state[current_id].stamp == stamp && current_distance > state[current_id].dist) continue;
            if (current_id == dest) break;
            for (const auto& [connected_id, connected_distance] : g[current_id]) {
                const double possible_distance = current_distance + connected_distance;
                if (state[connected_id].stamp != stamp || possible_distance < state[connected_id].dist) {
                    state[connected_id].dist = possible_distance;
                    state[connected_id].pred = current_id;
                    state[connected_id].stamp = stamp;
                    open_leaves.emplace(possible_distance, connected_id);
                }
            }
        }

        if (state[dest].stamp != stamp) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        std::vector<int> output_path;
        int curr = dest;
        output_path.push_back(curr);
        while (state[curr].stamp == stamp && state[curr].pred != -1) {
            curr = state[curr].pred;
            output_path.push_back(curr);
        }
        std::reverse(output_path.begin(), output_path.end());

        return GraphResult{
            output_path,
            state[dest].dist
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_dijkstra);
}

GraphResult Graph::bidirectional_dijkstra(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);

    if (origin_ids.count(destination_id) > 0) {
        return GraphResult{{destination_id}, 0.0};
    }

    auto run_bidir = [&origin_ids](
        const std::vector<std::vector<std::pair<int, double>>>& fwd_g,
        const std::vector<std::vector<std::pair<int, double>>>& inv_g,
        int dest
    ) -> GraphResult {
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

        using PQElement = std::pair<double, int>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<>> forward_open;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<>> backward_open;

        for (int oid : origin_ids) {
            state[oid].forward_dist = 0.0;
            state[oid].forward_pred = -1;
            state[oid].forward_stamp = stamp;
            forward_open.emplace(0.0, oid);
        }

        state[dest].backward_dist = 0.0;
        state[dest].backward_pred = -1;
        state[dest].backward_stamp = stamp;
        backward_open.emplace(0.0, dest);

        double best_dist = std::numeric_limits<double>::infinity();
        int meeting_node = -1;

        while (!forward_open.empty() && !backward_open.empty()) {
            const double top_fwd = forward_open.top().first;
            const double top_bwd = backward_open.top().first;
            if (top_fwd + top_bwd >= best_dist) {
                break;
            }

            if (top_fwd <= top_bwd) {
                auto [cur_d, u] = forward_open.top();
                forward_open.pop();

                if (state[u].forward_stamp == stamp && cur_d == state[u].forward_dist) {
                    for (const auto& [v, w] : fwd_g[u]) {
                        const double new_d = cur_d + w;
                        if (state[v].forward_stamp != stamp || new_d < state[v].forward_dist) {
                            state[v].forward_dist = new_d;
                            state[v].forward_pred = u;
                            state[v].forward_stamp = stamp;
                            forward_open.emplace(new_d, v);
                            if (state[v].backward_stamp == stamp) {
                                const double total_d = new_d + state[v].backward_dist;
                                if (total_d < best_dist) {
                                    best_dist = total_d;
                                    meeting_node = v;
                                }
                            }
                        }
                    }
                }
            } else {
                auto [cur_d, v] = backward_open.top();
                backward_open.pop();

                if (state[v].backward_stamp == stamp && cur_d == state[v].backward_dist) {
                    for (const auto& [u, w] : inv_g[v]) {
                        const double new_d = cur_d + w;
                        if (state[u].backward_stamp != stamp || new_d < state[u].backward_dist) {
                            state[u].backward_dist = new_d;
                            state[u].backward_pred = v;
                            state[u].backward_stamp = stamp;
                            backward_open.emplace(new_d, u);
                            if (state[u].forward_stamp == stamp) {
                                const double total_d = state[u].forward_dist + new_d;
                                if (total_d < best_dist) {
                                    best_dist = total_d;
                                    meeting_node = u;
                                }
                            }
                        }
                    }
                }
            }
        }

        if (meeting_node == -1 || best_dist == std::numeric_limits<double>::infinity()) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        std::vector<int> forward_path;
        int curr = meeting_node;
        while (curr != -1) {
            forward_path.push_back(curr);
            if (origin_ids.count(curr) > 0) {
                break;
            }
            curr = (state[curr].forward_stamp == stamp) ? state[curr].forward_pred : -1;
        }
        std::reverse(forward_path.begin(), forward_path.end());

        std::vector<int> backward_path;
        curr = meeting_node;
        while (curr != dest && curr != -1) {
            curr = (state[curr].backward_stamp == stamp) ? state[curr].backward_pred : -1;
            if (curr != -1) {
                backward_path.push_back(curr);
            }
        }

        forward_path.insert(forward_path.end(), backward_path.begin(), backward_path.end());
        return GraphResult{forward_path, best_dist};
    };

    if (has_reduced_graph) {
        if (is_same_chain(origin_id, destination_id)) {
            this->ensure_inverse_graph();
            return run_bidir(this->graph, this->inverse_graph, destination_id);
        }
        GraphResult res = run_bidir(this->reduced_graph, this->reduced_inverse_graph, destination_id);
        res.path = expand_path(res.path);
        return res;
    }

    this->ensure_inverse_graph();
    return run_bidir(this->graph, this->inverse_graph, destination_id);
}

GraphResult Graph::dijkstra_buckets(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                                     std::optional<double> max_edge_weight) {
    input_check(origin_id, destination_id);

    auto run_buckets = [this, max_edge_weight](const std::vector<std::vector<std::pair<int, double>>>& g,
                                               const std::variant<int, std::set<int>>& orig,
                                               int dest) -> GraphResult {
        auto origin_ids = get_origin_ids(orig);

        double max_weight = 0.0;
        if (max_edge_weight.has_value()) {
            max_weight = max_edge_weight.value();
        } else {
            for (const auto& node_edges : g) {
                for (const auto& [connected_id, connected_distance] : node_edges) {
                    if (connected_distance > max_weight) {
                        max_weight = connected_distance;
                    }
                }
            }
        }
        int num_buckets = static_cast<int>(std::ceil(max_weight)) + 1;

        const size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> predecessor(n, -1);
        std::vector<std::vector<int>> buckets(num_buckets);

        for (int oid : origin_ids) {
            distance_matrix[oid] = 0.0;
            buckets[0].push_back(oid);
        }

        int current_dist = 0;
        size_t nodes_in_buckets = origin_ids.size();

        while (nodes_in_buckets > 0) {
            int bucket_idx = current_dist % num_buckets;
            while (buckets[bucket_idx].empty()) {
                current_dist++;
                bucket_idx = current_dist % num_buckets;
                if (nodes_in_buckets == 0) break;
                if (distance_matrix[dest] < static_cast<double>(current_dist)) break;
            }

            if (nodes_in_buckets == 0 || distance_matrix[dest] < static_cast<double>(current_dist)) break;

            int current_id = buckets[bucket_idx].back();
            buckets[bucket_idx].pop_back();
            nodes_in_buckets--;

            if (distance_matrix[current_id] < static_cast<double>(current_dist)) {
                continue;
            }

            for (const auto& [connected_id, connected_distance] : g[current_id]) {
                double possible_distance = distance_matrix[current_id] + connected_distance;
                if (possible_distance < distance_matrix[connected_id]) {
                    distance_matrix[connected_id] = possible_distance;
                    predecessor[connected_id] = current_id;
                    buckets[static_cast<int>(possible_distance) % num_buckets].push_back(connected_id);
                    nodes_in_buckets++;
                }
            }
        }

        if (distance_matrix[dest] == std::numeric_limits<double>::infinity()) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(dest, predecessor),
            distance_matrix[dest]
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_buckets);
}

GraphResult Graph::dijkstra_negative(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                                     std::optional<int> cycle_check_iterations) {
    input_check(origin_id, destination_id);

    auto run_negative = [this, cycle_check_iterations](const std::vector<std::vector<std::pair<int, double>>>& g,
                                                       const std::variant<int, std::set<int>>& orig,
                                                       int dest) -> GraphResult {
        auto origin_ids = get_origin_ids(orig);

        size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> predecessor(n, -1);

        using PQElement = std::pair<double, int>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

        for (int oid : origin_ids) {
            distance_matrix[oid] = 0.0;
            open_leaves.push({0.0, oid});
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

        if (distance_matrix[dest] == std::numeric_limits<double>::infinity()) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(dest, predecessor),
            distance_matrix[dest]
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_negative);
}

GraphResult Graph::a_star(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                          std::function<double(int, int)> heuristic_fn) {
    if (!heuristic_fn) {
        return dijkstra(origin_id, destination_id);
    }

    input_check(origin_id, destination_id);

    auto run_astar = [this, heuristic_fn](const std::vector<std::vector<std::pair<int, double>>>& g,
                                          const std::variant<int, std::set<int>>& orig,
                                          int dest) -> GraphResult {
        auto origin_ids = get_origin_ids(orig);

        size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> visited(n, 0);
        std::vector<int> predecessor(n, -1);

        using PQElement = std::pair<double, int>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

        for (int oid : origin_ids) {
            distance_matrix[oid] = 0.0;
            open_leaves.push({0.0, oid});
        }

        int current_id = -1;
        while (!open_leaves.empty()) {
            current_id = open_leaves.top().second;
            open_leaves.pop();

            if (current_id == dest) {
                break;
            }

            if (visited[current_id] == 1) {
                continue;
            }
            visited[current_id] = 1;

            double current_distance = distance_matrix[current_id];
            for (const auto& [connected_id, connected_distance] : g[current_id]) {
                double possible_distance = current_distance + connected_distance;
                if (possible_distance < distance_matrix[connected_id]) {
                    distance_matrix[connected_id] = possible_distance;
                    predecessor[connected_id] = current_id;
                    open_leaves.push({
                        possible_distance + heuristic_fn(connected_id, dest),
                        connected_id
                    });
                }
            }
        }

        if (current_id != dest) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(dest, predecessor),
            distance_matrix[dest]
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_astar);
}

GraphResult Graph::bellman_ford(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    input_check(origin_id, destination_id);

    auto run_bf = [this](const std::vector<std::vector<std::pair<int, double>>>& g,
                         const std::variant<int, std::set<int>>& orig,
                         int dest) -> GraphResult {
        auto origin_ids = get_origin_ids(orig);

        size_t n = g.size();
        std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
        std::vector<int> predecessor(n, -1);

        for (int oid : origin_ids) {
            distance_matrix[oid] = 0.0;
        }

        for (size_t i = 0; i < n; ++i) {
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
                        if (i == n - 1) {
                            throw std::runtime_error("Graph contains a negative weight cycle");
                        }
                    }
                }
            }
        }

        if (distance_matrix[dest] == std::numeric_limits<double>::infinity()) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        return GraphResult{
            reconstruct_path(dest, predecessor),
            distance_matrix[dest]
        };
    };

    return run_query_with_reducer(origin_id, destination_id, run_bf);
}

GraphResult Graph::bmssp(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    input_check(origin_id, destination_id);

    auto run_bmssp = [](const std::vector<std::vector<std::pair<int, double>>>& g,
                        const std::variant<int, std::set<int>>& orig,
                        int dest) -> GraphResult {
        auto origin_ids = get_origin_ids(orig);
        const size_t n = g.size();

        const bool multi_source = (origin_ids.size() > 1);

        std::vector<double> distances;
        std::vector<int>    preds;

        if (!multi_source) {
            spp_expected::bmssp<double> solver(g);
            solver.prepare_graph(false);

            int src = *origin_ids.begin();
            auto [dist, pred] = solver.execute(src);
            distances = std::move(dist);
            preds     = std::move(pred);
        } else {
            std::vector<std::vector<std::pair<int, double>>> augmented(g);
            std::vector<std::pair<int, double>> super_edges;
            super_edges.reserve(origin_ids.size());
            for (int oid : origin_ids) {
                super_edges.emplace_back(oid, 0.0);
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
        if (distances[dest] >= solver_inf) {
            throw std::runtime_error("The origin and destination nodes are not connected.");
        }

        std::vector<int> path;
        {
            int cur = dest;
            while (true) {
                path.push_back(cur);
                int p = preds[cur];
                if (p == cur || p == -1) break;
                cur = p;
            }
            std::reverse(path.begin(), path.end());
        }

        return GraphResult{path, distances[dest]};
    };

    return run_query_with_reducer(origin_id, destination_id, run_bmssp);
}

GraphResult Graph::cached_shortest_path(int origin_id, int destination_id, bool length_only) {
    if (cache[origin_id].predecessors.empty()) {
        cache[origin_id] = get_shortest_path_tree(origin_id);
    }

    return get_tree_path(origin_id, destination_id, cache[origin_id], length_only);
}

std::shared_ptr<CHGraph> Graph::create_contraction_hierarchy(std::function<double(CHGraph*, int)> heuristic_fn, int settled_limit) {
    if (__ch_graph__ == nullptr) {
        __ch_graph__ = create_ch_graph(heuristic_fn, settled_limit);
    }
    return __ch_graph__;
}

GraphResult Graph::contraction_hierarchy(int origin_id, int destination_id, bool length_only) {
    if (is_same_chain(origin_id, destination_id)) {
        auto res = dijkstra(origin_id, destination_id);
        if (length_only) {
            res.path = {};
        }
        return res;
    }
    if (__ch_graph__ == nullptr) {
        create_contraction_hierarchy();
    }
    auto res = __ch_graph__->get_shortest_path(origin_id, destination_id);
    if (has_reduced_graph) {
        res.path = expand_path(res.path);
    }
    if (length_only) {
        res.path = {};
    }
    return res;
}

std::shared_ptr<TNRGraph> Graph::create_tnr_hierarchy(int num_transit_nodes, std::function<double(CHGraph*, int)> heuristic_fn, int settled_limit) {
    if (__tnr_graph__ == nullptr) {
        __tnr_graph__ = create_tnr_graph(num_transit_nodes, heuristic_fn, settled_limit);
    }
    return __tnr_graph__;
}

void Graph::set_tnr_graph(std::shared_ptr<TNRGraph> tnr_graph) {
    __tnr_graph__ = tnr_graph;
}

GraphResult Graph::tnr(int origin_id, int destination_id, bool length_only) {
    if (is_same_chain(origin_id, destination_id)) {
        auto res = dijkstra(origin_id, destination_id);
        if (length_only) {
            res.path = {};
        }
        return res;
    }
    if (__tnr_graph__ == nullptr) {
        create_tnr_hierarchy();
    }
    auto res = __tnr_graph__->search(origin_id, destination_id, length_only);
    if (has_reduced_graph && !length_only) {
        res.path = expand_path(res.path);
    }
    return res;
}
