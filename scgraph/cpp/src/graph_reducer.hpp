#pragma once
#include <vector>
#include <unordered_map>
#include <set>
#include <variant>
#include <string>
#include <optional>
#include "graph_utils.hpp"

class GraphReducer : public GraphUtils {
protected:
    bool has_reduced_graph = false;
    std::vector<bool> is_reduced;
    std::vector<std::vector<std::pair<int, double>>> reduced_graph;
    std::vector<std::unordered_map<int, std::vector<int>>> reduced_graph_connections;

    struct RestoreData {
        std::vector<std::pair<int, std::vector<std::pair<int, double>>>> graph_restore;
        std::vector<std::pair<int, std::unordered_map<int, std::vector<int>>>> connections_restore;
    };

    RestoreData prepare_query_graph(const std::variant<int, std::set<int>>& origin_id, std::optional<int> destination_id);
    void restore_query_graph(const RestoreData& restore);
    std::vector<int> expand_path(const std::vector<int>& path);
    std::unordered_map<int, std::pair<double, std::vector<int>>> get_temp_connections(
        int start_node, const std::string& direction, const std::set<int>& target_nodes);

public:
    virtual ~GraphReducer() = default;

    // Getters for python bindings
    bool get_has_reduced_graph() const { return has_reduced_graph; }
    const std::vector<std::vector<std::pair<int, double>>>& get_reduced_graph_internal() const { return reduced_graph; }
    const std::vector<bool>& get_is_reduced_internal() const { return is_reduced; }
    const std::vector<std::unordered_map<int, std::vector<int>>>& get_reduced_graph_connections_internal() const { return reduced_graph_connections; }

    // reduce method
    void reduce();

    // Override reset_cache to clear reduction data
    void reset_cache() override;
};
