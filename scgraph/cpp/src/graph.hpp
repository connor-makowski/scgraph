#pragma once
#include <set>
#include <functional>
#include <optional>
#include <variant>
#include <memory>
#include "graph_utils.hpp"

#include "contraction_hierarchies.hpp"
#include "transit_node_routing.hpp"

class Graph : public GraphUtils {
private:
    std::shared_ptr<CHGraph> __ch_graph__ = nullptr;
    std::shared_ptr<TNRGraph> __tnr_graph__ = nullptr;

public:
    // Constructor
    explicit Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate = false);

    // Override reset_cache to also clear ch_graph and tnr_graph
    void reset_cache();

    // Tree algorithms
    TreeData get_shortest_path_tree(const std::variant<int, std::set<int>>& origin_id);
    GraphResult get_tree_path(int origin_id, int destination_id, const TreeData& tree_data, bool length_only = false);

    // Shortest path algorithms
    GraphResult dijkstra(const std::variant<int, std::set<int>>& origin_id, int destination_id);
    GraphResult dijkstra_buckets(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                                 std::optional<double> max_edge_weight = std::nullopt);
    GraphResult dijkstra_negative(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                                  std::optional<int> cycle_check_iterations = std::nullopt);
    GraphResult a_star(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                      std::function<double(int, int)> heuristic_fn = nullptr);
    GraphResult bellman_ford(const std::variant<int, std::set<int>>& origin_id, int destination_id);
    GraphResult bmssp(const std::variant<int, std::set<int>>& origin_id, int destination_id);

    // Cached shortest path
    GraphResult cached_shortest_path(int origin_id, int destination_id, bool length_only = false);

    // Contraction Hierarchies
    std::shared_ptr<CHGraph> create_contraction_hierarchy(std::function<double(CHGraph*, int)> heuristic_fn = nullptr);
    GraphResult contraction_hierarchy(int origin_id, int destination_id);

    // Transit Node Routing
    std::shared_ptr<TNRGraph> create_tnr_hierarchy(int num_transit_nodes = 100, std::function<double(CHGraph*, int)> heuristic_fn = nullptr);
    void set_tnr_graph(std::shared_ptr<TNRGraph> tnr_graph);
    GraphResult tnr(int origin_id, int destination_id, bool length_only = false);

};
