#include <queue>
#include <functional>
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
    reduced_max_edge_weight = 0.0;
}

void GraphReducer::reduce(int iterations) {
    this->reset_cache();
    if (iterations == 0) {
        return;
    }
    this->ensure_inverse_graph();

    size_t n = graph.size();
    is_reduced.assign(n, false);

    int current_iter = 0;
    std::vector<int> candidates;
    while (true) {
        size_t newly_reduced_count = 0;
        if (current_iter == 0) {
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
                        newly_reduced_count++;
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
                            newly_reduced_count++;
                        }
                    }
                }
            }
            // Later passes can only change nodes next to a reduced node
            if (iterations != 1) {
                for (size_t u = 0; u < n; ++u) {
                    if (is_reduced[u]) {
                        continue;
                    }
                    bool next_to_reduced = false;
                    for (const auto* adjacency : {&graph[u], &inverse_graph[u]}) {
                        for (const auto& edge : *adjacency) {
                            int v = edge.first;
                            if (v >= 0 && v < (int)n && is_reduced[v]) {
                                next_to_reduced = true;
                            }
                        }
                    }
                    if (next_to_reduced) {
                        candidates.push_back((int)u);
                    }
                }
            }
        } else {
            // Subsequent iterations: identify pass-through nodes on current reduced topology
            // Reducing u changes the flows of its own outflows and inflows
            // only, so only those are examined again: those after u in this
            // pass, the others in the next one. Examining candidates in
            // increasing order, as a scan of every node would, gives the
            // same result.
            // A node is visited in the current search iff visited[node] == stamp
            std::vector<size_t> visited(n, 0);
            size_t stamp = 0;
            std::vector<char> queued(n, 0);
            std::vector<char> in_next(n, 0);
            std::vector<int> next_candidates;
            for (int c : candidates) {
                queued[c] = 1;
            }
            std::priority_queue<int, std::vector<int>, std::greater<int>> pending(
                std::greater<int>(), std::move(candidates));
            while (!pending.empty()) {
                size_t u = (size_t)pending.top();
                pending.pop();
                if (is_reduced[u]) {
                    continue;
                }

                // Outflows from u through is_reduced nodes
                std::set<int> outflows;
                {
                    std::vector<int> q = {(int)u};
                    visited[u] = ++stamp;
                    while (!q.empty()) {
                        int curr = q.back();
                        q.pop_back();
                        if (curr != (int)u && !is_reduced[curr]) {
                            outflows.insert(curr);
                            continue;
                        }
                        for (const auto& edge : graph[curr]) {
                            int v = edge.first;
                            if (v >= 0 && v < (int)n && visited[v] != stamp) {
                                visited[v] = stamp;
                                q.push_back(v);
                            }
                        }
                    }
                }

                // Inflows to u through is_reduced nodes
                std::set<int> inflows;
                {
                    std::vector<int> q = {(int)u};
                    visited[u] = ++stamp;
                    while (!q.empty()) {
                        int curr = q.back();
                        q.pop_back();
                        if (curr != (int)u && !is_reduced[curr]) {
                            inflows.insert(curr);
                            continue;
                        }
                        for (const auto& edge : inverse_graph[curr]) {
                            int v = edge.first;
                            if (v >= 0 && v < (int)n && visited[v] != stamp) {
                                visited[v] = stamp;
                                q.push_back(v);
                            }
                        }
                    }
                }

                size_t outflows_len = outflows.size();
                size_t inflows_len = inflows.size();

                if (outflows_len == 1) {
                    if (inflows_len >= 1) {
                        is_reduced[u] = true;
                        newly_reduced_count++;
                    }
                } else if (outflows_len == 2) {
                    if (inflows_len > 0) {
                        bool subset = true;
                        for (int in_v : inflows) {
                            if (outflows.find(in_v) == outflows.end()) {
                                subset = false;
                                break;
                            }
                        }
                        if (subset) {
                            is_reduced[u] = true;
                            newly_reduced_count++;
                        }
                    }
                }
                if (is_reduced[u]) {
                    for (const std::set<int>* flows : {&outflows, &inflows}) {
                        for (int w : *flows) {
                            if (w < (int)u) {
                                if (!in_next[w]) {
                                    in_next[w] = 1;
                                    next_candidates.push_back(w);
                                }
                            } else if (!queued[w]) {
                                queued[w] = 1;
                                pending.push(w);
                            }
                        }
                    }
                }
            }
            candidates = std::move(next_candidates);
        }

        current_iter++;
        if (newly_reduced_count == 0) {
            break;
        }
        if (iterations != -1 && current_iter >= iterations) {
            break;
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

    // 3. Build reduced graph (outbound from all nodes). Hidden nodes are
    // stored as pointers from the searches rooted at non-reduced nodes (see
    // hidden_nodes): the search from a non-reduced node A gives those of the
    // reduced_inverse_graph edges A -> B.
    reduced_graph.assign(n, std::vector<std::pair<int, double>>());
    reduced_inverse_graph_connections.assign(n, std::vector<std::pair<int, int>>());

    // Search state shared by the 2n local searches of steps 3-4:
    // best_dist[v] and predecessor[v] belong to the current search iff seen[v] == stamp
    std::vector<double> best_dist(n);
    std::vector<int> predecessor(n);
    std::vector<size_t> seen(n, 0);
    size_t stamp = 0;
    using PQElement = std::pair<double, int>;
    std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;

    for (size_t A = 0; A < n; ++A) {
        seen[A] = ++stamp;
        best_dist[A] = 0.0;
        open_leaves.push({0.0, (int)A});
        bool is_root = !is_reduced[A];

        while (!open_leaves.empty()) {
            auto [dist, u] = open_leaves.top();
            open_leaves.pop();

            if (dist > best_dist[u]) {
                continue;
            }

            if (is_root && u != (int)A && predecessor[u] != (int)A) {
                reduced_inverse_graph_connections[u].push_back({(int)A, predecessor[u]});
            }

            if (u != (int)A && !is_reduced[u]) {
                // Boundary non-reduced node. Record connection.
                reduced_graph[A].push_back({u, dist});
                continue;
            }

            for (const auto& edge : graph[u]) {
                int v = edge.first;
                double w = edge.second;
                double new_dist = dist + w;
                if (seen[v] != stamp || new_dist < best_dist[v]) {
                    seen[v] = stamp;
                    best_dist[v] = new_dist;
                    predecessor[v] = u;
                    open_leaves.push({new_dist, v});
                }
            }
        }
    }

    // 4. Build reduced inverse graph (inbound into all nodes). The search from
    // a non-reduced node B gives the hidden nodes of the reduced_graph edges
    // A -> B.
    reduced_inverse_graph.assign(n, std::vector<std::pair<int, double>>());
    reduced_graph_connections.assign(n, std::vector<std::pair<int, int>>());

    for (size_t B = 0; B < n; ++B) {
        seen[B] = ++stamp;
        best_dist[B] = 0.0;
        open_leaves.push({0.0, (int)B});
        bool is_root = !is_reduced[B];

        while (!open_leaves.empty()) {
            auto [dist, u] = open_leaves.top();
            open_leaves.pop();

            if (dist > best_dist[u]) {
                continue;
            }

            if (is_root && u != (int)B && predecessor[u] != (int)B) {
                reduced_graph_connections[u].push_back({(int)B, predecessor[u]});
            }

            if (u != (int)B && !is_reduced[u]) {
                // Boundary non-reduced node reaching B.
                reduced_inverse_graph[B].push_back({u, dist});
                continue;
            }

            for (const auto& edge : inverse_graph[u]) {
                int v = edge.first;
                double w = edge.second;
                double new_dist = dist + w;
                if (seen[v] != stamp || new_dist < best_dist[v]) {
                    seen[v] = stamp;
                    best_dist[v] = new_dist;
                    predecessor[v] = u;
                    open_leaves.push({new_dist, v});
                }
            }
        }
    }

    has_reduced_graph = true;
    for (const auto& edges : reduced_graph) {
        for (const auto& [destination_id, weight] : edges) {
            if (weight > reduced_max_edge_weight) {
                reduced_max_edge_weight = weight;
            }
        }
    }
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
        std::vector<int> hidden = hidden_nodes(u, v, false);
        if (hidden.empty()) {
            hidden = hidden_nodes(v, u, true);
        }
        new_path.insert(new_path.end(), hidden.begin(), hidden.end());
    }
    if (!path.empty()) {
        new_path.push_back(path.back());
    }
    return new_path;
}

std::vector<int> GraphReducer::hidden_nodes(int node, int root, bool inverse) const {
    // Follow the pointers toward root: they come from one shortest path tree
    const auto& pointers = inverse ? reduced_inverse_graph_connections : reduced_graph_connections;
    std::vector<int> path;
    if (node < 0 || node >= (int)pointers.size()) {
        return path;
    }
    bool found = true;
    while (found) {
        found = false;
        for (const auto& [pointer_root, next] : pointers[node]) {
            if (pointer_root == root) {
                node = next;
                path.push_back(node);
                found = true;
                break;
            }
        }
    }
    if (inverse) {
        std::reverse(path.begin(), path.end());
    }
    return path;
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

bool GraphReducer::is_same_chain(const NodeIdVariant& origin_id, const std::optional<NodeIdVariant>& destination_id) const {
    if (!destination_id.has_value() || reduced_node_chain_ids.empty()) {
        return false;
    }
    auto orig_ids = get_node_ids(origin_id);
    auto dest_ids = get_node_ids(destination_id.value());

    for (int orig : orig_ids) {
        if (orig < 0 || orig >= (int)reduced_node_chain_ids.size()) {
            continue;
        }
        int orig_chain = reduced_node_chain_ids[orig];
        if (orig_chain == -1) {
            continue;
        }
        for (int dest : dest_ids) {
            if (dest >= 0 && dest < (int)reduced_node_chain_ids.size() && reduced_node_chain_ids[dest] == orig_chain) {
                return true;
            }
        }
    }
    return false;
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
