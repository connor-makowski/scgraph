#include "contraction_hierarchies.hpp"
#include <queue>
#include <algorithm>
#include <limits>
#include <cmath>
#include <stdexcept>

CHGraph::CHGraph(const std::vector<std::unordered_map<int, double>>& graph,
                 int settled_limit,
                 std::function<double(CHGraph*, int)> heuristic_fn)
    : nodes_count(graph.size()), original_graph(graph), contracted_count(0), settled_limit(settled_limit) {

    ranks.assign(nodes_count, -1);
    forward_graph.assign(nodes_count, {});
    backward_graph.assign(nodes_count, {});
    contracted.assign(nodes_count, false);

    contracting_graph = original_graph;
    contracting_inverse_graph.assign(nodes_count, {});
    for (int origin_id = 0; origin_id < nodes_count; ++origin_id) {
        for (const auto& [destination_id, weight] : original_graph[origin_id]) {
            contracting_inverse_graph[destination_id][origin_id] = weight;
        }
    }

    witness_distances.assign(nodes_count, std::numeric_limits<double>::infinity());
    witness_targets.assign(nodes_count, std::numeric_limits<double>::infinity());
    witness_resolved.assign(nodes_count, false);

    preprocess(heuristic_fn);
}

CHGraph::CHGraph(int nodes_count,
                 const std::vector<int>& ranks,
                 const std::vector<std::unordered_map<int, double>>& forward_graph,
                 const std::vector<std::unordered_map<int, double>>& backward_graph,
                 const std::unordered_map<std::pair<int, int>, int, pair_hash>& shortcuts,
                 const std::optional<std::vector<std::unordered_map<int, double>>>& original_graph,
                 int settled_limit)
    : nodes_count(nodes_count), ranks(ranks), forward_graph(forward_graph),
      backward_graph(backward_graph), shortcuts(shortcuts), settled_limit(settled_limit) {
    if (original_graph.has_value()) {
        this->original_graph = original_graph.value();
    } else {
        this->original_graph.assign(nodes_count, {});
    }
}

double CHGraph::get_rank(int node_id) const {
    if (node_id >= 0 && node_id < static_cast<int>(ranks.size())) {
        return ranks[node_id] == -1 ? std::numeric_limits<double>::infinity() : static_cast<double>(ranks[node_id]);
    }
    return std::numeric_limits<double>::infinity();
}

const std::vector<double>& CHGraph::witness_search(int start_node, int avoid_node, double max_dist, size_t num_targets) const {
    witness_distances[start_node] = 0.0;
    witness_visited.push_back(start_node);

    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
    open_leaves.push({0.0, start_node});

    int settled_count = 0;
    size_t resolved_count = 0;

    while (!open_leaves.empty()) {
        auto [current_distance, current_id] = open_leaves.top();
        open_leaves.pop();

        if (current_distance > max_dist) continue;
        if (current_distance > witness_distances[current_id]) continue;

        if (witness_targets[current_id] != std::numeric_limits<double>::infinity() && current_distance <= witness_targets[current_id]) {
            if (!witness_resolved[current_id]) {
                witness_resolved[current_id] = true;
                resolved_count++;
                if (resolved_count == num_targets) {
                    break;
                }
            }
        }

        settled_count++;
        if (settled_count > settled_limit) {
            break;
        }

        for (const auto& [neighbor_id, weight] : contracting_graph[current_id]) {
            if (neighbor_id == avoid_node || (neighbor_id < static_cast<int>(contracted.size()) && contracted[neighbor_id])) continue;

            double possible_distance = current_distance + weight;
            if (possible_distance <= max_dist && possible_distance < witness_distances[neighbor_id]) {
                if (witness_distances[neighbor_id] == std::numeric_limits<double>::infinity()) {
                    witness_visited.push_back(neighbor_id);
                }
                witness_distances[neighbor_id] = possible_distance;
                open_leaves.push({possible_distance, neighbor_id});
            }
        }
    }

    return witness_distances;
}

std::pair<int, std::vector<std::tuple<int, int, double, int>>> CHGraph::count_shortcuts(int node_id) const {
    std::vector<std::tuple<int, int, double, int>> found_shortcuts;
    const auto& in_neighbors = contracting_inverse_graph[node_id];
    const auto& out_neighbors = contracting_graph[node_id];

    for (const auto& [in_neighbor_id, in_weight] : in_neighbors) {
        if (contracted[in_neighbor_id]) continue;

        double max_dist = 0;
        for (const auto& [out_neighbor_id, out_weight] : out_neighbors) {
            if (contracted[out_neighbor_id] || in_neighbor_id == out_neighbor_id) continue;
            double shortcut_distance = in_weight + out_weight;

            // Direct edge check
            auto it = contracting_graph[in_neighbor_id].find(out_neighbor_id);
            if (it != contracting_graph[in_neighbor_id].end() && it->second <= shortcut_distance + 1e-9) {
                continue;
            }

            witness_targets[out_neighbor_id] = shortcut_distance;
            witness_target_ids.push_back(out_neighbor_id);
            max_dist = std::max(max_dist, shortcut_distance);
        }

        if (witness_target_ids.empty()) continue;

        const auto& distances = witness_search(in_neighbor_id, node_id, max_dist, witness_target_ids.size());

        for (int out_neighbor_id : witness_target_ids) {
            double shortcut_distance = witness_targets[out_neighbor_id];
            if (!witness_resolved[out_neighbor_id] || distances[out_neighbor_id] > shortcut_distance + 1e-9) {
                found_shortcuts.emplace_back(in_neighbor_id, out_neighbor_id, shortcut_distance, node_id);
            }
        }

        for (int v : witness_visited) {
            witness_distances[v] = std::numeric_limits<double>::infinity();
        }
        witness_visited.clear();

        for (int t : witness_target_ids) {
            witness_targets[t] = std::numeric_limits<double>::infinity();
            witness_resolved[t] = false;
        }
        witness_target_ids.clear();
    }
    return {static_cast<int>(found_shortcuts.size()), found_shortcuts};
}

double CHGraph::default_heuristic(int node_id) const {
    auto [shortcuts_needed, found_shortcuts] = count_shortcuts(node_id);
    if (node_id >= 0 && node_id < static_cast<int>(shortcuts_cache_table.size())) {
        shortcuts_cache_table[node_id] = std::move(found_shortcuts);
    } else {
        shortcuts_cache_node = node_id;
        shortcuts_cache = std::move(found_shortcuts);
    }

    int in_edges = contracting_inverse_graph[node_id].size();
    int out_edges = contracting_graph[node_id].size();
    int edge_diff = shortcuts_needed - in_edges - out_edges;

    int contracted_neighbors = 0;
    for (const auto& [neighbor, _] : contracting_graph[node_id]) {
        if (contracted[neighbor]) contracted_neighbors++;
    }
    for (const auto& [neighbor, _] : contracting_inverse_graph[node_id]) {
        if (contracted[neighbor]) contracted_neighbors++;
    }

    return static_cast<double>(edge_diff + contracted_neighbors);
}

void CHGraph::preprocess(std::function<double(CHGraph*, int)> heuristic_fn) {
    shortcuts_cache_node = -1;
    shortcuts_cache.clear();
    shortcuts_cache_table.assign(nodes_count, {});

    if (!heuristic_fn) {
        heuristic_fn = [](CHGraph* g, int node_id) { return g->default_heuristic(node_id); };
    }

    std::vector<bool> up_to_date(nodes_count, false);

    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
    for (int node_id = 0; node_id < nodes_count; ++node_id) {
        double initial_val = contracting_graph[node_id].size() + contracting_inverse_graph[node_id].size();
        open_leaves.push({initial_val, node_id});
    }

    int rank = 0;
    while (!open_leaves.empty()) {
        auto [heuristic_value, node_id] = open_leaves.top();
        open_leaves.pop();

        if (contracted[node_id]) continue;

        double current_heuristic = heuristic_value;
        if (!up_to_date[node_id]) {
            current_heuristic = heuristic_fn(this, node_id);
            up_to_date[node_id] = true;
            if (!open_leaves.empty() && current_heuristic > open_leaves.top().first + 1e-9) {
                open_leaves.push({current_heuristic, node_id});
                continue;
            }
        }

        // Contract node_id
        ranks[node_id] = rank++;
        contracted[node_id] = true;
        contracted_count++;

        std::vector<std::tuple<int, int, double, int>> found_shortcuts;
        if (node_id >= 0 && node_id < static_cast<int>(shortcuts_cache_table.size())) {
            found_shortcuts = std::move(shortcuts_cache_table[node_id]);
        } else if (shortcuts_cache_node == node_id) {
            found_shortcuts = std::move(shortcuts_cache);
        } else {
            found_shortcuts = count_shortcuts(node_id).second;
        }

        for (const auto& [origin_id, destination_id, distance, via_node_id] : found_shortcuts) {
            if (contracting_graph[origin_id].find(destination_id) == contracting_graph[origin_id].end() || distance < contracting_graph[origin_id][destination_id]) {
                contracting_graph[origin_id][destination_id] = distance;
                contracting_inverse_graph[destination_id][origin_id] = distance;
                shortcuts[{origin_id, destination_id}] = via_node_id;
            }
        }

        // Mark remaining neighbors as dirty
        for (const auto& [neighbor_id, _] : contracting_graph[node_id]) {
            if (neighbor_id < nodes_count && !contracted[neighbor_id]) {
                up_to_date[neighbor_id] = false;
            }
        }
        for (const auto& [neighbor_id, _] : contracting_inverse_graph[node_id]) {
            if (neighbor_id < nodes_count && !contracted[neighbor_id]) {
                up_to_date[neighbor_id] = false;
            }
        }
    }

    // Build final graphs
    for (int origin_id = 0; origin_id < nodes_count; ++origin_id) {
        for (const auto& [destination_id, weight] : contracting_graph[origin_id]) {
            if (ranks[origin_id] < ranks[destination_id]) forward_graph[origin_id][destination_id] = weight;
        }
        for (const auto& [destination_id, weight] : contracting_inverse_graph[origin_id]) {
            if (ranks[origin_id] < ranks[destination_id]) backward_graph[origin_id][destination_id] = weight;
        }
    }
}

int CHGraph::add_node(const std::unordered_map<int, double>& node_dict, bool symmetric) {
    original_graph.push_back(node_dict);
    int new_node_id = static_cast<int>(original_graph.size()) - 1;
    if (symmetric) {
        for (const auto& [dest_id, distance] : node_dict) {
            if (dest_id < static_cast<int>(original_graph.size())) {
                original_graph[dest_id][new_node_id] = distance;
            }
        }
    }
    return new_node_id;
}

GraphResult CHGraph::search(int origin_id, int destination_id) const {
    if (origin_id == destination_id) {
        return {{origin_id}, 0.0};
    }

    int max_node_id = std::max(origin_id, destination_id);
    int current_sz = static_cast<int>(query_f_distances.size());
    if (max_node_id >= current_sz) {
        int new_sz = max_node_id + 1;
        query_f_distances.resize(new_sz, std::numeric_limits<double>::infinity());
        query_b_distances.resize(new_sz, std::numeric_limits<double>::infinity());
        query_f_parents.resize(new_sz, -1);
        query_b_parents.resize(new_sz, -1);
    }

    query_f_distances[origin_id] = 0.0;
    query_f_parents[origin_id] = -1;
    query_visited.push_back(origin_id);

    query_b_distances[destination_id] = 0.0;
    query_b_parents[destination_id] = -1;
    query_visited.push_back(destination_id);

    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> forward_open_leaves, backward_open_leaves;
    forward_open_leaves.push({0.0, origin_id});
    backward_open_leaves.push({0.0, destination_id});

    double best_dist = std::numeric_limits<double>::infinity();
    int meeting_node = -1;

    while (!forward_open_leaves.empty() || !backward_open_leaves.empty()) {
        if (!forward_open_leaves.empty()) {
            auto [current_distance, current_id] = forward_open_leaves.top();
            forward_open_leaves.pop();

            if (current_distance <= best_dist) {
                if (current_id < nodes_count) {
                    for (const auto& [neighbor_id, weight] : forward_graph[current_id]) {
                        double new_dist = current_distance + weight;
                        if (neighbor_id >= static_cast<int>(query_f_distances.size())) {
                            int new_sz = neighbor_id + 1;
                            query_f_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_b_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_f_parents.resize(new_sz, -1);
                            query_b_parents.resize(new_sz, -1);
                        }
                        if (query_f_distances[neighbor_id] == std::numeric_limits<double>::infinity()) {
                            query_visited.push_back(neighbor_id);
                        }
                        if (new_dist < query_f_distances[neighbor_id]) {
                            query_f_distances[neighbor_id] = new_dist;
                            query_f_parents[neighbor_id] = current_id;
                            forward_open_leaves.push({new_dist, neighbor_id});
                            if (query_b_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_b_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_b_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                } else {
                    for (const auto& [neighbor_id, weight] : original_graph[current_id]) {
                        double new_dist = current_distance + weight;
                        if (neighbor_id >= static_cast<int>(query_f_distances.size())) {
                            int new_sz = neighbor_id + 1;
                            query_f_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_b_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_f_parents.resize(new_sz, -1);
                            query_b_parents.resize(new_sz, -1);
                        }
                        if (query_f_distances[neighbor_id] == std::numeric_limits<double>::infinity()) {
                            query_visited.push_back(neighbor_id);
                        }
                        if (new_dist < query_f_distances[neighbor_id]) {
                            query_f_distances[neighbor_id] = new_dist;
                            query_f_parents[neighbor_id] = current_id;
                            forward_open_leaves.push({new_dist, neighbor_id});
                            if (query_b_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_b_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_b_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                }
            } else {
                while (!forward_open_leaves.empty()) forward_open_leaves.pop();
            }
        }

        if (!backward_open_leaves.empty()) {
            auto [current_distance, current_id] = backward_open_leaves.top();
            backward_open_leaves.pop();

            if (current_distance <= best_dist) {
                if (current_id < nodes_count) {
                    for (const auto& [neighbor_id, weight] : backward_graph[current_id]) {
                        double new_dist = current_distance + weight;
                        if (neighbor_id >= static_cast<int>(query_f_distances.size())) {
                            int new_sz = neighbor_id + 1;
                            query_f_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_b_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_f_parents.resize(new_sz, -1);
                            query_b_parents.resize(new_sz, -1);
                        }
                        if (query_b_distances[neighbor_id] == std::numeric_limits<double>::infinity()) {
                            query_visited.push_back(neighbor_id);
                        }
                        if (new_dist < query_b_distances[neighbor_id]) {
                            query_b_distances[neighbor_id] = new_dist;
                            query_b_parents[neighbor_id] = current_id;
                            backward_open_leaves.push({new_dist, neighbor_id});
                            if (query_f_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_f_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_f_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                } else {
                    for (const auto& [neighbor_id, weight] : original_graph[current_id]) {
                        double new_dist = current_distance + weight;
                        if (neighbor_id >= static_cast<int>(query_f_distances.size())) {
                            int new_sz = neighbor_id + 1;
                            query_f_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_b_distances.resize(new_sz, std::numeric_limits<double>::infinity());
                            query_f_parents.resize(new_sz, -1);
                            query_b_parents.resize(new_sz, -1);
                        }
                        if (query_b_distances[neighbor_id] == std::numeric_limits<double>::infinity()) {
                            query_visited.push_back(neighbor_id);
                        }
                        if (new_dist < query_b_distances[neighbor_id]) {
                            query_b_distances[neighbor_id] = new_dist;
                            query_b_parents[neighbor_id] = current_id;
                            backward_open_leaves.push({new_dist, neighbor_id});
                            if (query_f_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_f_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_f_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                }
            } else {
                while (!backward_open_leaves.empty()) backward_open_leaves.pop();
            }
        }

        double forward_min = forward_open_leaves.empty() ? std::numeric_limits<double>::infinity() : forward_open_leaves.top().first;
        double backward_min = backward_open_leaves.empty() ? std::numeric_limits<double>::infinity() : backward_open_leaves.top().first;
        if (forward_min > best_dist && backward_min > best_dist) break;
    }

    if (meeting_node == -1) {
        for (int v : query_visited) {
            query_f_distances[v] = std::numeric_limits<double>::infinity();
            query_b_distances[v] = std::numeric_limits<double>::infinity();
            query_f_parents[v] = -1;
            query_b_parents[v] = -1;
        }
        query_visited.clear();
        throw std::runtime_error("No path found between origin and destination");
    }

    std::vector<int> path = reconstruct_ch_path(origin_id, destination_id, meeting_node, query_f_parents, query_b_parents);

    for (int v : query_visited) {
        query_f_distances[v] = std::numeric_limits<double>::infinity();
        query_b_distances[v] = std::numeric_limits<double>::infinity();
        query_f_parents[v] = -1;
        query_b_parents[v] = -1;
    }
    query_visited.clear();

    return {path, best_dist};
}

std::vector<int> CHGraph::reconstruct_ch_path(int origin_id, int destination_id, int meeting_node,
                                            const std::vector<int>& forward_parent,
                                            const std::vector<int>& backward_parent) const {
    std::vector<int> forward_path;
    int current_id = meeting_node;
    while (current_id != -1) {
        forward_path.push_back(current_id);
        current_id = (current_id < static_cast<int>(forward_parent.size())) ? forward_parent[current_id] : -1;
    }
    std::reverse(forward_path.begin(), forward_path.end());

    std::vector<int> backward_path;
    current_id = (meeting_node < static_cast<int>(backward_parent.size())) ? backward_parent[meeting_node] : -1;
    while (current_id != -1) {
        backward_path.push_back(current_id);
        current_id = (current_id < static_cast<int>(backward_parent.size())) ? backward_parent[current_id] : -1;
    }

    std::vector<int> contracted_path = forward_path;
    contracted_path.insert(contracted_path.end(), backward_path.begin(), backward_path.end());

    std::vector<int> path;
    for (size_t i = 0; i < contracted_path.size() - 1; ++i) {
        std::vector<int> unpacked = unpack_shortcut(contracted_path[i], contracted_path[i + 1]);
        path.insert(path.end(), unpacked.begin(), unpacked.end());
    }
    path.push_back(contracted_path.back());
    return path;
}

std::vector<int> CHGraph::unpack_shortcut(int origin_id, int destination_id) const {
    auto it = shortcuts.find({origin_id, destination_id});
    if (it != shortcuts.end()) {
        int via_node_id = it->second;
        std::vector<int> left = unpack_shortcut(origin_id, via_node_id);
        std::vector<int> right = unpack_shortcut(via_node_id, destination_id);
        left.insert(left.end(), right.begin(), right.end());
        return left;
    } else {
        return {origin_id};
    }
}
