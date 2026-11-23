#pragma once
#include <cstdint>
#include <memory>
#include <span>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

// Reading an edge must cost what reading a pair did: GCC does not inline these calls
// inside the large search loops by itself (seen in the bucket searches)
#if defined(_MSC_VER)
#define SCGRAPH_INLINE __forceinline
#else
#define SCGRAPH_INLINE inline __attribute__((always_inline))
#endif

// One edge: `destination_id` is the node it leads to. An aggregate, so that a loop over a row can
// name both members (`auto [node, distance]`)
struct Edge {
    int destination_id;
    double weight;
};

// The edges of one node, read in place
class Row {
    const int32_t* edge_destination_ids_;
    const double* weights_;
    int32_t count_;

public:
    SCGRAPH_INLINE Row(const int32_t* edge_destination_ids, const double* weights, int32_t count)
        : edge_destination_ids_(edge_destination_ids), weights_(weights), count_(count) {}

    struct iterator {
        const int32_t* destination_id;
        const double* weight;
        SCGRAPH_INLINE Edge operator*() const { return {*destination_id, *weight}; }
        SCGRAPH_INLINE iterator& operator++() {
            ++destination_id;
            ++weight;
            return *this;
        }
        SCGRAPH_INLINE bool operator!=(const iterator& other) const { return destination_id != other.destination_id; }
    };

    SCGRAPH_INLINE iterator begin() const { return {edge_destination_ids_, weights_}; }
    SCGRAPH_INLINE iterator end() const { return {edge_destination_ids_ + count_, weights_ + count_}; }

    void append_to(std::vector<int32_t>& to_edge_destination_ids, std::vector<double>& to_weights) const {
        to_edge_destination_ids.insert(to_edge_destination_ids.end(), edge_destination_ids_, edge_destination_ids_ + count_);
        to_weights.insert(to_weights.end(), weights_, weights_ + count_);
    }

    // A copy as pairs: the form of an edited row (RowEdits) and of the rows BMSSP reads
    std::vector<std::pair<int, double>> to_vector() const {
        std::vector<std::pair<int, double>> edges;
        edges.reserve(count_);
        for (int32_t i = 0; i < count_; ++i) {
            edges.emplace_back(edge_destination_ids_[i], weights_[i]);
        }
        return edges;
    }
};

// Edges stored by origin, as in a .scgraph file (compressed sparse rows): the edges of
// node u are edge_destination_ids_[node_first_edge_ids_[u]] .. edge_destination_ids_[node_first_edge_ids_[u + 1] - 1], with their weights. Read
// only: edits go to RowEdits, and the next read packs them into new arrays (GraphUtils).
// node_first_edge_ids are 32-bit, as in the file: at most 2^31 - 1 edges. The arrays are owned, or
// borrowed (a mapped file) and kept alive by `owner_`
class CsrGraph {
    struct Owned {
        std::vector<int32_t> node_first_edge_ids, edge_destination_ids;
        std::vector<double> weights;
    };
    std::shared_ptr<const void> owner_;
    const int32_t* node_first_edge_ids_ = nullptr;
    const int32_t* edge_destination_ids_ = nullptr;
    const double* weights_ = nullptr;
    int node_count_ = 0;
    int64_t edge_count_ = 0;

public:
    CsrGraph() : CsrGraph(std::vector<int32_t>{0}, {}, {}) {}

    // Arrays already checked by the caller
    CsrGraph(std::vector<int32_t> node_first_edge_ids, std::vector<int32_t> edge_destination_ids, std::vector<double> weights) {
        auto arrays = std::make_shared<Owned>(Owned{std::move(node_first_edge_ids), std::move(edge_destination_ids), std::move(weights)});
        *this = CsrGraph(arrays, arrays->node_first_edge_ids.data(), arrays->edge_destination_ids.data(), arrays->weights.data(),
                         static_cast<int>(arrays->node_first_edge_ids.size()) - 1,
                         static_cast<int64_t>(arrays->edge_destination_ids.size()));
    }

    // Arrays that `owner` keeps alive (a mapped file, for instance), already checked
    CsrGraph(std::shared_ptr<const void> owner, const int32_t* node_first_edge_ids, const int32_t* edge_destination_ids,
             const double* weights, int node_count, int64_t edge_count)
        : owner_(std::move(owner)),
          node_first_edge_ids_(node_first_edge_ids),
          edge_destination_ids_(edge_destination_ids),
          weights_(weights),
          node_count_(node_count),
          edge_count_(edge_count) {}

    explicit CsrGraph(const std::vector<std::vector<std::pair<int, double>>>& rows) {
        std::vector<int32_t> node_first_edge_ids{0};
        node_first_edge_ids.reserve(rows.size() + 1);
        size_t total_edges = 0;
        for (const auto& row : rows) {
            total_edges += row.size();
            if (total_edges > INT32_MAX) {
                throw std::length_error("a graph holds at most 2^31 - 1 edges");
            }
            node_first_edge_ids.push_back(static_cast<int32_t>(total_edges));
        }
        std::vector<int32_t> edge_destination_ids;
        std::vector<double> weights;
        edge_destination_ids.reserve(total_edges);
        weights.reserve(total_edges);
        for (const auto& row : rows) {
            for (const auto& [destination_id, weight] : row) {
                edge_destination_ids.push_back(destination_id);
                weights.push_back(weight);
            }
        }
        *this = CsrGraph(std::move(node_first_edge_ids), std::move(edge_destination_ids), std::move(weights));
    }

    std::vector<std::vector<std::pair<int, double>>> to_rows() const {
        std::vector<std::vector<std::pair<int, double>>> rows(size());
        for (int u = 0; u < size(); ++u) {
            rows[u] = (*this)[u].to_vector();
        }
        return rows;
    }

    SCGRAPH_INLINE Row operator[](int u) const {
        return {edge_destination_ids_ + node_first_edge_ids_[u], weights_ + node_first_edge_ids_[u], node_first_edge_ids_[u + 1] - node_first_edge_ids_[u]};
    }

    int size() const { return node_count_; }
    int64_t edges() const { return edge_count_; }

    // The whole arrays, in place
    std::span<const int32_t> all_node_first_edge_ids() const { return {node_first_edge_ids_, static_cast<size_t>(node_count_) + 1}; }
    std::span<const int32_t> all_edge_destination_ids() const { return {edge_destination_ids_, static_cast<size_t>(edge_count_)}; }
    std::span<const double> all_weights() const { return {weights_, static_cast<size_t>(edge_count_)}; }

    void clear() { *this = CsrGraph(); }
};

// Pending edits over a CsrGraph: the rows changed since it was packed (each copied as a
// vector at its first change) and the number of nodes. Indexed and resized as a vector of
// rows, so that the edit functions read as on one
struct RowEdits {
    std::unordered_map<int, std::vector<std::pair<int, double>>> rows;
    int node_count = -1;  // -1: no pending edit

    bool has_edits() const { return node_count >= 0; }

    // The row of node u, to change
    std::vector<std::pair<int, double>>& at(const CsrGraph& base, int u) {
        auto found = rows.find(u);
        if (found == rows.end()) {
            found = rows.emplace(u, u < base.size() ? base[u].to_vector()
                                                     : std::vector<std::pair<int, double>>{}).first;
        }
        return found->second;
    }

    // The arrays with the edits applied: untouched rows are copied as they are
    CsrGraph apply(const CsrGraph& base) const {
        std::vector<int32_t> node_first_edge_ids{0}, edge_destination_ids;
        std::vector<double> weights;
        node_first_edge_ids.reserve(node_count + 1);
        edge_destination_ids.reserve(base.edges());
        weights.reserve(base.edges());
        for (int u = 0; u < node_count; ++u) {
            auto edited = rows.find(u);
            if (edited != rows.end()) {
                for (const auto& [destination_id, weight] : edited->second) {
                    edge_destination_ids.push_back(destination_id);
                    weights.push_back(weight);
                }
            } else if (u < base.size()) {
                base[u].append_to(edge_destination_ids, weights);
            }
            if (edge_destination_ids.size() > INT32_MAX) {
                throw std::length_error("a graph holds at most 2^31 - 1 edges");
            }
            node_first_edge_ids.push_back(static_cast<int32_t>(edge_destination_ids.size()));
        }
        return CsrGraph(std::move(node_first_edge_ids), std::move(edge_destination_ids), std::move(weights));
    }
};

// What the edit functions index: a view of the arrays and their pending edits
class EditableRows {
    const CsrGraph& base_;
    RowEdits& edits_;

public:
    EditableRows(const CsrGraph& base, RowEdits& edits) : base_(base), edits_(edits) {
        if (edits_.node_count < 0) {
            edits_.node_count = base_.size();
        }
    }

    std::vector<std::pair<int, double>>& operator[](int u) { return edits_.at(base_, u); }

    // Without copying the row of node u
    bool has_edge(int u, int destination_id) const {
        auto edited = edits_.rows.find(u);
        if (edited != edits_.rows.end()) {
            for (const auto& edge : edited->second) {
                if (edge.first == destination_id) return true;
            }
            return false;
        }
        if (u >= base_.size()) return false;
        for (const auto& edge : base_[u]) {
            if (edge.destination_id == destination_id) return true;
        }
        return false;
    }

    void push_back(std::vector<std::pair<int, double>> row) {
        edits_.rows[edits_.node_count++] = std::move(row);
    }
    void pop_back() {
        edits_.rows.erase(--edits_.node_count);
    }
    int size() const { return edits_.node_count; }
};
