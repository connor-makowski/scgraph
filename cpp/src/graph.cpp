#include "graph.hpp"
#include <queue>
#include <limits>
#include <stdexcept>
#include <algorithm>
#include <iostream>

// Helper function to get set from variant
static std::set<int> get_origin_ids(const std::variant<int, std::set<int>>& origin_id) {
    if (std::holds_alternative<int>(origin_id)) {
        return {std::get<int>(origin_id)};
    }
    return std::get<std::set<int>>(origin_id);
}

// Static helper to convert unordered_map representation to vector of pairs
std::vector<std::vector<std::pair<int, double>>> Graph::serialize_graph(
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

// Convert internal representation back to unordered_map for a single node
std::unordered_map<int, double> Graph::get_adjacency_dict(int idx) const {
    if (idx < 0 || idx >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Index out of range");
    }
    
    std::unordered_map<int, double> result;
    for (const auto& [dest, dist] : graph[idx]) {
        result[dest] = dist;
    }
    return result;
}

// Constructor
Graph::Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate)
    : graph(serialize_graph(graph_data)) {
    reset_cache();
    if (validate) {
        this->validate();
    }
}

// Utility methods
void Graph::input_check(const std::variant<int, std::set<int>>& origin_id, int destination_id) const {
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

std::vector<int> Graph::reconstruct_path(int destination_id, const std::vector<int>& predecessor) const {
    std::vector<int> output_path;
    output_path.push_back(destination_id);
    
    while (predecessor[destination_id] != -1) {
        destination_id = predecessor[destination_id];
        output_path.push_back(destination_id);
    }
    
    std::reverse(output_path.begin(), output_path.end());
    return output_path;
}

void Graph::cycle_check(const std::vector<int>& predecessor_matrix, int node_id) const {
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

bool Graph::connected_check(int origin_id) const {
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
    
    return *std::min_element(visited.begin(), visited.end()) == 1;
}

void Graph::validate(bool check_symmetry, bool check_connected) {
    check_symmetry = check_symmetry || check_connected;
    
    size_t len_graph = graph.size();
    
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
            
            if (check_symmetry) {
                // Find the reverse edge
                bool found = false;
                double reverse_dist = 0.0;
                for (const auto& [rev_dest, rev_dist] : graph[dest_id]) {
                    if (rev_dest == static_cast<int>(origin_id)) {
                        found = true;
                        reverse_dist = rev_dist;
                        break;
                    }
                }
                
                if (!found || reverse_dist != distance) {
                    throw std::invalid_argument("Graph is not symmetric: distance from " + 
                        std::to_string(origin_id) + " to " + std::to_string(dest_id) + 
                        " is " + std::to_string(distance) + " but reverse is " + 
                        (found ? std::to_string(reverse_dist) : "missing"));
                }
            }
        }
    }
    
    if (check_connected && !connected_check()) {
        throw std::runtime_error("Graph is not fully connected");
    }
}

void Graph::reset_cache() {
    cache.clear();
    cache.resize(graph.size());
}

const std::unordered_map<int, double> Graph::get(int idx) const {
    return get_adjacency_dict(idx);
}

const std::vector<std::unordered_map<int, double>> Graph::get_graph() const {
    std::vector<std::unordered_map<int, double>> result;
    result.reserve(graph.size());
    
    for (size_t i = 0; i < graph.size(); ++i) {
        result.push_back(get_adjacency_dict(i));
    }
    
    return result;
}

// Graph modification methods
int Graph::add_node(const std::unordered_map<int, double>& node_dict, bool symmetric) {
    // Convert unordered_map to vector of pairs
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

void Graph::add_edge(int origin_id, int destination_id, double distance, bool symmetric) {
    if (origin_id >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Origin node id is not in the graph");
    }
    if (destination_id >= static_cast<int>(graph.size())) {
        throw std::out_of_range("Destination node id is not in the graph");
    }
    
    // Check if edge already exists and update, otherwise add
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

std::unordered_map<int, double> Graph::remove_node(bool symmetric_node) {
    if (graph.empty()) {
        throw std::runtime_error("Graph is empty, cannot remove node");
    }
    
    int node_id = graph.size() - 1;
    
    if (symmetric_node) {
        // Only remove edges from nodes that this node points to
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
        // Remove edges from all nodes that point to this node
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
    
    // Convert removed edges to unordered_map
    std::unordered_map<int, double> removed_dict;
    for (const auto& [dest, dist] : graph[node_id]) {
        removed_dict[dest] = dist;
    }
    
    graph.pop_back();
    reset_cache();
    
    return removed_dict;
}

std::optional<double> Graph::remove_edge(int origin_id, int destination_id, bool symmetric) {
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

// Tree algorithms
TreeData Graph::get_shortest_path_tree(const std::variant<int, std::set<int>>& origin_id) {
    input_check(origin_id, 0);
    auto origin_ids = get_origin_ids(origin_id);
    
    size_t n = graph.size();
    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessor(n, -1);
    
    using PQElement = std::pair<double, int>;
    std::priority_queue<PQElement, std::vector<PQElement>, std::greater<PQElement>> open_leaves;
    
    for (int oid : origin_ids) {
        distance_matrix[oid] = 0.0;
        open_leaves.push({0.0, oid});
    }
    
    while (!open_leaves.empty()) {
        auto [current_distance, current_id] = open_leaves.top();
        open_leaves.pop();
        
        if (current_distance > distance_matrix[current_id]) {
            continue;
        }
        
        for (const auto& [connected_id, connected_distance] : graph[current_id]) {
            double possible_distance = current_distance + connected_distance;
            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessor[connected_id] = current_id;
                open_leaves.push({possible_distance, connected_id});
            }
        }
    }
    
    return TreeData{origin_id, predecessor, distance_matrix};
}

GraphResult Graph::get_tree_path(int origin_id, int destination_id, const TreeData& tree_data, bool length_only) {
    // Check if origin matches
    bool origin_matches = false;
    if (std::holds_alternative<int>(tree_data.origin_id)) {
        origin_matches = (std::get<int>(tree_data.origin_id) == origin_id);
    } else {
        const auto& origin_set = std::get<std::set<int>>(tree_data.origin_id);
        origin_matches = origin_set.count(origin_id) > 0;
    }
    
    if (!origin_matches) {
        throw std::invalid_argument("The origin node must be the same as the spanning node for this function to work.");
    }
    
    double destination_distance = tree_data.distance_matrix[destination_id];
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

// Shortest path algorithms
GraphResult Graph::dijkstra(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);

    const size_t n = graph.size();
    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessor(n, -1);

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
        if (current_id == destination_id) break;
        for (const auto& [connected_id, connected_distance] : graph[current_id]) {
            const double possible_distance = current_distance + connected_distance;
            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessor[connected_id] = current_id;
                open_leaves.emplace(possible_distance, connected_id);
            }
        }
    }

    if (distance_matrix[destination_id] == std::numeric_limits<double>::infinity()) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }

    return GraphResult{
        reconstruct_path(destination_id, predecessor),
        distance_matrix[destination_id]
    };
}

GraphResult Graph::dijkstra_negative(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                                     std::optional<int> cycle_check_iterations) {
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);
    
    size_t n = graph.size();
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
                cycle_check(predecessor, current_id);
            }
            
            for (const auto& [connected_id, connected_distance] : graph[current_id]) {
                double possible_distance = current_distance + connected_distance;
                if (possible_distance < distance_matrix[connected_id]) {
                    distance_matrix[connected_id] = possible_distance;
                    predecessor[connected_id] = current_id;
                    open_leaves.push({possible_distance, connected_id});
                }
            }
        }
    }
    
    if (distance_matrix[destination_id] == std::numeric_limits<double>::infinity()) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }
    
    return GraphResult{
        reconstruct_path(destination_id, predecessor),
        distance_matrix[destination_id]
    };
}

GraphResult Graph::a_star(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                         std::function<double(int, int)> heuristic_fn) {
    if (!heuristic_fn) {
        return dijkstra(origin_id, destination_id);
    }
    
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);
    
    size_t n = graph.size();
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
        
        if (current_id == destination_id) {
            break;
        }
        
        if (visited[current_id] == 1) {
            continue;
        }
        visited[current_id] = 1;
        
        double current_distance = distance_matrix[current_id];
        for (const auto& [connected_id, connected_distance] : graph[current_id]) {
            double possible_distance = current_distance + connected_distance;
            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessor[connected_id] = current_id;
                open_leaves.push({
                    possible_distance + heuristic_fn(connected_id, destination_id),
                    connected_id
                });
            }
        }
    }
    
    if (current_id != destination_id) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }
    
    return GraphResult{
        reconstruct_path(destination_id, predecessor),
        distance_matrix[destination_id]
    };
}

GraphResult Graph::bellman_ford(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);
    
    size_t n = graph.size();
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
            
            for (const auto& [connected_id, connected_distance] : graph[current_id]) {
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
    
    if (distance_matrix[destination_id] == std::numeric_limits<double>::infinity()) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }
    
    return GraphResult{
        reconstruct_path(destination_id, predecessor),
        distance_matrix[destination_id]
    };
}

GraphResult Graph::bmssp(const std::variant<int, std::set<int>>& origin_id, int destination_id) {
    // Print a warning that bmssp is not supported when using C++ backend
    std::cerr << "Warning: bmssp is not supported in the C++ backend. Falling back to Dijkstra's algorithm." << std::endl;
    return dijkstra(origin_id, destination_id);
}

GraphResult Graph::get_set_cached_shortest_path(int origin_id, int destination_id, bool length_only) {
    // Check if cache is empty (using default-constructed TreeData as sentinel)
    bool cache_empty = cache[origin_id].predecessors.empty();
    
    if (cache_empty) {
        cache[origin_id] = get_shortest_path_tree(origin_id);
    }
    
    return get_tree_path(origin_id, destination_id, cache[origin_id], length_only);
}