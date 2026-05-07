#include "transit_node_routing.hpp"
#include <queue>
#include <algorithm>
#include <limits>
#include <iostream>
#include <functional>

TNRGraph::TNRGraph(const std::vector<std::unordered_map<int, double>>& graph,
                   int num_transit_nodes,
                   std::function<double(CHGraph*, int)> heuristic_fn)
    : CHGraph(graph, heuristic_fn) {
    // 1. Select Transit Nodes
    std::vector<int> sorted_nodes(nodes_count);
    for (int i = 0; i < nodes_count; ++i) {
        sorted_nodes[i] = i;
    }
    std::sort(sorted_nodes.begin(), sorted_nodes.end(), [this](int a, int b) {
        return ranks[a] > ranks[b];
    });

    int actual_num_transit = std::min(num_transit_nodes, nodes_count);
    for (int i = 0; i < actual_num_transit; ++i) {
        transit_nodes.insert(sorted_nodes[i]);
    }

    // 2. Compute Access Nodes
    forward_access_nodes.assign(nodes_count, {});
    backward_access_nodes.assign(nodes_count, {});

    auto compute_access_nodes = [this](int node_id, bool forward) {
        std::unordered_map<int, double> access_nodes;
        std::unordered_map<int, double> distances;
        distances[node_id] = 0.0;
        using PQItem = std::pair<double, int>;
        std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
        open_leaves.push({0.0, node_id});

        while (!open_leaves.empty()) {
            auto [dist, current_id] = open_leaves.top();
            open_leaves.pop();

            if (distances.find(current_id) != distances.end() && dist > distances[current_id]) {
                continue;
            }

            if (transit_nodes.find(current_id) != transit_nodes.end()) {
                if (access_nodes.find(current_id) == access_nodes.end() || dist < access_nodes[current_id]) {
                    access_nodes[current_id] = dist;
                }
                continue;
            }

            const auto& neighbors = forward ? forward_graph[current_id] : backward_graph[current_id];
            for (const auto& [neighbor_id, weight] : neighbors) {
                double new_dist = dist + weight;
                if (distances.find(neighbor_id) == distances.end() || new_dist < distances[neighbor_id]) {
                    distances[neighbor_id] = new_dist;
                    open_leaves.push({new_dist, neighbor_id});
                }
            }
        }
        return access_nodes;
    };

    for (int i = 0; i < nodes_count; ++i) {
        forward_access_nodes[i] = compute_access_nodes(i, true);
        backward_access_nodes[i] = compute_access_nodes(i, false);
    }

    // 3. Compute Distance Table using full Dijkstra on original_graph (one tree per transit origin)
    size_t n = original_graph.size();
    for (int origin : transit_nodes) {
        std::vector<double> dist(n, std::numeric_limits<double>::infinity());
        dist[origin] = 0.0;
        using PQItem = std::pair<double, int>;
        std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> pq;
        pq.push({0.0, origin});
        while (!pq.empty()) {
            auto [d, u] = pq.top();
            pq.pop();
            if (d > dist[u]) continue;
            for (const auto& [v, w] : original_graph[u]) {
                double nd = d + w;
                if (nd < dist[v]) {
                    dist[v] = nd;
                    pq.push({nd, v});
                }
            }
        }
        for (int target : transit_nodes) {
            distance_table[{origin, target}] = dist[target];
        }
    }
}

TNRGraph::TNRGraph(int nodes_count,
                   const std::vector<int>& ranks,
                   const std::vector<std::unordered_map<int, double>>& forward_graph,
                   const std::vector<std::unordered_map<int, double>>& backward_graph,
                   const std::unordered_map<std::pair<int, int>, int, pair_hash>& shortcuts,
                   const std::optional<std::vector<std::unordered_map<int, double>>>& original_graph,
                   const std::set<int>& transit_nodes,
                   const std::unordered_map<std::pair<int, int>, double, pair_hash>& distance_table,
                   const std::vector<std::unordered_map<int, double>>& forward_access_nodes,
                   const std::vector<std::unordered_map<int, double>>& backward_access_nodes)
    : CHGraph(nodes_count, ranks, forward_graph, backward_graph, shortcuts, original_graph),
      transit_nodes(transit_nodes), distance_table(distance_table),
      forward_access_nodes(forward_access_nodes), backward_access_nodes(backward_access_nodes) {}

std::optional<GraphResult> TNRGraph::local_search(int origin_id, int destination_id, double upper_bound, bool length_only) const {
    std::unordered_map<int, double> forward_distances, backward_distances;
    std::unordered_map<int, int> forward_parent, backward_parent;
    forward_distances[origin_id] = 0.0;
    if (!length_only) forward_parent[origin_id] = -1;
    backward_distances[destination_id] = 0.0;
    if (!length_only) backward_parent[destination_id] = -1;

    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> forward_open_leaves, backward_open_leaves;
    forward_open_leaves.push({0.0, origin_id});
    backward_open_leaves.push({0.0, destination_id});

    double best_dist = upper_bound;
    int meeting_node = -1;

    while (!forward_open_leaves.empty() || !backward_open_leaves.empty()) {
        if (!forward_open_leaves.empty()) {
            auto [current_distance, current_id] = forward_open_leaves.top();
            forward_open_leaves.pop();

            if (current_distance > best_dist) {
                while (!forward_open_leaves.empty()) forward_open_leaves.pop();
            } else if (transit_nodes.find(current_id) == transit_nodes.end()) {
                double current_rank = get_rank(current_id);
                const auto& neighbors = (current_id < nodes_count) ? forward_graph[current_id] : original_graph[current_id];
                for (const auto& [neighbor_id, weight] : neighbors) {
                    double neighbor_rank = get_rank(neighbor_id);
                    if (neighbor_rank <= current_rank && neighbor_id < nodes_count) continue;

                    double new_dist = current_distance + weight;
                    if (forward_distances.find(neighbor_id) == forward_distances.end() || new_dist < forward_distances[neighbor_id]) {
                        forward_distances[neighbor_id] = new_dist;
                        if (!length_only) forward_parent[neighbor_id] = current_id;
                        forward_open_leaves.push({new_dist, neighbor_id});
                        if (backward_distances.find(neighbor_id) != backward_distances.end() && new_dist + backward_distances[neighbor_id] < best_dist) {
                            best_dist = new_dist + backward_distances[neighbor_id];
                            meeting_node = neighbor_id;
                        }
                    }
                }
            }
        }

        if (!backward_open_leaves.empty()) {
            auto [current_distance, current_id] = backward_open_leaves.top();
            backward_open_leaves.pop();

            if (current_distance > best_dist) {
                while (!backward_open_leaves.empty()) backward_open_leaves.pop();
            } else if (transit_nodes.find(current_id) == transit_nodes.end()) {
                double current_rank = get_rank(current_id);
                const auto& neighbors = (current_id < nodes_count) ? backward_graph[current_id] : original_graph[current_id];
                for (const auto& [neighbor_id, weight] : neighbors) {
                    double neighbor_rank = get_rank(neighbor_id);
                    if (neighbor_rank <= current_rank && neighbor_id < nodes_count) continue;

                    double new_dist = current_distance + weight;
                    if (backward_distances.find(neighbor_id) == backward_distances.end() || new_dist < backward_distances[neighbor_id]) {
                        backward_distances[neighbor_id] = new_dist;
                        if (!length_only) backward_parent[neighbor_id] = current_id;
                        backward_open_leaves.push({new_dist, neighbor_id});
                        if (forward_distances.find(neighbor_id) != forward_distances.end() && new_dist + forward_distances[neighbor_id] < best_dist) {
                            best_dist = new_dist + forward_distances[neighbor_id];
                            meeting_node = neighbor_id;
                        }
                    }
                }
            }
        }

        double forward_min = forward_open_leaves.empty() ? std::numeric_limits<double>::infinity() : forward_open_leaves.top().first;
        double backward_min = backward_open_leaves.empty() ? std::numeric_limits<double>::infinity() : backward_open_leaves.top().first;
        if (forward_min > best_dist && backward_min > best_dist) break;
    }

    if (length_only) {
        return GraphResult{{}, best_dist};
    }

    if (meeting_node != -1) {
        std::vector<int> path = reconstruct_ch_path(origin_id, destination_id, meeting_node, forward_parent, backward_parent);
        return GraphResult{path, best_dist};
    }

    return std::nullopt;
}

GraphResult TNRGraph::search(int origin_id, int destination_id, bool length_only) const {
    if (origin_id == destination_id) {
        return {{origin_id}, 0.0};
    }

    std::unordered_map<int, double> f_access, b_access;

    // Forward Access Nodes
    if (origin_id < nodes_count) {
        f_access = forward_access_nodes[origin_id];
    } else {
        // Compute for added node
        std::unordered_map<int, double> distances;
        distances[origin_id] = 0.0;
        using PQItem = std::pair<double, int>;
        std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
        open_leaves.push({0.0, origin_id});
        while (!open_leaves.empty()) {
            auto [current_distance, current_id] = open_leaves.top();
            open_leaves.pop();
            if (transit_nodes.find(current_id) != transit_nodes.end()) {
                if (f_access.find(current_id) == f_access.end() || current_distance < f_access[current_id]) {
                    f_access[current_id] = current_distance;
                }
                continue;
            }
            double current_rank = get_rank(current_id);
            const auto& neighbors = (current_id < nodes_count) ? forward_graph[current_id] : original_graph[current_id];
            for (const auto& [neighbor_id, weight] : neighbors) {
                if (get_rank(neighbor_id) <= current_rank && neighbor_id < nodes_count) continue;
                double new_dist = current_distance + weight;
                if (distances.find(neighbor_id) == distances.end() || new_dist < distances[neighbor_id]) {
                    distances[neighbor_id] = new_dist;
                    open_leaves.push({new_dist, neighbor_id});
                }
            }
        }
    }

    // Backward Access Nodes
    if (destination_id < nodes_count) {
        b_access = backward_access_nodes[destination_id];
    } else {
        // Compute for added node
        std::unordered_map<int, double> distances;
        distances[destination_id] = 0.0;
        using PQItem = std::pair<double, int>;
        std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
        open_leaves.push({0.0, destination_id});
        while (!open_leaves.empty()) {
            auto [current_distance, current_id] = open_leaves.top();
            open_leaves.pop();
            if (transit_nodes.find(current_id) != transit_nodes.end()) {
                if (b_access.find(current_id) == b_access.end() || current_distance < b_access[current_id]) {
                    b_access[current_id] = current_distance;
                }
                continue;
            }
            double current_rank = get_rank(current_id);
            const auto& neighbors = (current_id < nodes_count) ? backward_graph[current_id] : original_graph[current_id];
            for (const auto& [neighbor_id, weight] : neighbors) {
                if (get_rank(neighbor_id) <= current_rank && neighbor_id < nodes_count) continue;
                double new_dist = current_distance + weight;
                if (distances.find(neighbor_id) == distances.end() || new_dist < distances[neighbor_id]) {
                    distances[neighbor_id] = new_dist;
                    open_leaves.push({new_dist, neighbor_id});
                }
            }
        }
    }

    double best_dist = std::numeric_limits<double>::infinity();
    for (const auto& [t_f, d_f] : f_access) {
        for (const auto& [t_b, d_b] : b_access) {
            auto it = distance_table.find({t_f, t_b});
            if (it != distance_table.end()) {
                double total = d_f + it->second + d_b;
                if (total < best_dist) {
                    best_dist = total;
                }
            }
        }
    }

    auto local_res = local_search(origin_id, destination_id, best_dist, length_only);
    if (local_res.has_value()) {
        return local_res.value();
    }

    // Fallback to CH search for path reconstruction if global TNR path was found but local search failed
    // (should only happen if length_only=false and meeting_node was not found in local search)
    return CHGraph::search(origin_id, destination_id);
}
