#pragma once
#include <cstdint>
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

// One arc: `first` is the node it leads to, `second` its weight (the names of the
// std::pair rows this type replaces, so that loops over a row read the same)
struct Arc {
    int first;
    double second;
};

// The arcs of one node, read in place
class Row {
    const int32_t* heads;
    const double* weights;
    int32_t count;

public:
    SCGRAPH_INLINE Row(const int32_t* heads, const double* weights, int32_t count)
        : heads(heads), weights(weights), count(count) {}
    struct iterator {
        const int32_t* head;
        const double* weight;
        SCGRAPH_INLINE Arc operator*() const { return {*head, *weight}; }
        SCGRAPH_INLINE iterator& operator++() { ++head; ++weight; return *this; }
        SCGRAPH_INLINE bool operator!=(const iterator& other) const { return head != other.head; }
    };
    SCGRAPH_INLINE iterator begin() const { return {heads, weights}; }
    SCGRAPH_INLINE iterator end() const { return {heads + count, weights + count}; }
    void append_to(std::vector<int32_t>& to_heads, std::vector<double>& to_weights) const {
        to_heads.insert(to_heads.end(), heads, heads + count);
        to_weights.insert(to_weights.end(), weights, weights + count);
    }
    std::vector<std::pair<int, double>> to_vector() const {
        std::vector<std::pair<int, double>> arcs;
        arcs.reserve(count);
        for (int32_t i = 0; i < count; ++i) arcs.emplace_back(heads[i], weights[i]);
        return arcs;
    }
};

// Arcs stored by origin, as in a .scgraph file (compressed sparse rows): the arcs of
// node u are heads[offsets[u]] .. heads[offsets[u + 1] - 1], with their weights. Read
// only: edits go to RowEdits, and the next read packs them into new arrays (GraphUtils).
// Offsets are 32-bit, as in the file: at most 2^31 - 1 arcs
class Adjacency {
    std::vector<int32_t> offsets{0};
    std::vector<int32_t> heads;
    std::vector<double> weights;

public:
    Adjacency() = default;
    // Arrays already checked by the caller
    Adjacency(std::vector<int32_t> offsets, std::vector<int32_t> heads, std::vector<double> weights)
        : offsets(std::move(offsets)), heads(std::move(heads)), weights(std::move(weights)) {}
    explicit Adjacency(const std::vector<std::vector<std::pair<int, double>>>& rows) {
        offsets.reserve(rows.size() + 1);
        size_t m = 0;
        for (const auto& row : rows) {
            m += row.size();
            if (m > INT32_MAX) throw std::length_error("a graph holds at most 2^31 - 1 arcs");
            offsets.push_back(static_cast<int32_t>(m));
        }
        heads.reserve(m);
        weights.reserve(m);
        for (const auto& row : rows) {
            for (const auto& [head, weight] : row) {
                heads.push_back(head);
                weights.push_back(weight);
            }
        }
    }
    std::vector<std::vector<std::pair<int, double>>> to_rows() const {
        std::vector<std::vector<std::pair<int, double>>> rows(size());
        for (int u = 0; u < size(); ++u) rows[u] = (*this)[u].to_vector();
        return rows;
    }

    SCGRAPH_INLINE Row operator[](int u) const {
        return {heads.data() + offsets[u], weights.data() + offsets[u], offsets[u + 1] - offsets[u]};
    }
    int size() const { return static_cast<int>(offsets.size()) - 1; }
    int64_t arcs() const { return static_cast<int64_t>(heads.size()); }
    const std::vector<double>& all_weights() const { return weights; }
    void clear() { *this = Adjacency(); }
};

// Pending edits over an Adjacency: the rows changed since it was packed (each copied as a
// vector at its first change) and the number of nodes. Indexed and resized as a vector of
// rows, so that the edit functions read as on one
struct RowEdits {
    std::unordered_map<int, std::vector<std::pair<int, double>>> rows;
    int count = -1;  // -1: no pending edit

    // The row of node u, to change
    std::vector<std::pair<int, double>>& at(const Adjacency& base, int u) {
        auto found = rows.find(u);
        if (found == rows.end()) {
            found = rows.emplace(u, u < base.size() ? base[u].to_vector()
                                                    : std::vector<std::pair<int, double>>{}).first;
        }
        return found->second;
    }
    // The arrays with the edits applied: untouched rows are copied as they are
    Adjacency apply(const Adjacency& base) const {
        std::vector<int32_t> offsets{0}, heads;
        std::vector<double> weights;
        offsets.reserve(count + 1);
        heads.reserve(base.arcs());
        weights.reserve(base.arcs());
        for (int u = 0; u < count; ++u) {
            auto edited = rows.find(u);
            if (edited != rows.end()) {
                for (const auto& [head, weight] : edited->second) {
                    heads.push_back(head);
                    weights.push_back(weight);
                }
            } else if (u < base.size()) {
                base[u].append_to(heads, weights);
            }
            if (heads.size() > INT32_MAX) throw std::length_error("a graph holds at most 2^31 - 1 arcs");
            offsets.push_back(static_cast<int32_t>(heads.size()));
        }
        return Adjacency(std::move(offsets), std::move(heads), std::move(weights));
    }
};

// What the edit functions index: a view of the arrays and their pending edits
class EditableRows {
    const Adjacency& base;
    RowEdits& edits;

public:
    EditableRows(const Adjacency& base, RowEdits& edits) : base(base), edits(edits) {
        if (edits.count < 0) edits.count = base.size();
    }
    std::vector<std::pair<int, double>>& operator[](int u) { return edits.at(base, u); }
    // Whether node u has an arc to head (without copying its row)
    bool row_has(int u, int head) const {
        auto edited = edits.rows.find(u);
        if (edited != edits.rows.end()) {
            for (const auto& arc : edited->second) if (arc.first == head) return true;
            return false;
        }
        if (u >= base.size()) return false;
        for (const auto& arc : base[u]) if (arc.first == head) return true;
        return false;
    }
    void push_back(std::vector<std::pair<int, double>> row) { edits.rows[edits.count++] = std::move(row); }
    void pop_back() { edits.rows.erase(--edits.count); }
    int size() const { return edits.count; }
};

