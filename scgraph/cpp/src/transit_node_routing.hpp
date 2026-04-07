#pragma once
#include <vector>
#include <unordered_map>
#include <utility>
#include <set>
#include <optional>
#include "contraction_hierarchies.hpp"

class TNRGraph : public CHGraph {
private:
    std::set<int> transit_nodes;
    std::unordered_map<std::pair<int, int>, double, pair_hash> distance_table;
    std::vector<std::unordered_map<int, double>> forward_access_nodes;
    std::vector<std::unordered_map<int, double>> backward_access_nodes;

    // Helper methods
    std::optional<GraphResult> local_search(int origin_id, int destination_id, double upper_bound, bool length_only) const;

public:
    // Constructor for preprocessing
    TNRGraph(const std::vector<std::unordered_map<int, double>>& graph,
             int num_transit_nodes = 100,
             std::function<double(CHGraph*, int)> heuristic_fn = nullptr);

    // Constructor for loading from saved state
    TNRGraph(int nodes_count,
             const std::vector<int>& ranks,
             const std::vector<std::unordered_map<int, double>>& forward_graph,
             const std::vector<std::unordered_map<int, double>>& backward_graph,
             const std::unordered_map<std::pair<int, int>, int, pair_hash>& shortcuts,
             const std::optional<std::vector<std::unordered_map<int, double>>>& original_graph,
             const std::set<int>& transit_nodes,
             const std::unordered_map<std::pair<int, int>, double, pair_hash>& distance_table,
             const std::vector<std::unordered_map<int, double>>& forward_access_nodes,
             const std::vector<std::unordered_map<int, double>>& backward_access_nodes);

    // Search
    GraphResult search(int origin_id, int destination_id, bool length_only = false) const;
    
    // Accessors for serialization (optional, but good to have)
    const std::set<int>& get_transit_nodes() const { return transit_nodes; }
    const std::unordered_map<std::pair<int, int>, double, pair_hash>& get_distance_table() const { return distance_table; }
    const std::vector<std::unordered_map<int, double>>& get_forward_access_nodes() const { return forward_access_nodes; }
    const std::vector<std::unordered_map<int, double>>& get_backward_access_nodes() const { return backward_access_nodes; }
};
