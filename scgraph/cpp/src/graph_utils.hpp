#pragma once
#include <vector>
#include <set>
#include <variant>
#include <unordered_map>
#include <utility>
#include <optional>
#include <functional>
#include "adjacency.hpp"

using NodeIdVariant = std::variant<int, std::unordered_map<int, double>, std::set<int>>;

struct GraphResult {
    std::vector<int> path;
    double length;
};

struct TreeData {
    NodeIdVariant origin_id;
    std::vector<int> predecessors;
    std::vector<double> distance_matrix;
};

// Custom hash for std::pair<int, int> to use in unordered_map
struct pair_hash {
    inline std::size_t operator()(const std::pair<int, int>& v) const {
        return v.first * 31 + v.second;
    }
};

// Helper functions to get IDs and entries from variant
std::vector<int> get_node_ids(const NodeIdVariant& node_id);
std::vector<std::pair<int, double>> get_node_entries(const NodeIdVariant& node_id);
bool node_variant_contains(const NodeIdVariant& node_variant, int node_id);
std::vector<int> get_origin_ids(const NodeIdVariant& origin_id);
bool origin_id_contains(const NodeIdVariant& origin_id, int node_id);

class GraphUtils {
private:
    // The arcs, read through graph(). Edits change copies of the rows they touch, and the
    // next read packs them into new arrays, so that a series of edits costs one packing.
    // graph() const writes this state: safe because the bindings never release the GIL
    mutable Adjacency packed_graph;
    mutable RowEdits edits;

protected:
    const Adjacency& graph() const {
        if (edits.count >= 0) {
            packed_graph = edits.apply(packed_graph);
            edits = RowEdits();
        }
        return packed_graph;
    }
    void set_graph(Adjacency arcs) {
        packed_graph = std::move(arcs);
        edits = RowEdits();
    }
    // The rows, to edit
    EditableRows rows_to_edit() {
        inverse_graph_computed = false;
        inverse_graph.clear();
        return EditableRows(packed_graph, edits);
    }
    // Inverse graph (lazily computed)
    Adjacency inverse_graph;
    bool inverse_graph_computed = false;
    std::vector<TreeData> cache;
    mutable double max_edge_weight_cache = 0.0;
    mutable bool max_edge_weight_computed = false;

    // Helper methods for conversion
    static std::vector<std::vector<std::pair<int, double>>> serialize_graph(
        const std::vector<std::unordered_map<int, double>>& input_graph);
    std::unordered_map<int, double> get_adjacency_dict(int idx) const;

    // Utility methods
    void input_check(const NodeIdVariant& origin_id, const NodeIdVariant& destination_id) const;
    std::vector<int> reconstruct_path(int destination_id, const std::vector<int>& predecessor) const;
    void cycle_check(const std::vector<int>& predecessor_matrix, int node_id) const;
    void ensure_inverse_graph();
    double get_max_edge_weight() const;
    bool connected_check(int origin_id = 0);
    bool symmetric_check() const;

public:
    virtual ~GraphUtils() = default;

    // Validation
    void validate(bool check_symmetry = true, bool check_connected = true);

    // Cache management
    virtual void reset_cache();

    // Access
    const std::unordered_map<int, double> get(int idx) const;
    // The number of nodes, without packing pending edits
    int size() const { return edits.count >= 0 ? edits.count : packed_graph.size(); }
    const std::vector<std::unordered_map<int, double>> get_graph() const;
    std::vector<std::unordered_map<int, double>> get_inverse_graph();
    const std::vector<TreeData>& get_cache() const { return cache; }
    void set_cache(const std::vector<TreeData>& new_cache) { cache = new_cache; }
    double get_path_weight(const std::vector<int>& path) const;

    // Graph modification
    int add_node(const std::unordered_map<int, double>& node_dict = {}, bool symmetric = false);
    void add_edge(int origin_id, int destination_id, double distance, bool symmetric = false);
    std::unordered_map<int, double> remove_node(bool symmetric_node = false);
    std::optional<double> remove_edge(int origin_id, int destination_id, bool symmetric = false);
};
