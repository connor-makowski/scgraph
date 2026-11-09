#pragma once
#include <cstdint>
#include <memory>
#include <span>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

// Force inlining on performance-critical traversal loops (GCC / MSVC).
// Prevents function call overhead during tight graph searches (e.g. Dijkstra).
#if defined(_MSC_VER)
#define SCGRAPH_INLINE __forceinline
#else
#define SCGRAPH_INLINE inline __attribute__((always_inline))
#endif

// Directed edge (arc) representation.
// Uses clean domain naming while supporting C++17 structured bindings (`auto [v, w]`):
// - head:   target node ID
// - weight: edge traversal weight (distance)
struct Arc {
    int head;
    double weight;
};

// Read-only view over the outgoing arcs of a single node.
// Iterates directly over contiguous CSR memory without allocating.
class Row {
    const int32_t* heads_;
    const double* weights_;
    int32_t count_;

public:
    SCGRAPH_INLINE Row(const int32_t* heads, const double* weights, int32_t count)
        : heads_(heads), weights_(weights), count_(count) {}

    struct iterator {
        const int32_t* head;
        const double* weight;
        SCGRAPH_INLINE Arc operator*() const { return {*head, *weight}; }
        SCGRAPH_INLINE iterator& operator++() {
            ++head;
            ++weight;
            return *this;
        }
        SCGRAPH_INLINE bool operator!=(const iterator& other) const { return head != other.head; }
    };

    SCGRAPH_INLINE iterator begin() const { return {heads_, weights_}; }
    SCGRAPH_INLINE iterator end() const { return {heads_ + count_, weights_ + count_}; }

    // Append outgoing arcs to destination arrays
    void append_to(std::vector<int32_t>& to_heads, std::vector<double>& to_weights) const {
        to_heads.insert(to_heads.end(), heads_, heads_ + count_);
        to_weights.insert(to_weights.end(), weights_, weights_ + count_);
    }

    // Convert row to a vector of (head, weight) pairs for third-party libraries (e.g. BMSSP)
    std::vector<std::pair<int, double>> to_vector() const {
        std::vector<std::pair<int, double>> arcs;
        arcs.reserve(count_);
        for (int32_t i = 0; i < count_; ++i) {
            arcs.emplace_back(heads_[i], weights_[i]);
        }
        return arcs;
    }
};

// Compressed Sparse Row (CSR) graph storage.
//
// Matches the binary memory layout of .scgraph network files:
// - offsets_: indices where each node's arcs begin (size: node_count_ + 1)
// - heads_:   target node IDs (size: arc_count_)
// - weights_: arc weights (size: arc_count_)
//
// Key design principles:
// - Immutable CSR core: dynamic edits are isolated in RowEdits (Copy-on-Write).
// - Zero-copy mmap: borrows pointers directly from memory-mapped files via `owner_`.
// - 32-bit indices: supports up to 2^31 - 1 arcs per graph.
class CsrGraph {
    struct Owned {
        std::vector<int32_t> offsets, heads;
        std::vector<double> weights;
    };
    std::shared_ptr<const void> owner_; // Keeps borrowed buffer alive (e.g. mmap)
    const int32_t* offsets_ = nullptr;
    const int32_t* heads_ = nullptr;
    const double* weights_ = nullptr;
    int node_count_ = 0;
    int64_t arc_count_ = 0;

public:
    // Empty graph constructor (0 nodes, 0 arcs)
    CsrGraph() : CsrGraph(std::vector<int32_t>{0}, {}, {}) {}

    // Construct from owned contiguous vectors
    CsrGraph(std::vector<int32_t> offsets, std::vector<int32_t> heads, std::vector<double> weights) {
        auto arrays = std::make_shared<Owned>(Owned{std::move(offsets), std::move(heads), std::move(weights)});
        *this = CsrGraph(arrays, arrays->offsets.data(), arrays->heads.data(), arrays->weights.data(),
                         static_cast<int>(arrays->offsets.size()) - 1,
                         static_cast<int64_t>(arrays->heads.size()));
    }

    // Construct from borrowed arrays (e.g. memory-mapped file)
    CsrGraph(std::shared_ptr<const void> owner, const int32_t* offsets, const int32_t* heads,
             const double* weights, int node_count, int64_t arc_count)
        : owner_(std::move(owner)),
          offsets_(offsets),
          heads_(heads),
          weights_(weights),
          node_count_(node_count),
          arc_count_(arc_count) {}

    // Construct from an adjacency list: vector of outgoing (head, weight) pairs
    explicit CsrGraph(const std::vector<std::vector<std::pair<int, double>>>& rows) {
        std::vector<int32_t> offsets{0};
        offsets.reserve(rows.size() + 1);
        size_t total_arcs = 0;
        for (const auto& row : rows) {
            total_arcs += row.size();
            if (total_arcs > INT32_MAX) {
                throw std::length_error("a graph holds at most 2^31 - 1 arcs");
            }
            offsets.push_back(static_cast<int32_t>(total_arcs));
        }
        std::vector<int32_t> heads;
        std::vector<double> weights;
        heads.reserve(total_arcs);
        weights.reserve(total_arcs);
        for (const auto& row : rows) {
            for (const auto& [head, weight] : row) {
                heads.push_back(head);
                weights.push_back(weight);
            }
        }
        *this = CsrGraph(std::move(offsets), std::move(heads), std::move(weights));
    }

    // Export to an adjacency list for third-party libraries (e.g. BMSSP solver)
    std::vector<std::vector<std::pair<int, double>>> to_rows() const {
        std::vector<std::vector<std::pair<int, double>>> rows(size());
        for (int u = 0; u < size(); ++u) {
            rows[u] = (*this)[u].to_vector();
        }
        return rows;
    }

    // Access outgoing arcs for node u
    SCGRAPH_INLINE Row operator[](int u) const {
        return {heads_ + offsets_[u], weights_ + offsets_[u], offsets_[u + 1] - offsets_[u]};
    }

    int size() const { return node_count_; }
    int64_t arcs() const { return arc_count_; }

    // Direct spans over contiguous CSR arrays (for binary serialization)
    std::span<const int32_t> all_offsets() const { return {offsets_, static_cast<size_t>(node_count_) + 1}; }
    std::span<const int32_t> all_heads() const { return {heads_, static_cast<size_t>(arc_count_)}; }
    std::span<const double> all_weights() const { return {weights_, static_cast<size_t>(arc_count_)}; }

    void clear() { *this = CsrGraph(); }
};

// Copy-on-Write overlay tracking dynamic graph mutations (add_node, add_edge, etc.).
//
// Lifecycle:
// 1. Edits only copy and modify affected rows in `rows_`.
// 2. Untouched rows stay in the immutable CsrGraph.
// 3. Before running queries, apply() packs all rows back into a new contiguous CsrGraph.
struct RowEdits {
    std::unordered_map<int, std::vector<std::pair<int, double>>> rows_;
    int node_count = -1;  // -1 indicates no pending edits

    bool has_edits() const { return node_count >= 0; }

    // Access or create the mutable row for node u
    std::vector<std::pair<int, double>>& at(const CsrGraph& base, int u) {
        auto found = rows_.find(u);
        if (found == rows_.end()) {
            found = rows_.emplace(u, u < base.size() ? base[u].to_vector()
                                                     : std::vector<std::pair<int, double>>{}).first;
        }
        return found->second;
    }

    // Pack all pending edits and untouched rows into a new CsrGraph instance
    CsrGraph apply(const CsrGraph& base) const {
        std::vector<int32_t> offsets{0}, heads;
        std::vector<double> weights;
        offsets.reserve(node_count + 1);
        heads.reserve(base.arcs());
        weights.reserve(base.arcs());
        for (int u = 0; u < node_count; ++u) {
            auto edited = rows_.find(u);
            if (edited != rows_.end()) {
                for (const auto& [head, weight] : edited->second) {
                    heads.push_back(head);
                    weights.push_back(weight);
                }
            } else if (u < base.size()) {
                base[u].append_to(heads, weights);
            }
            if (heads.size() > INT32_MAX) {
                throw std::length_error("a graph holds at most 2^31 - 1 arcs");
            }
            offsets.push_back(static_cast<int32_t>(heads.size()));
        }
        return CsrGraph(std::move(offsets), std::move(heads), std::move(weights));
    }
};

// Adapter providing mutable row access during dynamic graph updates.
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

    // Check if node u has an arc to `head` without copying its row
    bool has_arc(int u, int head) const {
        auto edited = edits_.rows_.find(u);
        if (edited != edits_.rows_.end()) {
            for (const auto& arc : edited->second) {
                if (arc.first == head) return true;
            }
            return false;
        }
        if (u >= base_.size()) return false;
        for (const auto& arc : base_[u]) {
            if (arc.head == head) return true;
        }
        return false;
    }

    void push_back(std::vector<std::pair<int, double>> row) {
        edits_.rows_[edits_.node_count++] = std::move(row);
    }
    void pop_back() {
        edits_.rows_.erase(--edits_.node_count);
    }
    int size() const { return edits_.node_count; }
};
