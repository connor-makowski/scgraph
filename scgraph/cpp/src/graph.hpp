#pragma once
#include <vector>
#include <unordered_map>
#include <set>
#include <functional>
#include <optional>
#include <variant>
#include <utility>

struct GraphResult {
    std::vector<int> path;
    double length;
};

struct TreeData {
    std::variant<int, std::set<int>> origin_id;
    std::vector<int> predecessors;
    std::vector<double> distance_matrix;
};

class Graph {
private:
    // Internal representation: vector of vectors of (node_id, distance) pairs
    std::vector<std::vector<std::pair<int, double>>> graph;
    std::vector<TreeData> cache;

    // Helper methods for conversion
    static std::vector<std::vector<std::pair<int, double>>> serialize_graph(
        const std::vector<std::unordered_map<int, double>>& input_graph);
    std::unordered_map<int, double> get_adjacency_dict(int idx) const;

    // Utility methods
    void input_check(const std::variant<int, std::set<int>>& origin_id, int destination_id) const;
    std::vector<int> reconstruct_path(int destination_id, const std::vector<int>& predecessor) const;
    void cycle_check(const std::vector<int>& predecessor_matrix, int node_id) const;
    bool connected_check(int origin_id = 0) const;

public:
    // Constructor
    explicit Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate = false);

    // Validation
    void validate(bool check_symmetry = true, bool check_connected = true);
    
    // Cache management
    void reset_cache();

    // Access
    const std::unordered_map<int, double> get(int idx) const;
    int size() const { return graph.size(); }
    const std::vector<std::unordered_map<int, double>> get_graph() const;

    // Graph modification
    int add_node(const std::unordered_map<int, double>& node_dict = {}, bool symmetric = false);
    void add_edge(int origin_id, int destination_id, double distance, bool symmetric = false);
    std::unordered_map<int, double> remove_node(bool symmetric_node = false);
    std::optional<double> remove_edge(int origin_id, int destination_id, bool symmetric = false);

    // Tree algorithms
    TreeData get_shortest_path_tree(const std::variant<int, std::set<int>>& origin_id);
    GraphResult get_tree_path(int origin_id, int destination_id, const TreeData& tree_data, bool length_only = false);

    // Shortest path algorithms
    GraphResult dijkstra(const std::variant<int, std::set<int>>& origin_id, int destination_id);
    GraphResult dijkstra_negative(const std::variant<int, std::set<int>>& origin_id, int destination_id, 
                                  std::optional<int> cycle_check_iterations = std::nullopt);
    GraphResult a_star(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                      std::function<double(int, int)> heuristic_fn = nullptr);
    GraphResult bellman_ford(const std::variant<int, std::set<int>>& origin_id, int destination_id);
    GraphResult bmssp(const std::variant<int, std::set<int>>& origin_id, int destination_id);
    
    // Cached shortest path
    GraphResult get_set_cached_shortest_path(int origin_id, int destination_id, bool length_only = false);
};