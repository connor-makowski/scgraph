#include "graph_utils.hpp"
#include <stdexcept>
#include <algorithm>
#include <string>

std::set<int> get_origin_ids(const std::variant<int, std::set<int>>& origin_id) {
    if (std::holds_alternative<int>(origin_id)) {
        return {std::get<int>(origin_id)};
    }
    return std::get<std::set<int>>(origin_id);
}

std::vector<std::vector<std::pair<int, double>>> GraphUtils::serialize_graph(
    const std::vector<std::unordered_map<int, double>>& input_graph) {
    std::vector<std::vector<std::pair<int, double>>> serialized;
    serialized.reserve(input_graph.size());

    for (const auto& node_dict : input_graph) {
        std::vector<std::pair<int, double>> edges;
        edges.reserve(node_dict.size());
        for (const auto& [dest, dist] : node_dict) {
            edges.emplace_back(dest, dist);
        }
        serialized.push_back(std::move(edges));
    }

    return serialized;
}

std::unordered_map<int, double> GraphUtils::get_adjacency_dict(int idx) const {
    if (idx < 0 || idx >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Index out of range");
    }

    std::unordered_map<int, double> result;
    for (const auto& [dest, dist] : graph[idx]) {
        result[dest] = dist;
    }
    return result;
}

void GraphUtils::input_check(const std::variant<int, std::set<int>>& origin_id, int destination_id) const {
    auto origin_ids = get_origin_ids(origin_id);

    for (int oid : origin_ids) {
        if (oid < 0 || oid >= static_cast<int>(graph.size())) {
            throw std::invalid_argument("Origin node (" + std::to_string(oid) + ") is not in this graph");
        }
    }

    if (destination_id < 0 || destination_id >= static_cast<int>(graph.size())) {
        throw std::invalid_argument("Destination node (" + std::to_string(destination_id) + ") is not in this graph");
    }
}

std::vector<int> GraphUtils::reconstruct_path(int destination_id, const std::vector<int>& predecessor) const {
    std::vector<int> output_path;
    output_path.push_back(destination_id);

    while (predecessor[destination_id] != -1) {
        destination_id = predecessor[destination_id];
        output_path.push_back(destination_id);
    }

    std::reverse(output_path.begin(), output_path.end());
    return output_path;
}

void GraphUtils::cycle_check(const std::vector<int>& predecessor_matrix, int node_id) const {
    int cycle_id = node_id;
    while (true) {
        cycle_id = predecessor_matrix[cycle_id];
        if (cycle_id == -1) {
            return;
        }
        if (cycle_id == node_id) {
            throw std::runtime_error("Cycle detected in the graph at node " + std::to_string(node_id));
        }
    }
}

void GraphUtils::ensure_inverse_graph() {
    if (inverse_graph_computed) return;
    inverse_graph.assign(graph.size(), {});
    for (size_t origin_id = 0; origin_id < graph.size(); ++origin_id) {
        for (const auto& [dest_id, distance] : graph[origin_id]) {
            inverse_graph[dest_id].emplace_back(static_cast<int>(origin_id), distance);
        }
    }
    inverse_graph_computed = true;
}

bool GraphUtils::connected_check(int origin_id) {
    ensure_inverse_graph();

    // Forward traversal
    std::vector<int> visited(graph.size(), 0);
    std::vector<int> open_leaves = {origin_id};
    while (!open_leaves.empty()) {
        int current_id = open_leaves.back();
        open_leaves.pop_back();
        visited[current_id] = 1;
        for (const auto& [connected_id, _] : graph[current_id]) {
            if (visited[connected_id] == 0) {
                open_leaves.push_back(connected_id);
            }
        }
    }

    // Inverse traversal
    std::vector<int> inverse_visited(inverse_graph.size(), 0);
    std::vector<int> inverse_open_leaves = {origin_id};
    while (!inverse_open_leaves.empty()) {
        int current_id = inverse_open_leaves.back();
        inverse_open_leaves.pop_back();
        inverse_visited[current_id] = 1;
        for (const auto& [connected_id, _] : inverse_graph[current_id]) {
            if (inverse_visited[connected_id] == 0) {
                inverse_open_leaves.push_back(connected_id);
            }
        }
    }

    return *std::min_element(visited.begin(), visited.end()) == 1 &&
           *std::min_element(inverse_visited.begin(), inverse_visited.end()) == 1;
}

bool GraphUtils::symmetric_check() const {
    for (size_t origin_id = 0; origin_id < graph.size(); ++origin_id) {
        for (const auto& [dest_id, distance] : graph[origin_id]) {
            bool found = false;
            for (const auto& [rev_dest, rev_dist] : graph[dest_id]) {
                if (rev_dest == static_cast<int>(origin_id)) {
                    if (rev_dist != distance) return false;
                    found = true;
                    break;
                }
            }
            if (!found) return false;
        }
    }
    return true;
}

void GraphUtils::validate(bool check_symmetry, bool check_connected) {
    size_t len_graph = graph.size();
    if (len_graph == 0) {
        throw std::invalid_argument("The provided graph must contain at least one node");
    }
    for (size_t origin_id = 0; origin_id < len_graph; ++origin_id) {
        for (const auto& [dest_id, distance] : graph[origin_id]) {
            if (dest_id < 0 || dest_id >= static_cast<int>(len_graph)) {
                throw std::invalid_argument("Destination id " + std::to_string(dest_id) +
                    " at origin " + std::to_string(origin_id) + " is invalid");
            }
            if (distance < 0) {
                throw std::invalid_argument("Distance must be non-negative at origin " +
                    std::to_string(origin_id));
            }
        }
    }

    if (check_symmetry && !symmetric_check()) {
        throw std::invalid_argument("The provided graph is not symmetric");
    }
    if (check_connected && !connected_check()) {
        throw std::runtime_error("The provided graph is not fully connected");
    }
}

void GraphUtils::reset_cache() {
    cache.clear();
    cache.resize(graph.size());
}

const std::unordered_map<int, double> GraphUtils::get(int idx) const {
    return get_adjacency_dict(idx);
}

double GraphUtils::get_path_weight(const std::vector<int>& path) const {
    double total = 0.0;
    for (size_t i = 0; i + 1 < path.size(); ++i) {
        int origin = path[i];
        int dest = path[i + 1];
        bool found = false;
        for (const auto& [d, w] : graph[origin]) {
            if (d == dest) {
                total += w;
                found = true;
                break;
            }
        }
        if (!found) {
            throw std::invalid_argument(
                "No edge from node " + std::to_string(origin) +
                " to node " + std::to_string(dest)
            );
        }
    }
    return total;
}

const std::vector<std::unordered_map<int, double>> GraphUtils::get_graph() const {
    std::vector<std::unordered_map<int, double>> result;
    result.reserve(graph.size());

    for (size_t i = 0; i < graph.size(); ++i) {
        result.push_back(get_adjacency_dict(i));
    }

    return result;
}

int GraphUtils::add_node(const std::unordered_map<int, double>& node_dict, bool symmetric) {
    std::vector<std::pair<int, double>> edges;
    edges.reserve(node_dict.size());
    for (const auto& [dest_id, distance] : node_dict) {
        edges.emplace_back(dest_id, distance);
    }

    graph.push_back(std::move(edges));
    int new_node_id = graph.size() - 1;

    if (symmetric) {
        for (const auto& [dest_id, distance] : node_dict) {
            graph[dest_id].emplace_back(new_node_id, distance);
        }
    }

    reset_cache();
    return new_node_id;
}

void GraphUtils::add_edge(int origin_id, int destination_id, double distance, bool symmetric) {
    if (origin_id >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Origin node id is not in the graph");
    }
    if (destination_id >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Destination node id is not in the graph");
    }

    bool found = false;
    for (auto& [dest, dist] : graph[origin_id]) {
        if (dest == destination_id) {
            dist = distance;
            found = true;
            break;
        }
    }
    if (!found) {
        graph[origin_id].emplace_back(destination_id, distance);
    }

    if (symmetric) {
        found = false;
        for (auto& [dest, dist] : graph[destination_id]) {
            if (dest == origin_id) {
                dist = distance;
                found = true;
                break;
            }
        }
        if (!found) {
            graph[destination_id].emplace_back(origin_id, distance);
        }
    }

    reset_cache();
}

std::unordered_map<int, double> GraphUtils::remove_node(bool symmetric_node) {
    if (graph.empty()) {
        throw std::runtime_error("Graph is empty, cannot remove node");
    }

    int node_id = graph.size() - 1;

    if (symmetric_node) {
        for (const auto& [dest_id, _] : graph[node_id]) {
            auto& dest_edges = graph[dest_id];
            dest_edges.erase(
                std::remove_if(dest_edges.begin(), dest_edges.end(),
                    [node_id](const std::pair<int, double>& edge) {
                        return edge.first == node_id;
                    }),
                dest_edges.end()
            );
        }
    } else {
        for (auto& node_edges : graph) {
            node_edges.erase(
                std::remove_if(node_edges.begin(), node_edges.end(),
                    [node_id](const std::pair<int, double>& edge) {
                        return edge.first == node_id;
                    }),
                node_edges.end()
            );
        }
    }

    std::unordered_map<int, double> removed_dict;
    for (const auto& [dest, dist] : graph[node_id]) {
        removed_dict[dest] = dist;
    }

    graph.pop_back();
    reset_cache();

    return removed_dict;
}

std::optional<double> GraphUtils::remove_edge(int origin_id, int destination_id, bool symmetric) {
    if (origin_id >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Origin node id is not in the graph");
    }
    if (destination_id >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Destination node id is not in the graph");
    }

    std::optional<double> result;

    auto& origin_edges = graph[origin_id];
    for (auto it = origin_edges.begin(); it != origin_edges.end(); ++it) {
        if (it->first == destination_id) {
            result = it->second;
            origin_edges.erase(it);
            break;
        }
    }

    if (symmetric) {
        auto& dest_edges = graph[destination_id];
        dest_edges.erase(
            std::remove_if(dest_edges.begin(), dest_edges.end(),
                [origin_id](const std::pair<int, double>& edge) {
                    return edge.first == origin_id;
                }),
            dest_edges.end()
        );
    }

    reset_cache();
    return result;
}
