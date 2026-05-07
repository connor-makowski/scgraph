#include "graph.hpp"
#include "bmssp.hpp"
#include "contraction_hierarchies.hpp"
#include <queue>
#include <limits>
#include <stdexcept>
#include <algorithm>
#include <iostream>
#include <cmath>
#include <functional>

// Constructor
Graph::Graph(const std::vector<std::unordered_map<int, double>>& graph_data, bool validate)
    : GraphUtils() {
    graph = serialize_graph(graph_data);
    GraphUtils::reset_cache();
    if (validate) {
        this->validate();
    }
}

// Override reset_cache to also clear __ch_graph__ and __tnr_graph__
void Graph::reset_cache() {
    GraphUtils::reset_cache();
    __ch_graph__ = nullptr;
    __tnr_graph__ = nullptr;
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

GraphResult Graph::dijkstra_buckets(const std::variant<int, std::set<int>>& origin_id, int destination_id,
                                     std::optional<double> max_edge_weight) {
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);

    double max_weight = 0.0;
    if (max_edge_weight.has_value()) {
        max_weight = max_edge_weight.value();
    } else {
        for (const auto& node_edges : graph) {
            for (const auto& [connected_id, connected_distance] : node_edges) {
                if (connected_distance > max_weight) {
                    max_weight = connected_distance;
                }
            }
        }
    }
    int num_buckets = static_cast<int>(std::ceil(max_weight)) + 1;

    const size_t n = graph.size();
    std::vector<double> distance_matrix(n, std::numeric_limits<double>::infinity());
    std::vector<int> predecessor(n, -1);
    std::vector<std::vector<int>> buckets(num_buckets);

    for (int oid : origin_ids) {
        distance_matrix[oid] = 0.0;
        buckets[0].push_back(oid);
    }

    int current_dist = 0;
    size_t nodes_in_buckets = origin_ids.size();

    while (nodes_in_buckets > 0) {
        int bucket_idx = current_dist % num_buckets;
        while (buckets[bucket_idx].empty()) {
            current_dist++;
            bucket_idx = current_dist % num_buckets;
            if (nodes_in_buckets == 0) break;
            if (distance_matrix[destination_id] < static_cast<double>(current_dist)) break;
        }

        if (nodes_in_buckets == 0 || distance_matrix[destination_id] < static_cast<double>(current_dist)) break;

        int current_id = buckets[bucket_idx].back();
        buckets[bucket_idx].pop_back();
        nodes_in_buckets--;

        if (distance_matrix[current_id] < static_cast<double>(current_dist)) {
            continue;
        }

        for (const auto& [connected_id, connected_distance] : graph[current_id]) {
            double possible_distance = distance_matrix[current_id] + connected_distance;
            if (possible_distance < distance_matrix[connected_id]) {
                distance_matrix[connected_id] = possible_distance;
                predecessor[connected_id] = current_id;
                buckets[static_cast<int>(possible_distance) % num_buckets].push_back(connected_id);
                nodes_in_buckets++;
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
    input_check(origin_id, destination_id);
    auto origin_ids = get_origin_ids(origin_id);

    const size_t n = graph.size();

    const bool multi_source = (origin_ids.size() > 1);

    std::vector<double> distances;
    std::vector<int>    preds;

    if (!multi_source) {
        spp_expected::bmssp<double> solver(graph);
        solver.prepare_graph(false);

        int src = *origin_ids.begin();
        auto [dist, pred] = solver.execute(src);
        distances = std::move(dist);
        preds     = std::move(pred);
    } else {
        std::vector<std::vector<std::pair<int, double>>> augmented(graph);
        std::vector<std::pair<int, double>> super_edges;
        super_edges.reserve(origin_ids.size());
        for (int oid : origin_ids) {
            super_edges.emplace_back(oid, 0.0);
        }
        augmented.push_back(std::move(super_edges));

        spp_expected::bmssp<double> aug_solver(augmented);
        aug_solver.prepare_graph(false);

        int super_src = static_cast<int>(augmented.size()) - 1;
        auto [dist, pred] = aug_solver.execute(super_src);

        dist.resize(n);
        pred.resize(n);

        for (size_t i = 0; i < n; ++i) {
            if (pred[i] == super_src) {
                pred[i] = -1;
            }
        }

        distances = std::move(dist);
        preds     = std::move(pred);
    }

    const double solver_inf = std::numeric_limits<double>::max() / 10.0;
    if (distances[destination_id] >= solver_inf) {
        throw std::runtime_error("The origin and destination nodes are not connected.");
    }

    std::vector<int> path;
    {
        int cur = destination_id;
        while (true) {
            path.push_back(cur);
            int p = preds[cur];
            if (p == cur || p == -1) break;
            cur = p;
        }
        std::reverse(path.begin(), path.end());
    }

    return GraphResult{path, distances[destination_id]};
}

GraphResult Graph::cached_shortest_path(int origin_id, int destination_id, bool length_only) {
    if (cache[origin_id].predecessors.empty()) {
        cache[origin_id] = get_shortest_path_tree(origin_id);
    }

    return get_tree_path(origin_id, destination_id, cache[origin_id], length_only);
}

std::shared_ptr<CHGraph> Graph::create_contraction_hierarchy(std::function<double(CHGraph*, int)> heuristic_fn) {
    __ch_graph__ = std::make_shared<CHGraph>(get_graph(), heuristic_fn);
    return __ch_graph__;
}

GraphResult Graph::contraction_hierarchy(int origin_id, int destination_id) {
    if (__ch_graph__ == nullptr) {
        create_contraction_hierarchy();
    }
    return __ch_graph__->get_shortest_path(origin_id, destination_id);
}

std::shared_ptr<TNRGraph> Graph::create_tnr_hierarchy(int num_transit_nodes, std::function<double(CHGraph*, int)> heuristic_fn) {
    __tnr_graph__ = std::make_shared<TNRGraph>(get_graph(), num_transit_nodes, heuristic_fn);
    return __tnr_graph__;
}

void Graph::set_tnr_graph(std::shared_ptr<TNRGraph> tnr_graph) {
    __tnr_graph__ = tnr_graph;
}

GraphResult Graph::tnr(int origin_id, int destination_id, bool length_only) {
    if (__tnr_graph__ == nullptr) {
        create_tnr_hierarchy();
    }
    return __tnr_graph__->search(origin_id, destination_id, length_only);
}
