#pragma once
#include <cstdint>
#include <memory>
#include <span>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

// Reading an arc must cost what reading a pair did: GCC does not inline these calls
// inside the large search loops by itself (seen in the bucket searches)
#if defined(_MSC_VER)
#define SCGRAPH_INLINE __forceinline
#else
#define SCGRAPH_INLINE inline __attribute__((always_inline))
#endif

// One arc: `head` is the node it leads to. An aggregate, so that a loop over a row can
// name both members (`auto [node, distance]`)
struct Arc {
    int head;
    double weight;
};

// The arcs of one node, read in place
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

    void append_to(std::vector<int32_t>& to_heads, std::vector<double>& to_weights) const {
        to_heads.insert(to_heads.end(), heads_, heads_ + count_);
        to_weights.insert(to_weights.end(), weights_, weights_ + count_);
    }

    // A copy as pairs: the form of an edited row (RowEdits) and of the rows BMSSP reads
    std::vector<std::pair<int, double>> to_vector() const {
        std::vector<std::pair<int, double>> arcs;
        arcs.reserve(count_);
        for (int32_t i = 0; i < count_; ++i) {
            arcs.emplace_back(heads_[i], weights_[i]);
        }
        return arcs;
    }
};

// Arcs stored by origin, as in a .scgraph file (compressed sparse rows): the arcs of
// node u are heads_[offsets_[u]] .. heads_[offsets_[u + 1] - 1], with their weights. Read
// only: edits go to RowEdits, and the next read packs them into new arrays (GraphUtils).
// Offsets are 32-bit, as in the file: at most 2^31 - 1 arcs. The arrays are owned, or
// borrowed (a mapped file) and kept alive by `owner_`
class CsrGraph {
    struct Owned {
        std::vector<int32_t> offsets, heads;
        std::vector<double> weights;
    };
    std::shared_ptr<const void> owner_;
    const int32_t* offsets_ = nullptr;
    const int32_t* heads_ = nullptr;
    const double* weights_ = nullptr;
    int node_count_ = 0;
    int64_t arc_count_ = 0;

public:
    CsrGraph() : CsrGraph(std::vector<int32_t>{0}, {}, {}) {}

    // Arrays already checked by the caller
    CsrGraph(std::vector<int32_t> offsets, std::vector<int32_t> heads, std::vector<double> weights) {
        auto arrays = std::make_shared<Owned>(Owned{std::move(offsets), std::move(heads), std::move(weights)});
        *this = CsrGraph(arrays, arrays->offsets.data(), arrays->heads.data(), arrays->weights.data(),
                         static_cast<int>(arrays->offsets.size()) - 1,
                         static_cast<int64_t>(arrays->heads.size()));
    }

    // Arrays that `owner` keeps alive (a mapped file, for instance), already checked
    CsrGraph(std::shared_ptr<const void> owner, const int32_t* offsets, const int32_t* heads,
             const double* weights, int node_count, int64_t arc_count)
        : owner_(std::move(owner)),
          offsets_(offsets),
          heads_(heads),
          weights_(weights),
          node_count_(node_count),
          arc_count_(arc_count) {}

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

    std::vector<std::vector<std::pair<int, double>>> to_rows() const {
        std::vector<std::vector<std::pair<int, double>>> rows(size());
        for (int u = 0; u < size(); ++u) {
            rows[u] = (*this)[u].to_vector();
        }
        return rows;
    }

    SCGRAPH_INLINE Row operator[](int u) const {
        return {heads_ + offsets_[u], weights_ + offsets_[u], offsets_[u + 1] - offsets_[u]};
    }

    int size() const { return node_count_; }
    int64_t arcs() const { return arc_count_; }

    // The whole arrays, in place
    std::span<const int32_t> all_offsets() const { return {offsets_, static_cast<size_t>(node_count_) + 1}; }
    std::span<const int32_t> all_heads() const { return {heads_, static_cast<size_t>(arc_count_)}; }
    std::span<const double> all_weights() const { return {weights_, static_cast<size_t>(arc_count_)}; }

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
        std::vector<int32_t> offsets{0}, heads;
        std::vector<double> weights;
        offsets.reserve(node_count + 1);
        heads.reserve(base.arcs());
        weights.reserve(base.arcs());
        for (int u = 0; u < node_count; ++u) {
            auto edited = rows.find(u);
            if (edited != rows.end()) {
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
    bool has_arc(int u, int head) const {
        auto edited = edits_.rows.find(u);
        if (edited != edits_.rows.end()) {
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
        edits_.rows[edits_.node_count++] = std::move(row);
    }
    void pop_back() {
        edits_.rows.erase(--edits_.node_count);
    }
    int size() const { return edits_.node_count; }
};
