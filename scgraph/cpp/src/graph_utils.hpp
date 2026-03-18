#pragma once
#include <vector>
#include <set>
#include <variant>
#include <unordered_map>
#include <utility>
#include <optional>
#include <functional>

struct GraphResult {
    std::vector<int> path;
    double length;
};

struct TreeData {
    std::variant<int, std::set<int>> origin_id;
    std::vector<int> predecessors;
    std::vector<double> distance_matrix;
};

// Custom hash for std::pair<int, int> to use in unordered_map
struct pair_hash {
    inline std::size_t operator()(const std::pair<int, int>& v) const {
        return v.first * 31 + v.second;
    }
};

// Helper function to get set from variant
std::set<int> get_origin_ids(const std::variant<int, std::set<int>>& origin_id);

class GraphUtils {
protected:
    // Internal representation: vector of vectors of (node_id, distance) pairs
    std::vector<std::vector<std::pair<int, double>>> graph;
    // Inverse graph (lazily computed)
    std::vector<std::vector<std::pair<int, double>>> inverse_graph;
    bool inverse_graph_computed = false;
    std::vector<TreeData> cache;

    // Helper methods for conversion
    static std::vector<std::vector<std::pair<int, double>>> serialize_graph(
        const std::vector<std::unordered_map<int, double>>& input_graph);
    std::unordered_map<int, double> get_adjacency_dict(int idx) const;

    // Utility methods
    void input_check(const std::variant<int, std::set<int>>& origin_id, int destination_id) const;
    std::vector<int> reconstruct_path(int destination_id, const std::vector<int>& predecessor) const;
    void cycle_check(const std::vector<int>& predecessor_matrix, int node_id) const;
    void ensure_inverse_graph();
    bool connected_check(int origin_id = 0);
    bool symmetric_check() const;

public:
    // Validation
    void validate(bool check_symmetry = true, bool check_connected = true);

    // Cache management
    void reset_cache();

    // Access
    const std::unordered_map<int, double> get(int idx) const;
    int size() const { return graph.size(); }
    const std::vector<std::unordered_map<int, double>> get_graph() const;
    const std::vector<TreeData>& get_cache() const { return cache; }
    void set_cache(const std::vector<TreeData>& new_cache) { cache = new_cache; }

    // Graph modification
    int add_node(const std::unordered_map<int, double>& node_dict = {}, bool symmetric = false);
    void add_edge(int origin_id, int destination_id, double distance, bool symmetric = false);
    std::unordered_map<int, double> remove_node(bool symmetric_node = false);
    std::optional<double> remove_edge(int origin_id, int destination_id, bool symmetric = false);
};
