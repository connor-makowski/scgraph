#include "transit_node_routing.hpp"
#include <queue>
#include <algorithm>
#include <limits>
#include <iostream>
#include <functional>
#include <thread>

TNRGraph::TNRGraph(const std::vector<std::unordered_map<int, double>>& graph,
                   int settled_limit,
                   int num_transit_nodes,
                   std::function<double(CHGraph*, int)> heuristic_fn,
                   const std::optional<std::vector<std::unordered_map<int, double>>>& inverse_graph)
    : CHGraph(graph, settled_limit, heuristic_fn, inverse_graph) {
    // 1. Select Transit Nodes
    std::vector<int> sorted_nodes(nodes_count);
    for (int i = 0; i < nodes_count; ++i) {
        sorted_nodes[i] = i;
    }
    std::sort(sorted_nodes.begin(), sorted_nodes.end(), [this](int a, int b) {
        return ranks[a] > ranks[b];
    });

    int actual_num_transit = std::min(num_transit_nodes, nodes_count);
    for (int i = 0; i < actual_num_transit; ++i) {
        transit_nodes.insert(sorted_nodes[i]);
    }

    // 2. Compute Access Nodes in Parallel
    forward_access_nodes.assign(nodes_count, {});
    backward_access_nodes.assign(nodes_count, {});

    std::vector<bool> is_transit(nodes_count, false);
    for (int tn : transit_nodes) {
        is_transit[tn] = true;
    }

    unsigned int num_threads = std::thread::hardware_concurrency();
    if (num_threads == 0) num_threads = 4;

    std::vector<std::thread> threads;
    threads.reserve(num_threads);

    for (unsigned int thread_idx = 0; thread_idx < num_threads; ++thread_idx) {
        threads.emplace_back([this, thread_idx, num_threads, &is_transit]() {
            std::vector<double> distances(nodes_count, std::numeric_limits<double>::infinity());
            std::vector<int> visited_nodes;

            auto local_compute_access_nodes = [this, &distances, &visited_nodes, &is_transit](int node_id, bool forward) {
                std::unordered_map<int, double> access_nodes;
                distances[node_id] = 0.0;
                visited_nodes.push_back(node_id);
                using PQItem = std::pair<double, int>;
                std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
                open_leaves.push({0.0, node_id});

                while (!open_leaves.empty()) {
                    auto [dist, current_id] = open_leaves.top();
                    open_leaves.pop();

                    if (dist > distances[current_id]) {
                        continue;
                    }

                    if (is_transit[current_id]) {
                        if (access_nodes.find(current_id) == access_nodes.end() || dist < access_nodes[current_id]) {
                            access_nodes[current_id] = dist;
                        }
                        continue;
                    }

                    const auto& neighbors = forward ? forward_graph[current_id] : backward_graph[current_id];
                    for (const auto& [neighbor_id, weight] : neighbors) {
                        double new_dist = dist + weight;
                        if (new_dist < distances[neighbor_id]) {
                            if (distances[neighbor_id] == std::numeric_limits<double>::infinity()) {
                                visited_nodes.push_back(neighbor_id);
                            }
                            distances[neighbor_id] = new_dist;
                            open_leaves.push({new_dist, neighbor_id});
                        }
                    }
                }

                for (int v : visited_nodes) {
                    distances[v] = std::numeric_limits<double>::infinity();
                }
                visited_nodes.clear();

                return access_nodes;
            };

            for (int i = thread_idx; i < nodes_count; i += num_threads) {
                forward_access_nodes[i] = local_compute_access_nodes(i, true);
                backward_access_nodes[i] = local_compute_access_nodes(i, false);
            }
        });
    }

    for (auto& t : threads) {
        if (t.joinable()) {
            t.join();
        }
    }

    // 3. Compute Distance Table in Parallel
    num_transit = transit_nodes.size();
    transit_node_to_local_idx.assign(nodes_count, -1);
    std::vector<int> transit_nodes_vec(transit_nodes.begin(), transit_nodes.end());
    for (int i = 0; i < num_transit; ++i) {
        transit_node_to_local_idx[transit_nodes_vec[i]] = i;
    }
    distance_table_flat.assign(num_transit * num_transit, std::numeric_limits<double>::infinity());

    std::vector<std::thread> dt_threads;
    dt_threads.reserve(num_threads);

    for (unsigned int thread_idx = 0; thread_idx < num_threads; ++thread_idx) {
        dt_threads.emplace_back([this, thread_idx, num_threads, &transit_nodes_vec]() {
            size_t n = original_graph.size();
            std::vector<double> dist(n, std::numeric_limits<double>::infinity());
            std::vector<int> visited;

            for (int origin_idx = thread_idx; origin_idx < num_transit; origin_idx += num_threads) {
                int origin = transit_nodes_vec[origin_idx];
                dist[origin] = 0.0;
                visited.push_back(origin);
                using PQItem = std::pair<double, int>;
                std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> pq;
                pq.push({0.0, origin});
                while (!pq.empty()) {
                    auto [d, u] = pq.top();
                    pq.pop();
                    if (d > dist[u]) continue;
                    for (const auto& [v, w] : original_graph[u]) {
                        double nd = d + w;
                        if (nd < dist[v]) {
                            if (dist[v] == std::numeric_limits<double>::infinity()) {
                                visited.push_back(v);
                            }
                            dist[v] = nd;
                            pq.push({nd, v});
                        }
                    }
                }
                for (int target_idx = 0; target_idx < num_transit; ++target_idx) {
                    int target = transit_nodes_vec[target_idx];
                    distance_table_flat[origin_idx * num_transit + target_idx] = dist[target];
                }
                for (int v : visited) {
                    dist[v] = std::numeric_limits<double>::infinity();
                }
                visited.clear();
            }
        });
    }

    for (auto& t : dt_threads) {
        if (t.joinable()) {
            t.join();
        }
    }

    for (int i = 0; i < num_transit; ++i) {
        for (int j = 0; j < num_transit; ++j) {
            distance_table[{transit_nodes_vec[i], transit_nodes_vec[j]}] = distance_table_flat[i * num_transit + j];
        }
    }
}

TNRGraph::TNRGraph(int nodes_count,
                   const std::vector<int>& ranks,
                   const std::vector<std::unordered_map<int, double>>& forward_graph,
                   const std::vector<std::unordered_map<int, double>>& backward_graph,
                   const std::unordered_map<std::pair<int, int>, int, pair_hash>& shortcuts,
                   const std::optional<std::vector<std::unordered_map<int, double>>>& original_graph,
                   const std::set<int>& transit_nodes,
                   const std::unordered_map<std::pair<int, int>, double, pair_hash>& distance_table,
                   const std::vector<std::unordered_map<int, double>>& forward_access_nodes,
                   const std::vector<std::unordered_map<int, double>>& backward_access_nodes,
                   int settled_limit)
    : CHGraph(nodes_count, ranks, forward_graph, backward_graph, shortcuts, original_graph, settled_limit),
      transit_nodes(transit_nodes), distance_table(distance_table),
      forward_access_nodes(forward_access_nodes), backward_access_nodes(backward_access_nodes) {
    initialize_fast_lookup();
}

void TNRGraph::initialize_fast_lookup() {
    num_transit = transit_nodes.size();
    transit_node_to_local_idx.assign(nodes_count, -1);
    int idx = 0;
    for (int node : transit_nodes) {
        if (node >= 0 && node < nodes_count) {
            transit_node_to_local_idx[node] = idx++;
        }
    }
    distance_table_flat.assign(num_transit * num_transit, std::numeric_limits<double>::infinity());
    for (const auto& [pair, dist] : distance_table) {
        int u = (pair.first >= 0 && pair.first < nodes_count) ? transit_node_to_local_idx[pair.first] : -1;
        int v = (pair.second >= 0 && pair.second < nodes_count) ? transit_node_to_local_idx[pair.second] : -1;
        if (u != -1 && v != -1) {
            distance_table_flat[u * num_transit + v] = dist;
        }
    }
}

std::optional<GraphResult> TNRGraph::local_search(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, double upper_bound, bool length_only) const {
    auto origin_entries = get_node_entries(origin_id);
    auto dest_entries = get_node_entries(destination_id);

    int max_node_id = 0;
    for (const auto& [oid, _] : origin_entries) max_node_id = std::max(max_node_id, oid);
    for (const auto& [did, _] : dest_entries) max_node_id = std::max(max_node_id, did);

    int current_sz = static_cast<int>(query_f_distances.size());
    if (max_node_id >= current_sz) {
        int new_sz = max_node_id + 1;
        query_f_distances.resize(new_sz, std::numeric_limits<double>::infinity());
        query_b_distances.resize(new_sz, std::numeric_limits<double>::infinity());
        query_f_parents.resize(new_sz, -1);
        query_b_parents.resize(new_sz, -1);
    }

    auto& forward_open_leaves = query_forward_open;
    auto& backward_open_leaves = query_backward_open;
    forward_open_leaves.clear();
    backward_open_leaves.clear();

    for (const auto& [oid, odist] : origin_entries) {
        if (odist < query_f_distances[oid]) {
            if (query_f_distances[oid] == std::numeric_limits<double>::infinity() &&
                query_b_distances[oid] == std::numeric_limits<double>::infinity()) {
                query_visited.push_back(oid);
            }
            query_f_distances[oid] = odist;
            if (!length_only) query_f_parents[oid] = -1;
            forward_open_leaves.push({odist, oid});
        }
    }

    for (const auto& [did, ddist] : dest_entries) {
        if (ddist < query_b_distances[did]) {
            if (query_f_distances[did] == std::numeric_limits<double>::infinity() &&
                query_b_distances[did] == std::numeric_limits<double>::infinity()) {
                query_visited.push_back(did);
            }
            query_b_distances[did] = ddist;
            if (!length_only) query_b_parents[did] = -1;
            backward_open_leaves.push({ddist, did});
        }
    }

    double best_dist = upper_bound;
    int meeting_node = -1;

    for (const auto& [oid, odist] : origin_entries) {
        for (const auto& [did, ddist] : dest_entries) {
            if (oid == did && odist + ddist < best_dist) {
                best_dist = odist + ddist;
                meeting_node = oid;
            }
        }
    }

    while (!forward_open_leaves.empty() || !backward_open_leaves.empty()) {
        if (!forward_open_leaves.empty()) {
            auto [current_distance, current_id] = forward_open_leaves.top();
            forward_open_leaves.pop();

            if (current_distance > best_dist) {
                while (!forward_open_leaves.empty()) forward_open_leaves.pop();
            } else if (current_id < 0 || current_id >= nodes_count || transit_node_to_local_idx[current_id] == -1) {
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
                            if (!length_only) query_f_parents[neighbor_id] = current_id;
                            forward_open_leaves.push({new_dist, neighbor_id});
                            if (query_b_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_b_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_b_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                } else {
                    double current_rank = get_rank(current_id);
                    for (const auto& [neighbor_id, weight] : original_graph[current_id]) {
                        double neighbor_rank = get_rank(neighbor_id);
                        if (neighbor_rank <= current_rank && neighbor_id < nodes_count) continue;

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
                            if (!length_only) query_f_parents[neighbor_id] = current_id;
                            forward_open_leaves.push({new_dist, neighbor_id});
                            if (query_b_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_b_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_b_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                }
            }
        }

        if (!backward_open_leaves.empty()) {
            auto [current_distance, current_id] = backward_open_leaves.top();
            backward_open_leaves.pop();

            if (current_distance > best_dist) {
                while (!backward_open_leaves.empty()) backward_open_leaves.pop();
            } else if (current_id < 0 || current_id >= nodes_count || transit_node_to_local_idx[current_id] == -1) {
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
                            if (!length_only) query_b_parents[neighbor_id] = current_id;
                            backward_open_leaves.push({new_dist, neighbor_id});
                            if (query_f_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_f_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_f_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                } else {
                    double current_rank = get_rank(current_id);
                    for (const auto& [neighbor_id, weight] : original_graph[current_id]) {
                        double neighbor_rank = get_rank(neighbor_id);
                        if (neighbor_rank <= current_rank && neighbor_id < nodes_count) continue;

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
                            if (!length_only) query_b_parents[neighbor_id] = current_id;
                            backward_open_leaves.push({new_dist, neighbor_id});
                            if (query_f_distances[neighbor_id] != std::numeric_limits<double>::infinity() && new_dist + query_f_distances[neighbor_id] < best_dist) {
                                best_dist = new_dist + query_f_distances[neighbor_id];
                                meeting_node = neighbor_id;
                            }
                        }
                    }
                }
            }
        }

        double forward_min = forward_open_leaves.empty() ? std::numeric_limits<double>::infinity() : forward_open_leaves.top().first;
        double backward_min = backward_open_leaves.empty() ? std::numeric_limits<double>::infinity() : backward_open_leaves.top().first;
        if (forward_min > best_dist && backward_min > best_dist) break;
    }

    std::optional<GraphResult> res = std::nullopt;
    if (meeting_node != -1) {
        if (length_only) {
            res = GraphResult{{}, best_dist};
        } else {
            std::vector<int> path = reconstruct_ch_path(0, 0, meeting_node, query_f_parents, query_b_parents);
            res = GraphResult{path, best_dist};
        }
    }

    for (int v : query_visited) {
        query_f_distances[v] = std::numeric_limits<double>::infinity();
        query_b_distances[v] = std::numeric_limits<double>::infinity();
        query_f_parents[v] = -1;
        query_b_parents[v] = -1;
    }
    query_visited.clear();

    return res;
}

GraphResult TNRGraph::search(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id, bool length_only) const {
    auto origin_entries = get_node_entries(origin_id);
    auto dest_entries = get_node_entries(destination_id);

    std::unordered_map<int, double> f_access, b_access;

    for (const auto& [s, d_s] : origin_entries) {
        if (s < nodes_count) {
            for (const auto& [tf, df] : forward_access_nodes[s]) {
                double tot = d_s + df;
                if (f_access.find(tf) == f_access.end() || tot < f_access[tf]) {
                    f_access[tf] = tot;
                }
            }
        } else {
            // Compute for added node
            std::unordered_map<int, double> distances;
            distances[s] = 0.0;
            using PQItem = std::pair<double, int>;
            std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
            open_leaves.push({0.0, s});
            while (!open_leaves.empty()) {
                auto [current_distance, current_id] = open_leaves.top();
                open_leaves.pop();
                if (current_id >= 0 && current_id < nodes_count && transit_node_to_local_idx[current_id] != -1) {
                    double tot = d_s + current_distance;
                    if (f_access.find(current_id) == f_access.end() || tot < f_access[current_id]) {
                        f_access[current_id] = tot;
                    }
                    continue;
                }
                double current_rank = get_rank(current_id);
                const auto& neighbors = (current_id < nodes_count) ? forward_graph[current_id] : original_graph[current_id];
                for (const auto& [neighbor_id, weight] : neighbors) {
                    if (current_id < nodes_count && get_rank(neighbor_id) <= current_rank && neighbor_id < nodes_count) continue;
                    double new_dist = current_distance + weight;
                    if (distances.find(neighbor_id) == distances.end() || new_dist < distances[neighbor_id]) {
                        distances[neighbor_id] = new_dist;
                        open_leaves.push({new_dist, neighbor_id});
                    }
                }
            }
        }
    }

    for (const auto& [t, d_t] : dest_entries) {
        if (t < nodes_count) {
            for (const auto& [tb, db] : backward_access_nodes[t]) {
                double tot = d_t + db;
                if (b_access.find(tb) == b_access.end() || tot < b_access[tb]) {
                    b_access[tb] = tot;
                }
            }
        } else {
            // Compute for added node
            std::unordered_map<int, double> distances;
            distances[t] = 0.0;
            using PQItem = std::pair<double, int>;
            std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> open_leaves;
            open_leaves.push({0.0, t});
            while (!open_leaves.empty()) {
                auto [current_distance, current_id] = open_leaves.top();
                open_leaves.pop();
                if (current_id >= 0 && current_id < nodes_count && transit_node_to_local_idx[current_id] != -1) {
                    double tot = d_t + current_distance;
                    if (b_access.find(current_id) == b_access.end() || tot < b_access[current_id]) {
                        b_access[current_id] = tot;
                    }
                    continue;
                }
                double current_rank = get_rank(current_id);
                const auto& neighbors = (current_id < nodes_count) ? backward_graph[current_id] : original_graph[current_id];
                for (const auto& [neighbor_id, weight] : neighbors) {
                    if (current_id < nodes_count && get_rank(neighbor_id) <= current_rank && neighbor_id < nodes_count) continue;
                    double new_dist = current_distance + weight;
                    if (distances.find(neighbor_id) == distances.end() || new_dist < distances[neighbor_id]) {
                        distances[neighbor_id] = new_dist;
                        open_leaves.push({new_dist, neighbor_id});
                    }
                }
            }
        }
    }

    double best_dist = std::numeric_limits<double>::infinity();
    for (const auto& [oid, odist] : origin_entries) {
        for (const auto& [did, ddist] : dest_entries) {
            if (oid == did && odist + ddist < best_dist) {
                best_dist = odist + ddist;
            }
        }
    }

    for (const auto& [t_f, d_f] : f_access) {
        int u = (t_f >= 0 && t_f < nodes_count) ? transit_node_to_local_idx[t_f] : -1;
        if (u == -1) continue;
        for (const auto& [t_b, d_b] : b_access) {
            int v = (t_b >= 0 && t_b < nodes_count) ? transit_node_to_local_idx[t_b] : -1;
            if (v == -1) continue;
            double d_table = distance_table_flat[u * num_transit + v];
            if (d_table != std::numeric_limits<double>::infinity()) {
                double total = d_f + d_table + d_b;
                if (total < best_dist) {
                    best_dist = total;
                }
            }
        }
    }

    auto local_res = local_search(origin_id, destination_id, best_dist, length_only);
    if (local_res.has_value()) {
        return local_res.value();
    }

    if (length_only) {
        return {{}, best_dist};
    }

    // Fallback to CH search for path reconstruction if global TNR path was found but local search failed
    return CHGraph::search(origin_id, destination_id);
}
