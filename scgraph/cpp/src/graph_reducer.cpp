#include <queue>
#include <algorithm>
#include <tuple>
#include "graph_reducer.hpp"
#include "contraction_hierarchies.hpp"
#include "transit_node_routing.hpp"

void GraphReducer::reset_cache() {
    GraphUtils::reset_cache();
    has_reduced_graph = false;
    is_reduced.clear();
    reduced_node_chain_ids.clear();
    reduced_graph.clear();
    reduced_graph_connections.clear();
    reduced_inverse_graph.clear();
    reduced_inverse_graph_connections.clear();
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

    // Assign chain IDs to connected components of reduced nodes
    reduced_node_chain_ids.assign(n, -1);
    int current_chain_id = 0;
    for (size_t u = 0; u < n; ++u) {
        if (is_reduced[u] && reduced_node_chain_ids[u] == -1) {
            std::vector<int> q = {(int)u};
            reduced_node_chain_ids[u] = current_chain_id;
            while (!q.empty()) {
                int curr = q.back();
                q.pop_back();
                for (const auto& edge : graph[curr]) {
                    int v = edge.first;
                    if (v != curr && v >= 0 && v < (int)n && is_reduced[v] && reduced_node_chain_ids[v] == -1) {
                        reduced_node_chain_ids[v] = current_chain_id;
                        q.push_back(v);
                    }
                }
                for (const auto& edge : inverse_graph[curr]) {
                    int v = edge.first;
                    if (v != curr && v >= 0 && v < (int)n && is_reduced[v] && reduced_node_chain_ids[v] == -1) {
                        reduced_node_chain_ids[v] = current_chain_id;
                        q.push_back(v);
                    }
                }
            }
            current_chain_id++;
        }
    }

    // 3. Build reduced graph and connections (outbound from all nodes)
    reduced_graph.assign(n, std::vector<std::pair<int, double>>());
    reduced_graph_connections.assign(n, std::unordered_map<int, std::vector<int>>());

    for (size_t A = 0; A < n; ++A) {
        std::unordered_map<int, double> best_dist;
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

    // 4. Build reduced inverse graph and connections (inbound into all nodes)
    reduced_inverse_graph.assign(n, std::vector<std::pair<int, double>>());
    reduced_inverse_graph_connections.assign(n, std::unordered_map<int, std::vector<int>>());

    for (size_t B = 0; B < n; ++B) {
        std::unordered_map<int, double> best_dist;
        using PQElement = std::tuple<double, int, std::vector<int>>;
        std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

        open_leaves.push({0.0, (int)B, {}});

        while (!open_leaves.empty()) {
            auto [dist, u, path] = open_leaves.top();
            open_leaves.pop();

            if (best_dist.find(u) != best_dist.end() && best_dist[u] <= dist) {
                continue;
            }
            best_dist[u] = dist;

            if (u != (int)B && !is_reduced[u]) {
                // Boundary non-reduced node reaching B.
                reduced_inverse_graph[B].push_back({u, dist});
                std::vector<int> fwd_path = path;
                std::reverse(fwd_path.begin(), fwd_path.end());
                if (!fwd_path.empty()) {
                    reduced_inverse_graph_connections[B][u] = fwd_path;
                }
                continue;
            }

            for (const auto& edge : inverse_graph[u]) {
                int v = edge.first;
                double w = edge.second;
                double new_dist = dist + w;
                if (best_dist.find(v) == best_dist.end() || new_dist < best_dist[v]) {
                    std::vector<int> new_path = (u == (int)B) ? std::vector<int>{} : path;
                    if (u != (int)B) {
                        new_path.push_back(u);
                    }
                    open_leaves.push({new_dist, v, new_path});
                }
            }
        }
    }

    has_reduced_graph = true;
}

std::vector<int> GraphReducer::expand_path(const std::vector<int>& path) const {
    if (!has_reduced_graph) {
        return path;
    }
    std::vector<int> new_path;
    for (size_t i = 0; i < path.size() - 1; ++i) {
        int u = path[i];
        int v = path[i + 1];
        new_path.push_back(u);
        bool expanded = false;
        if (u >= 0 && u < (int)reduced_graph_connections.size()) {
            const auto& conns = reduced_graph_connections[u];
            auto it = conns.find(v);
            if (it != conns.end()) {
                new_path.insert(new_path.end(), it->second.begin(), it->second.end());
                expanded = true;
            }
        }
        if (!expanded && v >= 0 && v < (int)reduced_inverse_graph_connections.size()) {
            const auto& inv_conns = reduced_inverse_graph_connections[v];
            auto it = inv_conns.find(u);
            if (it != inv_conns.end()) {
                new_path.insert(new_path.end(), it->second.begin(), it->second.end());
            }
        }
    }
    if (!path.empty()) {
        new_path.push_back(path.back());
    }
    return new_path;
}

std::vector<std::unordered_map<int, double>> GraphReducer::get_reduced_graph() const {
    std::vector<std::unordered_map<int, double>> result;
    result.reserve(reduced_graph.size());
    for (size_t i = 0; i < reduced_graph.size(); ++i) {
        std::unordered_map<int, double> adj;
        for (const auto& [v, w] : reduced_graph[i]) {
            adj[v] = w;
        }
        result.push_back(std::move(adj));
    }
    return result;
}

std::vector<std::unordered_map<int, double>> GraphReducer::get_reduced_inverse_graph() const {
    std::vector<std::unordered_map<int, double>> result;
    result.reserve(reduced_inverse_graph.size());
    for (size_t i = 0; i < reduced_inverse_graph.size(); ++i) {
        std::unordered_map<int, double> adj;
        for (const auto& [v, w] : reduced_inverse_graph[i]) {
            adj[v] = w;
        }
        result.push_back(std::move(adj));
    }
    return result;
}

bool GraphReducer::is_same_chain(const std::variant<int, std::set<int>>& origin_id, std::optional<int> destination_id) const {
    if (!destination_id.has_value() || reduced_node_chain_ids.empty()) {
        return false;
    }
    int dest = destination_id.value();
    if (dest < 0 || dest >= (int)reduced_node_chain_ids.size()) {
        return false;
    }
    int dest_chain = reduced_node_chain_ids[dest];
    if (dest_chain == -1) {
        return false;
    }
    if (std::holds_alternative<int>(origin_id)) {
        int orig = std::get<int>(origin_id);
        if (orig >= 0 && orig < (int)reduced_node_chain_ids.size()) {
            return reduced_node_chain_ids[orig] == dest_chain;
        }
        return false;
    } else {
        const auto& origins = std::get<std::set<int>>(origin_id);
        for (int orig : origins) {
            if (orig >= 0 && orig < (int)reduced_node_chain_ids.size() && reduced_node_chain_ids[orig] == dest_chain) {
                return true;
            }
        }
        return false;
    }
}

std::function<double(CHGraph*, int)> GraphReducer::wrap_heuristic(std::function<double(CHGraph*, int)> heuristic_fn) const {
    if (!has_reduced_graph) {
        return heuristic_fn;
    }
    if (!heuristic_fn) {
        return [this](CHGraph* ch, int node_id) {
            return (is_reduced[node_id] ? 0.0 : 1000000.0) + ch->default_heuristic(node_id);
        };
    }
    return [this, heuristic_fn](CHGraph* ch, int node_id) {
        return (is_reduced[node_id] ? 0.0 : 1000000.0) + heuristic_fn(ch, node_id);
    };
}

std::shared_ptr<CHGraph> GraphReducer::create_ch_graph(std::function<double(CHGraph*, int)> heuristic_fn, int settled_limit) const {
    if (has_reduced_graph) {
        return std::make_shared<CHGraph>(get_reduced_graph(), settled_limit, wrap_heuristic(heuristic_fn), get_reduced_inverse_graph());
    }
    return std::make_shared<CHGraph>(get_graph(), settled_limit, heuristic_fn);
}

std::shared_ptr<TNRGraph> GraphReducer::create_tnr_graph(int num_transit_nodes, std::function<double(CHGraph*, int)> heuristic_fn, int settled_limit) const {
    if (has_reduced_graph) {
        return std::make_shared<TNRGraph>(get_reduced_graph(), settled_limit, num_transit_nodes, wrap_heuristic(heuristic_fn), get_reduced_inverse_graph());
    }
    return std::make_shared<TNRGraph>(get_graph(), settled_limit, num_transit_nodes, heuristic_fn);
}
