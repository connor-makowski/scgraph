#pragma once
#include <vector>
#include <unordered_map>
#include <set>
#include <variant>
#include <string>
#include <optional>
#include <memory>
#include <functional>
#include "graph_utils.hpp"

class CHGraph;
class TNRGraph;

class GraphReducer : public GraphUtils {
protected:
    bool has_reduced_graph = false;
    std::vector<bool> is_reduced;
    std::vector<int> reduced_node_chain_ids;
    std::vector<std::vector<std::pair<int, double>>> reduced_graph;
    std::vector<std::unordered_map<int, std::vector<int>>> reduced_graph_connections;
    std::vector<std::vector<std::pair<int, double>>> reduced_inverse_graph;
    std::vector<std::unordered_map<int, std::vector<int>>> reduced_inverse_graph_connections;

    std::vector<int> expand_path(const std::vector<int>& path) const;

public:
    virtual ~GraphReducer() = default;

    // Getters for python bindings
    bool get_has_reduced_graph() const { return has_reduced_graph; }
    const std::vector<std::vector<std::pair<int, double>>>& get_reduced_graph_internal() const { return reduced_graph; }
    const std::vector<std::vector<std::pair<int, double>>>& get_reduced_inverse_graph_internal() const { return reduced_inverse_graph; }
    const std::vector<bool>& get_is_reduced_internal() const { return is_reduced; }
    const std::vector<int>& get_reduced_node_chain_ids_internal() const { return reduced_node_chain_ids; }
    const std::vector<std::unordered_map<int, std::vector<int>>>& get_reduced_graph_connections_internal() const { return reduced_graph_connections; }
    const std::vector<std::unordered_map<int, std::vector<int>>>& get_reduced_inverse_graph_connections_internal() const { return reduced_inverse_graph_connections; }
    std::vector<std::unordered_map<int, double>> get_reduced_graph() const;
    std::vector<std::unordered_map<int, double>> get_reduced_inverse_graph() const;

    // is_same_chain helper
    bool is_same_chain(const std::variant<int, std::set<int>>& origin_id, std::optional<int> destination_id) const;

    // CH / TNR reduction helpers
    std::function<double(CHGraph*, int)> wrap_heuristic(std::function<double(CHGraph*, int)> heuristic_fn = nullptr) const;
    std::shared_ptr<CHGraph> create_ch_graph(std::function<double(CHGraph*, int)> heuristic_fn = nullptr, int settled_limit = 50) const;
    std::shared_ptr<TNRGraph> create_tnr_graph(int num_transit_nodes = 100, std::function<double(CHGraph*, int)> heuristic_fn = nullptr, int settled_limit = 50) const;

    // reduce method
    void reduce();

    // Override reset_cache to clear reduction data
    void reset_cache() override;
};
