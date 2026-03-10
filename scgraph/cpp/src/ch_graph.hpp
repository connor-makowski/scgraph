#pragma once
#include <vector>
#include <unordered_map>
#include <utility>
#include <string>
#include <functional>
#include <optional>
#include "graph.hpp"

// Custom hash for std::pair<int, int> to use in unordered_map
struct pair_hash {
    inline std::size_t operator()(const std::pair<int, int> & v) const {
        return v.first * 31 + v.second;
    }
};

class CHGraph {
private:
    int nodes_count;
    std::vector<int> ranks;
    std::vector<std::unordered_map<int, double>> forward_graph;
    std::vector<std::unordered_map<int, double>> backward_graph;
    std::unordered_map<std::pair<int, int>, int, pair_hash> shortcuts;
    std::vector<std::unordered_map<int, double>> original_graph;

    // Preprocessing state
    std::vector<std::unordered_map<int, double>> contracting_graph;
    std::vector<std::unordered_map<int, double>> contracting_inverse_graph;
    std::vector<bool> contracted;
    int contracted_count;

    // Helper methods
    double get_rank(int node_id) const;
    std::unordered_map<int, double> witness_search(int start_node, int avoid_node, double max_dist) const;
    std::pair<int, std::vector<std::tuple<int, int, double, int>>> count_shortcuts(int v) const;
    double default_heuristic(int node_id) const;
    void preprocess(std::function<double(CHGraph*, int)> heuristic_fn = nullptr);
    std::vector<int> reconstruct_ch_path(int origin_id, int destination_id, int meeting_node,
                                        const std::unordered_map<int, int>& f_parent,
                                        const std::unordered_map<int, int>& b_parent) const;
    std::vector<int> unpack_shortcut(int u, int w) const;

public:
    // Constructors
    CHGraph(const std::vector<std::unordered_map<int, double>>& graph,
            std::function<double(CHGraph*, int)> heuristic_fn = nullptr);
    
    // Constructor for loading from saved state
    CHGraph(int nodes_count,
            const std::vector<int>& ranks,
            const std::vector<std::unordered_map<int, double>>& forward_graph,
            const std::vector<std::unordered_map<int, double>>& backward_graph,
            const std::unordered_map<std::pair<int, int>, int, pair_hash>& shortcuts,
            const std::optional<std::vector<std::unordered_map<int, double>>>& original_graph);

    // Graph modification
    int add_node(const std::unordered_map<int, double>& node_dict = {}, bool symmetric = false);

    // Search
    GraphResult search(int origin_id, int destination_id) const;
    GraphResult get_shortest_path(int origin_id, int destination_id) const {
        return search(origin_id, destination_id);
    }

    // Accessors for serialization
    int get_nodes_count() const { return nodes_count; }
    const std::vector<int>& get_ranks() const { return ranks; }
    const std::vector<std::unordered_map<int, double>>& get_forward_graph() const { return forward_graph; }
    const std::vector<std::unordered_map<int, double>>& get_backward_graph() const { return backward_graph; }
    const std::unordered_map<std::pair<int, int>, int, pair_hash>& get_shortcuts() const { return shortcuts; }
    const std::vector<std::unordered_map<int, double>>& get_original_graph() const { return original_graph; }
};
