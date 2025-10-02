#pragma once
#include <vector>
#include <unordered_map>

using Graph = std::vector<std::unordered_map<int, double>>;

struct GraphResult {
    std::vector<int> path;
    double length;
};

GraphResult dijkstra(const Graph& graph, int origin_id, int destination_id);
GraphResult dijkstra_makowski(const Graph& graph, int origin_id, int destination_id);