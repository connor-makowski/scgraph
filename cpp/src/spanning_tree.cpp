#include <iostream>
#include <vector>
#include <unordered_map>
#include <queue>
#include <limits>
#include "spanning_tree.hpp"

// Custom comparator for priority queue (min-heap)
struct MinHeapCompare {
    bool operator()(const std::pair<double, int>& a, const std::pair<double, int>& b) {
        return a.first > b.first; // min-heap based on distance
    }
};

SpanningTreeResult makowskis_spanning_tree(const Graph& graph, int node_id) {
    int n = graph.size();

    // Input validation
    if (node_id < 0 || node_id >= n) {
        throw std::invalid_argument("node_id must be a valid node index");
    }

    // Initialize distance and predecessor vectors
    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessors(n, -1);

    distance_matrix[node_id] = 0;

    // Priority queue: (distance, node_id)
    std::priority_queue<std::pair<double, int>,
                        std::vector<std::pair<double, int>>,
                        MinHeapCompare> open_leaves;

    open_leaves.push({0.0, node_id});

    while (!open_leaves.empty()) {
        auto [current_distance, current_id] = open_leaves.top();
        open_leaves.pop();

        const auto& neighbors = graph[current_id];
        for (const auto& [connected_id, connected_distance] : neighbors) {
            double possible_distance = current_distance + connected_distance;

            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessors[connected_id] = current_id;
                open_leaves.push({possible_distance, connected_id});
            }
        }
    }

    return SpanningTreeResult{node_id, predecessors, distance_matrix};
}

int main() {
    // Example graph as list of maps (like Python list[dict])
    Graph graph = {
        {{1, 2.0}, {2, 5.0}},      // Node 0 connects to 1 (2.0), 2 (5.0)
        {{0, 2.0}, {2, 1.0}},      // Node 1 connects to 0, 2
        {{0, 5.0}, {1, 1.0}},      // Node 2 connects to 0, 1
    };

    int origin = 0;

    try {
        SpanningTreeResult result = makowskis_spanning_tree(graph, origin);

        std::cout << "Node ID: " << result.node_id << "\n";
        std::cout << "Predecessors: ";
        for (int p : result.predecessors) {
            std::cout << p << " ";
        }
        std::cout << "\nDistances: ";
        for (double d : result.distance_matrix) {
            if (d == std::numeric_limits<double>::infinity()) {
                std::cout << "inf ";
            } else {
                std::cout << d << " ";
            }
        }
        std::cout << "\n";

    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << "\n";
    }

    return 0;
}