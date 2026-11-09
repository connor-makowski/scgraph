#pragma once
// The cheapest path over water on a one-bit land raster, for LandMask.water_path
// (scgraph/pipelines/steps/landmask.py, where `python.water_path_cells` is the pure-Python twin: same
// answers, same tie rules). Only additions of the step costs given by Python: no
// floating-point operation that a compiler could fuse or reorder differently.

#include <algorithm>
#include <cstdint>
#include <functional>
#include <optional>
#include <queue>
#include <unordered_map>
#include <utility>
#include <vector>

struct WaterPath {
    double km;
    std::vector<int64_t> cells;  // from the start cell to the target cell
};

// Cell `start` to the first target settled, over the 8 neighbours of each cell that is
// water (bit 0) or a target (`targets` sorted), columns wrapping if `wrap`. A step costs
// east[row] along a row, north between rows, diagonal[min row] between two rows. The
// lowest (km, cell) is settled first; a cell keeps the first predecessor at that km. No
// path if the search would hold more than max_cells cells.
inline std::optional<WaterPath> water_path_cells(const uint8_t* bits, int64_t width,
                                                 int64_t height, bool wrap, int64_t start,
                                                 const int64_t* targets, size_t target_count,
                                                 double max_km, const double* east,
                                                 const double* diagonal, double north,
                                                 size_t max_cells) {
    static const int steps[8][2] = {{-1, -1}, {-1, 0}, {-1, 1}, {0, -1},
                                    {0, 1},   {1, -1}, {1, 0},  {1, 1}};
    auto is_target = [&](int64_t cell) {
        return std::binary_search(targets, targets + target_count, cell);
    };
    auto passable = [&](int64_t cell) {
        return !((bits[cell >> 3] >> (cell & 7)) & 1) || is_target(cell);
    };
    using Entry = std::pair<double, int64_t>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> heap;
    std::unordered_map<int64_t, std::pair<double, int64_t>> best;  // cell -> (km, before)
    best[start] = {0.0, -1};
    heap.push({0.0, start});
    while (!heap.empty()) {
        auto [d, cell] = heap.top();
        heap.pop();
        if (d > best[cell].first) continue;
        if (is_target(cell)) {
            WaterPath path{d, {cell}};
            while (best[path.cells.back()].second >= 0)
                path.cells.push_back(best[path.cells.back()].second);
            std::reverse(path.cells.begin(), path.cells.end());
            return path;
        }
        int64_t row = cell / width, column = cell % width;
        for (const auto& s : steps) {
            int64_t r = row + s[0], c = column + s[1];
            if (r < 0 || r >= height || (!wrap && (c < 0 || c >= width))) continue;
            c = (c + width) % width;
            double step = s[1] == 0 ? north : s[0] == 0 ? east[row] : diagonal[std::min(row, r)];
            int64_t next = r * width + c;
            double next_km = d + step;
            if (next_km > max_km) continue;
            auto found = best.find(next);
            if (found != best.end() && !(next_km < found->second.first)) continue;
            if (!passable(next)) continue;
            if (found == best.end() && best.size() >= max_cells) return std::nullopt;
            best[next] = {next_km, cell};
            heap.push({next_km, next});
        }
    }
    return std::nullopt;
}
