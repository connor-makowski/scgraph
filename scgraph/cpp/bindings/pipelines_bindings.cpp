// Bindings of the pipelines' kernels (scgraph/pipelines/steps/), a translation unit of its own:
// it is compiled without fused multiply-add (CMakeLists.txt), so that the kernels round as
// their pure-Python twins
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/tuple.h>
#include <limits>
#include <nanobind/stl/vector.h>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>
#include "array_types.hpp"
#include "../src/pipelines/assembly.hpp"
#include "../src/pipelines/landmask.hpp"

namespace nb = nanobind;

using Ids = nb::ndarray<const int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Modes = nb::ndarray<const uint8_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

// A read-only memoryview that owns the vector
template <class T>
static nb::object owned_view(std::vector<T>&& values) {
    auto* owned = new std::vector<T>(std::move(values));
    nb::capsule owner(owned, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
    return nb::cast(nb::ndarray<nb::memview, T, nb::ndim<1>>(owned->data(), {owned->size()}, owner));
}

void bind_pipelines(nb::module_& m) {
    // Assembly kernels (contracts in scgraph/pipelines/steps/assembly.py)
    auto bind_csr = [](Ids origins, Ids destinations, CsrDoubles weights) {
        const int64_t m = (int64_t)origins.shape(0);
        if ((int64_t)destinations.shape(0) != m || (int64_t)weights.shape(0) != m)
            throw std::invalid_argument("one destination and one weight per origin expected");
        auto t = assembly::csr_from_arcs(origins.data(), destinations.data(), weights.data(), m);
        return nb::make_tuple(owned_view(std::move(t.node_ids)), owned_view(std::move(t.offsets)),
                              owned_view(std::move(t.heads)), owned_view(std::move(t.weights)),
                              owned_view(std::move(t.kept)));
    };
    m.def("build_csr_from_arcs", bind_csr, nb::arg("origins"), nb::arg("destinations"), nb::arg("weights"));
    auto bind_scc = [](CsrInts offsets, CsrInts heads) {
        auto c = assembly::strongly_connected_components(offsets.data(), heads.data(), (int64_t)offsets.shape(0) - 1,
                                                         (int64_t)heads.shape(0));
        return nb::make_tuple(owned_view(std::move(c.labels)), owned_view(std::move(c.sizes)));
    };
    m.def("strongly_connected_components", bind_scc, nb::arg("offsets"), nb::arg("heads"));
    m.def("contract_chains", [](CsrInts offsets, CsrInts heads, CsrDoubles weights, std::optional<Modes> modes,
                                double max_km) {
        const int64_t n = (int64_t)offsets.shape(0) - 1;
        if (weights.shape(0) != heads.shape(0) || (modes && (int64_t)modes->shape(0) != n))
            throw std::invalid_argument("expected one weight per arc and one mode per node");
        auto c = assembly::contract_chains(offsets.data(), heads.data(), weights.data(),
                                           modes ? modes->data() : nullptr, n, (int64_t)heads.shape(0), max_km);
        return nb::make_tuple(owned_view(std::move(c.kept)), owned_view(std::move(c.origins)),
                              owned_view(std::move(c.heads)), owned_view(std::move(c.weights)),
                              owned_view(std::move(c.member_offsets)), owned_view(std::move(c.members)));
    }, nb::arg("offsets"), nb::arg("heads"), nb::arg("weights"), nb::arg("modes") = nb::none(),
       nb::arg("max_km") = std::numeric_limits<double>::infinity());
    m.def("simplify_shapes", [](CsrInts points, CsrInts offsets, CsrInts ends, double tolerance_m) {
        const int64_t shapes = (int64_t)offsets.shape(0) - 1;
        if (points.shape(0) % 2 || (int64_t)ends.shape(0) != 4 * shapes)
            throw std::invalid_argument("expected two ints per point and four ends per shape");
        auto r = assembly::simplify_shapes(points.data(), (int64_t)points.shape(0) / 2, offsets.data(), ends.data(),
                                           shapes, tolerance_m);
        return nb::make_tuple(owned_view(std::move(r.points)), owned_view(std::move(r.offsets)));
    }, nb::arg("points"), nb::arg("offsets"), nb::arg("ends"), nb::arg("tolerance_m"));

    // Water paths on a land raster (contract in scgraph/pipelines/steps/landmask.py)
    auto bind_water = [](nb::ndarray<const uint8_t, nb::ndim<1>, nb::c_contig, nb::device::cpu> bits,
                         int64_t width, int64_t height, bool wrap, int64_t start, Ids targets,
                         double max_km, CsrDoubles east, CsrDoubles diagonal, double north,
                         size_t max_cells) -> nb::object {
        if (width <= 0 || height <= 0 || (int64_t)bits.shape(0) * 8 < width * height
            || (int64_t)east.shape(0) < height || (int64_t)diagonal.shape(0) + 1 < height
            || start < 0 || start >= width * height)
            throw std::invalid_argument("find_water_path_cells: arrays do not match the raster");
        std::optional<WaterPath> path;
        {
            nb::gil_scoped_release release;
            path = water_path_cells(bits.data(), width, height, wrap, start, targets.data(),
                               targets.shape(0), max_km, east.data(), diagonal.data(), north, max_cells);
        }
        if (!path) return nb::none();
        return nb::make_tuple(path->km, nb::cast(path->cells));
    };
    m.def("find_water_path_cells", bind_water, nb::arg("bits"), nb::arg("width"), nb::arg("height"), nb::arg("wrap"), nb::arg("start"),
       nb::arg("targets"), nb::arg("max_km"), nb::arg("east"), nb::arg("diagonal"), nb::arg("north"),
       nb::arg("max_cells"),
       "Cheapest path over water cells to a target cell: (km, cells) or None; see "
       "scgraph.pipelines.steps.landmask.python.find_water_path_cells");
}
