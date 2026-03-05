#include "ch_graph.hpp"
#include <queue>
#include <algorithm>
#include <limits>
#include <cmath>
#include <stdexcept>

CHGraph::CHGraph(const std::vector<std::unordered_map<int, double>>& graph,
                 std::function<double(int)> heuristic_fn)
    : nodes_count(graph.size()), original_graph(graph), contracted_count(0) {
    
    ranks.assign(nodes_count, -1);
    forward_graph.assign(nodes_count, {});
    backward_graph.assign(nodes_count, {});
    contracted.assign(nodes_count, false);
    
    contracting_graph = original_graph;
    contracting_inverse_graph.assign(nodes_count, {});
    for (int u = 0; u < nodes_count; ++u) {
        for (const auto& [v, w] : original_graph[u]) {
            contracting_inverse_graph[v][u] = w;
        }
    }
    
    preprocess(heuristic_fn);
}

CHGraph::CHGraph(int nodes_count,
                 const std::vector<int>& ranks,
                 const std::vector<std::unordered_map<int, double>>& forward_graph,
                 const std::vector<std::unordered_map<int, double>>& backward_graph,
                 const std::unordered_map<std::pair<int, int>, int, pair_hash>& shortcuts,
                 const std::optional<std::vector<std::unordered_map<int, double>>>& original_graph)
    : nodes_count(nodes_count), ranks(ranks), forward_graph(forward_graph),
      backward_graph(backward_graph), shortcuts(shortcuts) {
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

std::unordered_map<int, double> CHGraph::witness_search(int start_node, int avoid_node, double max_dist) const {
    std::unordered_map<int, double> distances;
    distances[start_node] = 0;
    
    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> pq;
    pq.push({0.0, start_node});
    
    while (!pq.empty()) {
        auto [d, u] = pq.top();
        pq.pop();
        
        if (d > max_dist) continue;
        if (distances.find(u) != distances.end() && d > distances.at(u)) continue;
        
        for (const auto& [v, weight] : contracting_graph[u]) {
            if (v == avoid_node || (v < static_cast<int>(contracted.size()) && contracted[v])) continue;
            
            double new_dist = d + weight;
            if (new_dist <= max_dist && (distances.find(v) == distances.end() || new_dist < distances.at(v))) {
                distances[v] = new_dist;
                pq.push({new_dist, v});
            }
        }
    }
    return distances;
}

std::pair<int, std::vector<std::tuple<int, int, double, int>>> CHGraph::count_shortcuts(int v) const {
    std::vector<std::tuple<int, int, double, int>> found_shortcuts;
    const auto& in_neighbors = contracting_inverse_graph[v];
    const auto& out_neighbors = contracting_graph[v];
    
    for (const auto& [u, w_uv] : in_neighbors) {
        if (contracted[u]) continue;
        
        double max_dist = 0;
        std::unordered_map<int, double> targets;
        for (const auto& [w, w_vw] : out_neighbors) {
            if (contracted[w] || u == w) continue;
            double dist_uvw = w_uv + w_vw;
            targets[w] = dist_uvw;
            max_dist = std::max(max_dist, dist_uvw);
        }
        
        if (targets.empty()) continue;
        
        auto distances = witness_search(u, v, max_dist);
        
        for (const auto& [w, dist_uvw] : targets) {
            if (distances.find(w) == distances.end() || distances.at(w) > dist_uvw + 1e-9) {
                found_shortcuts.emplace_back(u, w, dist_uvw, v);
            }
        }
    }
    return {static_cast<int>(found_shortcuts.size()), found_shortcuts};
}

double CHGraph::default_heuristic(int node_id) const {
    auto [shortcuts_needed, _] = count_shortcuts(node_id);
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

void CHGraph::preprocess(std::function<double(int)> heuristic_fn) {
    if (!heuristic_fn) {
        heuristic_fn = [this](int id) { return this->default_heuristic(id); };
    }
    
    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> pq;
    for (int i = 0; i < nodes_count; ++i) {
        pq.push({heuristic_fn(i), i});
    }
    
    int rank = 0;
    while (!pq.empty()) {
        auto [h, v] = pq.top();
        pq.pop();
        
        // Lazy update
        double new_h = heuristic_fn(v);
        if (!pq.empty() && new_h > pq.top().first + 1e-9) {
            pq.push({new_h, v});
            continue;
        }
        
        // Contract v
        ranks[v] = rank++;
        contracted[v] = true;
        contracted_count++;
        
        auto [_, found_shortcuts] = count_shortcuts(v);
        for (const auto& [u, w, dist, v_mid] : found_shortcuts) {
            if (contracting_graph[u].find(w) == contracting_graph[u].end() || dist < contracting_graph[u][w]) {
                contracting_graph[u][w] = dist;
                contracting_inverse_graph[w][u] = dist;
                shortcuts[{u, w}] = v_mid;
            }
        }
    }
    
    // Build final graphs
    for (int u = 0; u < nodes_count; ++u) {
        for (const auto& [v, w] : contracting_graph[u]) {
            if (ranks[u] < ranks[v]) forward_graph[u][v] = w;
        }
        for (const auto& [v, w] : contracting_inverse_graph[u]) {
            if (ranks[u] < ranks[v]) backward_graph[u][v] = w;
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
    
    std::unordered_map<int, double> f_dist, b_dist;
    std::unordered_map<int, int> f_parent, b_parent;
    f_dist[origin_id] = 0.0;
    f_parent[origin_id] = -1;
    b_dist[destination_id] = 0.0;
    b_parent[destination_id] = -1;
    
    using PQItem = std::pair<double, int>;
    std::priority_queue<PQItem, std::vector<PQItem>, std::greater<PQItem>> f_pq, b_pq;
    f_pq.push({0.0, origin_id});
    b_pq.push({0.0, destination_id});
    
    double best_dist = std::numeric_limits<double>::infinity();
    int meeting_node = -1;
    
    while (!f_pq.empty() || !b_pq.empty()) {
        if (!f_pq.empty()) {
            auto [d, u] = f_pq.top();
            f_pq.pop();
            
            if (d <= best_dist) {
                double u_rank = get_rank(u);
                const auto& neighbors = (u < nodes_count) ? forward_graph[u] : original_graph[u];
                for (const auto& [v, w] : neighbors) {
                    double v_rank = get_rank(v);
                    if (v_rank <= u_rank && v < nodes_count) continue;
                    
                    double new_dist = d + w;
                    if (f_dist.find(v) == f_dist.end() || new_dist < f_dist[v]) {
                        f_dist[v] = new_dist;
                        f_parent[v] = u;
                        f_pq.push({new_dist, v});
                        if (b_dist.find(v) != b_dist.end() && new_dist + b_dist[v] < best_dist) {
                            best_dist = new_dist + b_dist[v];
                            meeting_node = v;
                        }
                    }
                }
            } else {
                while(!f_pq.empty()) f_pq.pop();
            }
        }
        
        if (!b_pq.empty()) {
            auto [d, u] = b_pq.top();
            b_pq.pop();
            
            if (d <= best_dist) {
                double u_rank = get_rank(u);
                const auto& neighbors = (u < nodes_count) ? backward_graph[u] : original_graph[u];
                for (const auto& [v, w] : neighbors) {
                    double v_rank = get_rank(v);
                    if (v_rank <= u_rank && v < nodes_count) continue;
                    
                    double new_dist = d + w;
                    if (b_dist.find(v) == b_dist.end() || new_dist < b_dist[v]) {
                        b_dist[v] = new_dist;
                        b_parent[v] = u;
                        b_pq.push({new_dist, v});
                        if (f_dist.find(v) != f_dist.end() && new_dist + f_dist[v] < best_dist) {
                            best_dist = new_dist + f_dist[v];
                            meeting_node = v;
                        }
                    }
                }
            } else {
                while(!b_pq.empty()) b_pq.pop();
            }
        }
        
        double f_min = f_pq.empty() ? std::numeric_limits<double>::infinity() : f_pq.top().first;
        double b_min = b_pq.empty() ? std::numeric_limits<double>::infinity() : b_pq.top().first;
        if (f_min > best_dist && b_min > best_dist) break;
    }
    
    if (meeting_node == -1) {
        throw std::runtime_error("No path found between origin and destination");
    }
    
    std::vector<int> path = reconstruct_ch_path(origin_id, destination_id, meeting_node, f_parent, b_parent);
    return {path, best_dist};
}

std::vector<int> CHGraph::reconstruct_ch_path(int origin_id, int destination_id, int meeting_node,
                                            const std::unordered_map<int, int>& f_parent,
                                            const std::unordered_map<int, int>& b_parent) const {
    std::vector<int> f_path;
    int curr = meeting_node;
    while (curr != -1) {
        f_path.push_back(curr);
        curr = f_parent.count(curr) ? f_parent.at(curr) : -1;
    }
    std::reverse(f_path.begin(), f_path.end());
    
    std::vector<int> b_path;
    curr = b_parent.count(meeting_node) ? b_parent.at(meeting_node) : -1;
    while (curr != -1) {
        b_path.push_back(curr);
        curr = b_parent.count(curr) ? b_parent.at(curr) : -1;
    }
    
    std::vector<int> full_ch_path = f_path;
    full_ch_path.insert(full_ch_path.end(), b_path.begin(), b_path.end());
    
    std::vector<int> actual_path;
    for (size_t i = 0; i < full_ch_path.size() - 1; ++i) {
        std::vector<int> unpacked = unpack_shortcut(full_ch_path[i], full_ch_path[i+1]);
        actual_path.insert(actual_path.end(), unpacked.begin(), unpacked.end());
    }
    actual_path.push_back(full_ch_path.back());
    return actual_path;
}

std::vector<int> CHGraph::unpack_shortcut(int u, int w) const {
    auto it = shortcuts.find({u, w});
    if (it != shortcuts.end()) {
        int v_mid = it->second;
        std::vector<int> left = unpack_shortcut(u, v_mid);
        std::vector<int> right = unpack_shortcut(v_mid, w);
        left.insert(left.end(), right.begin(), right.end());
        return left;
    } else {
        return {u};
    }
}
