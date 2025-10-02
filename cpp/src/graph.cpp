#include <iostream>
#include <vector>
#include <unordered_map>
#include <queue>
#include <limits>
#include <stdexcept>
#include <algorithm>
#include "graph.hpp"

// Helper function to reconstruct the path
std::vector<int> reconstruct_path(int destination_id, const std::vector<int>& predecessor) {
    std::vector<int> path;
    int current = destination_id;
    while (current != -1) {
        path.push_back(current);
        current = predecessor[current];
    }
    std::reverse(path.begin(), path.end());
    return path;
}

GraphResult dijkstra(const Graph& graph, int origin_id, int destination_id) {
    int n = graph.size();

    // Basic input check
    if (origin_id < 0 || origin_id >= n || destination_id < 0 || destination_id >= n) {
        throw std::invalid_argument("Invalid origin or destination node id");
    }

    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<double> branch_tip_distances(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessor(n, -1);

    distance_matrix[origin_id] = 0.0;
    branch_tip_distances[origin_id] = 0.0;

    while (true) {
        // Find node with minimum distance in branch_tip_distances
        double current_distance = std::numeric_limits<double>::infinity();
        int current_id = -1;

        for (int i = 0; i < n; ++i) {
            if (branch_tip_distances[i] < current_distance) {
                current_distance = branch_tip_distances[i];
                current_id = i;
            }
        }

        if (current_distance == std::numeric_limits<double>::infinity()) {
            throw std::runtime_error("No path exists between origin and destination.");
        }

        // Mark node as visited
        branch_tip_distances[current_id] = std::numeric_limits<double>::infinity();

        if (current_id == destination_id) {
            break;
        }

        for (const auto& [connected_id, connected_distance] : graph[current_id]) {
            double possible_distance = current_distance + connected_distance;
            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessor[connected_id] = current_id;
                branch_tip_distances[connected_id] = possible_distance;
            }
        }
    }

    return GraphResult{
        reconstruct_path(destination_id, predecessor),
        distance_matrix[destination_id]
    };
}

GraphResult dijkstra_makowski(const Graph& graph, int origin_id, int destination_id) {
    int n = graph.size();

    // Input validation
    if (origin_id < 0 || origin_id >= n || destination_id < 0 || destination_id >= n) {
        throw std::invalid_argument("Invalid origin or destination node id");
    }

    double infinity = std::numeric_limits<double>::infinity();

    std::vector<double> distance_matrix(n, infinity);
    std::vector<int> predecessors(n, -1);
    distance_matrix[origin_id] = 0.0;

    // Min-heap (priority queue) of (distance, node_id)
    std::priority_queue<
        std::pair<double, int>,
        std::vector<std::pair<double, int>>,
        std::greater<std::pair<double, int>>
    > open_leaves;

    open_leaves.push({0.0, origin_id});

    while (!open_leaves.empty()) {
        auto [current_distance, current_id] = open_leaves.top();
        open_leaves.pop();

        // Early termination if destination is reached
        if (current_id == destination_id) {
            break;
        }

        // Only process if current distance is the best known
        if (current_distance == distance_matrix[current_id]) {
            const auto& neighbors = graph[current_id];
            for (const auto& [neighbor_id, edge_weight] : neighbors) {
                double new_distance = current_distance + edge_weight;
                if (new_distance < distance_matrix[neighbor_id]) {
                    distance_matrix[neighbor_id] = new_distance;
                    predecessors[neighbor_id] = current_id;
                    open_leaves.push({new_distance, neighbor_id});
                }
            }
        }
    }

    if (distance_matrix[destination_id] == infinity) {
        throw std::runtime_error("No path between origin and destination.");
    }

    return {
        reconstruct_path(destination_id, predecessors),
        distance_matrix[destination_id]
    };
}


int main() {
    // Example graph
    Graph graph = {
        {{1, 1.0}, {2, 4.0}},      // Node 0
        {{0, 1.0}, {2, 2.0}, {3, 5.0}}, // Node 1
        {{0, 4.0}, {1, 2.0}, {3, 1.0}}, // Node 2
        {{1, 5.0}, {2, 1.0}}       // Node 3
    };

    int origin = 0;
    int destination = 3;

    try {
        GraphResult result = dijkstra(graph, origin, destination);
        std::cout << "Path: ";
        for (int node : result.path) {
            std::cout << node << " ";
        }
        std::cout << "\nLength: " << result.length << "\n";
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << "\n";
    }

    try {
        GraphResult result_makowski = dijkstra_makowski(graph, origin, destination);
        std::cout << "Makowski Path: ";
        for (int node : result_makowski.path) {
            std::cout << node << " ";
        }
        std::cout << "\nMakowski Length: " << result_makowski.length << "\n";
    } catch (const std::exception& ex) {
        std::cerr << "Error in Makowski: " << ex.what() << "\n";
    }

    return 0;
}