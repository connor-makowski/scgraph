#include <queue>
#include <algorithm>
#include <tuple>
#include "graph_reducer.hpp"

void GraphReducer::reset_cache() {
    GraphUtils::reset_cache();
    has_reduced_graph = false;
    is_reduced.clear();
    reduced_graph.clear();
    reduced_graph_connections.clear();
}

void GraphReducer::reduce() {
    this->reset_cache();
    this->ensure_inverse_graph();

    size_t n = graph.size();
    is_reduced.assign(n, false);

    for (size_t u = 0; u < n; ++u) {
        // Count outflows excluding self-loop
        size_t outflows_len = 0;
        for (const auto& edge : graph[u]) {
            if (edge.first != (int)u) {
                outflows_len++;
            }
        }

        size_t inflows_len = 0;
        for (const auto& edge : inverse_graph[u]) {
            if (edge.first != (int)u) {
                inflows_len++;
            }
        }

        if (outflows_len == 1) {
            if (inflows_len >= 1) {
                is_reduced[u] = true;
            }
        } else if (outflows_len == 2) {
            if (inflows_len > 0) {
                // Get set of outflows and inflows
                std::set<int> outflows;
                for (const auto& edge : graph[u]) {
                    if (edge.first != (int)u) {
                        outflows.insert(edge.first);
                    }
                }
                bool subset = true;
                for (const auto& edge : inverse_graph[u]) {
                    if (edge.first != (int)u) {
                        if (outflows.find(edge.first) == outflows.end()) {
                            subset = false;
                            break;
                        }
                    }
                }
                if (subset) {
                    is_reduced[u] = true;
                }
            }
        }
    }

    reduced_graph.assign(n, std::vector<std::pair<int, double>>());
    reduced_graph_connections.assign(n, std::unordered_map<int, std::vector<int>>());

    for (size_t A = 0; A < n; ++A) {
        if (is_reduced[A]) {
            continue;
        }

        std::unordered_map<int, double> best_dist;
        // Priority queue element: (distance, (node, path))
        using PQElement = std::tuple<double, int, std::vector<int>>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

        open_leaves.push({0.0, (int)A, {}});

        while (!open_leaves.empty()) {
            auto [dist, u, path] = open_leaves.top();
            open_leaves.pop();

            if (best_dist.find(u) != best_dist.end() && best_dist[u] <= dist) {
                continue;
            }
            best_dist[u] = dist;

            if (u != (int)A && !is_reduced[u]) {
                // Boundary non-reduced node. Record connection.
                reduced_graph[A].push_back({u, dist});
                if (!path.empty()) {
                    reduced_graph_connections[A][u] = path;
                }
                continue;
            }

            for (const auto& edge : graph[u]) {
                int v = edge.first;
                double w = edge.second;
                double new_dist = dist + w;
                if (best_dist.find(v) == best_dist.end() || new_dist < best_dist[v]) {
                    std::vector<int> new_path = (u == (int)A) ? std::vector<int>{} : path;
                    if (u != (int)A) {
                        new_path.push_back(u);
                    }
                    open_leaves.push({new_dist, v, new_path});
                }
            }
        }
    }

    has_reduced_graph = true;
}

std::unordered_map<int, std::pair<double, std::vector<int>>> GraphReducer::get_temp_connections(
    int start_node, const std::string& direction, const std::set<int>& target_nodes) {

    const auto& adj_graph = (direction == "out") ? graph : inverse_graph;

    std::unordered_map<int, double> best_dist;
    using PQElement = std::tuple<double, int, std::vector<int>>;
    std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

    open_leaves.push({0.0, start_node, {}});

    std::unordered_map<int, std::pair<double, std::vector<int>>> connections;

    while (!open_leaves.empty()) {
        auto [dist, u, path] = open_leaves.top();
        open_leaves.pop();

        if (best_dist.find(u) != best_dist.end() && best_dist[u] <= dist) {
            continue;
        }
        best_dist[u] = dist;

        if (u != start_node && (!is_reduced[u] || target_nodes.find(u) != target_nodes.end())) {
            connections[u] = {dist, path};
            continue;
        }

        for (const auto& edge : adj_graph[u]) {
            int v = edge.first;
            double w = edge.second;
            double new_dist = dist + w;
            if (best_dist.find(v) == best_dist.end() || new_dist < best_dist[v]) {
                std::vector<int> new_path = (u == start_node) ? std::vector<int>{} : path;
                if (u != start_node) {
                    new_path.push_back(u);
                }
                open_leaves.push({new_dist, v, new_path});
            }
        }
    }

    return connections;
}

GraphReducer::RestoreData GraphReducer::prepare_query_graph(const std::variant<int, std::set<int>>& origin_id, std::optional<int> destination_id) {
    std::set<int> origin_ids = get_origin_ids(origin_id);
    std::set<int> target_nodes = origin_ids;
    if (destination_id.has_value()) {
        target_nodes.insert(destination_id.value());
    }

    std::set<int> nodes_to_process;
    for (int oid : origin_ids) {
        if (is_reduced[oid]) {
            nodes_to_process.insert(oid);
        }
    }
    if (destination_id.has_value() && is_reduced[destination_id.value()]) {
        nodes_to_process.insert(destination_id.value());
    }

    RestoreData restore;

    if (!nodes_to_process.empty()) {
        this->ensure_inverse_graph();
        for (int node : nodes_to_process) {
            // Outgoing
            auto outgoing = get_temp_connections(node, "out", target_nodes);
            if (std::find_if(restore.graph_restore.begin(), restore.graph_restore.end(),
                             [node](const auto& p) { return p.first == node; }) == restore.graph_restore.end()) {
                restore.graph_restore.push_back({node, reduced_graph[node]});
            }
            for (const auto& [v, data] : outgoing) {
                double dist = data.first;
                const auto& path = data.second;
                // Add to reduced_graph
                // Check if v already exists in reduced_graph[node]
                auto it = std::find_if(reduced_graph[node].begin(), reduced_graph[node].end(),
                                       [v](const auto& p) { return p.first == v; });
                if (it != reduced_graph[node].end()) {
                    it->second = dist;
                } else {
                    reduced_graph[node].push_back({v, dist});
                }

                if (!path.empty()) {
                    if (std::find_if(restore.connections_restore.begin(), restore.connections_restore.end(),
                                     [node](const auto& p) { return p.first == node; }) == restore.connections_restore.end()) {
                        restore.connections_restore.push_back({node, reduced_graph_connections[node]});
                    }
                    reduced_graph_connections[node][v] = path;
                }
            }

            // Incoming
            auto incoming = get_temp_connections(node, "in", target_nodes);
            for (const auto& [u, data] : incoming) {
                double dist = data.first;
                auto path = data.second;
                std::reverse(path.begin(), path.end()); // forward path

                if (std::find_if(restore.graph_restore.begin(), restore.graph_restore.end(),
                                 [u](const auto& p) { return p.first == u; }) == restore.graph_restore.end()) {
                    restore.graph_restore.push_back({u, reduced_graph[u]});
                }
                auto it = std::find_if(reduced_graph[u].begin(), reduced_graph[u].end(),
                                       [node](const auto& p) { return p.first == node; });
                if (it != reduced_graph[u].end()) {
                    it->second = dist;
                } else {
                    reduced_graph[u].push_back({node, dist});
                }

                if (!path.empty()) {
                    if (std::find_if(restore.connections_restore.begin(), restore.connections_restore.end(),
                                     [u](const auto& p) { return p.first == u; }) == restore.connections_restore.end()) {
                        restore.connections_restore.push_back({u, reduced_graph_connections[u]});
                    }
                    reduced_graph_connections[u][node] = path;
                }
            }
        }
    }

    // Swap graph with reduced graph
    std::swap(graph, reduced_graph);
    inverse_graph_computed = false; // invalidate inverse graph cache since graph was modified/swapped

    return restore;
}

void GraphReducer::restore_query_graph(const RestoreData& restore) {
    // Swap back graph
    std::swap(graph, reduced_graph);
    inverse_graph_computed = false;

    // Restore original nodes/connections in reduced_graph
    for (const auto& [node, edges] : restore.graph_restore) {
        reduced_graph[node] = edges;
    }
    for (const auto& [node, conns] : restore.connections_restore) {
        reduced_graph_connections[node] = conns;
    }
}

std::vector<int> GraphReducer::expand_path(const std::vector<int>& path) {
    if (!has_reduced_graph) {
        return path;
    }
    std::vector<int> new_path;
    for (size_t i = 0; i < path.size() - 1; ++i) {
        int u = path[i];
        int v = path[i + 1];
        new_path.push_back(u);
        if (u < (int)reduced_graph_connections.size()) {
            const auto& conns = reduced_graph_connections[u];
            auto it = conns.find(v);
            if (it != conns.end()) {
                new_path.insert(new_path.end(), it->second.begin(), it->second.end());
            }
        }
    }
    if (!path.empty()) {
        new_path.push_back(path.back());
    }
    return new_path;
}
