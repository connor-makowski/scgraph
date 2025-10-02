#pragma once
#include <vector>
#include <unordered_map>

using Graph = std::vector<std::unordered_map<int, double>>;

struct SpanningTreeResult {
    int node_id;
    std::vector<int> predecessors;
    std::vector<double> distance_matrix;
};

SpanningTreeResult makowskis_spanning_tree(const Graph& graph, int origin_id);