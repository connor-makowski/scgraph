#pragma once
#include <vector>
#include <set>
#include <variant>
#include <unordered_map>
#include <utility>
#include <optional>
#include <functional>
#include <stdexcept>
#include "csr_graph.hpp"

struct PathNotFoundException : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct NegativeCycleException : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

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
    // CSR graph storage and Copy-on-Write edit buffer.
    // - packed_graph: contiguous CSR arrays
    // - edits: pending row modifications
    // Dynamic updates write into `edits`; graph() packs them on subsequent read queries.
    // Note: graph() const mutates this cache; safe because Python bindings hold the GIL.
    mutable CsrGraph packed_graph;
    mutable RowEdits edits;

protected:
    const CsrGraph& graph() const {
        if (edits.has_edits()) {
            packed_graph = edits.apply(packed_graph);
            edits = RowEdits();
        }
        return packed_graph;
    }
    void set_graph(CsrGraph arcs) {
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
    CsrGraph inverse_graph;
    bool inverse_graph_computed = false;
    // Cached trees by origin: only computed trees take memory
    std::unordered_map<int, TreeData> cache;
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
    int size() const { return edits.has_edits() ? edits.node_count : packed_graph.size(); }
    const std::vector<std::unordered_map<int, double>> get_graph() const;
    // The arcs by origin, pending edits packed
    const CsrGraph& arcs() const { return graph(); }
    std::vector<std::unordered_map<int, double>> get_inverse_graph();
    const std::unordered_map<int, TreeData>& get_cache() const { return cache; }
    void set_cache(std::unordered_map<int, TreeData> new_cache) { cache = std::move(new_cache); }
    double get_path_weight(const std::vector<int>& path) const;

    // Graph modification
    int add_node(const std::unordered_map<int, double>& node_dict = {}, bool symmetric = false);
    void add_edge(int origin_id, int destination_id, double distance, bool symmetric = false);
    std::unordered_map<int, double> remove_node(bool symmetric_node = false);
    std::optional<double> remove_edge(int origin_id, int destination_id, bool symmetric = false);
};
