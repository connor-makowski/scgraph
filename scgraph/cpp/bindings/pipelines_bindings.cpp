// Bindings of the pipelines' kernels (scgraph/pipelines/steps/), a translation unit of its own:
// it is compiled without fused multiply-add (CMakeLists.txt), so that the kernels round as
// their pure-Python twins
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <limits>
#include <nanobind/stl/vector.h>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>
#include "ndarray_types.hpp"
#include "../src/pipelines/assembly.hpp"
#include "../src/pipelines/landmask.hpp"

namespace nb = nanobind;

// A memoryview that owns the vector
template <class T>
static nb::object owned_view(std::vector<T>&& values) {
    auto* owned = new std::vector<T>(std::move(values));
    nb::capsule owner(owned, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
    return nb::cast(nb::ndarray<nb::memview, T, nb::ndim<1>>(owned->data(), {owned->size()}, owner));
}

void bind_pipelines(nb::module_& m) {
    // Assembly kernels (contracts in scgraph/pipelines/steps/stage3_assembly/assembly.py)
    auto bind_csr = [](Int64Array origins, Int64Array destinations, DoubleArray weights) {
        const int64_t m = (int64_t)origins.shape(0);
        if ((int64_t)destinations.shape(0) != m || (int64_t)weights.shape(0) != m)
            throw std::invalid_argument("one destination and one weight per origin expected");
        auto t = assembly::csr_from_arcs(origins.data(), destinations.data(), weights.data(), m);
        return nb::make_tuple(owned_view(std::move(t.node_ids)), owned_view(std::move(t.offsets)),
                              owned_view(std::move(t.heads)), owned_view(std::move(t.weights)),
                              owned_view(std::move(t.kept)));
    };
    m.def("build_csr_from_arcs", bind_csr, nb::arg("origins"), nb::arg("destinations"), nb::arg("weights"));
    auto bind_scc = [](Int32Array offsets, Int32Array heads) {
        auto c = assembly::strongly_connected_components(offsets.data(), heads.data(), (int64_t)offsets.shape(0) - 1,
                                                         (int64_t)heads.shape(0));
        return nb::make_tuple(owned_view(std::move(c.labels)), owned_view(std::move(c.sizes)));
    };
    m.def("strongly_connected_components", bind_scc, nb::arg("offsets"), nb::arg("heads"));
    m.def("contract_chains", [](Int32Array offsets, Int32Array heads, DoubleArray weights, std::optional<Uint8Array> node_modes,
                                double max_km_between_nodes) {
        const int64_t n = (int64_t)offsets.shape(0) - 1;
        if (weights.shape(0) != heads.shape(0) || (node_modes && (int64_t)node_modes->shape(0) != n))
            throw std::invalid_argument("expected one weight per arc and one mode per node");
        auto c = assembly::contract_chains(offsets.data(), heads.data(), weights.data(),
                                           node_modes ? node_modes->data() : nullptr, n, (int64_t)heads.shape(0), max_km_between_nodes);
        return nb::make_tuple(owned_view(std::move(c.kept)), owned_view(std::move(c.origins)),
                              owned_view(std::move(c.heads)), owned_view(std::move(c.weights)),
                              owned_view(std::move(c.member_offsets)), owned_view(std::move(c.members)));
    }, nb::arg("offsets"), nb::arg("heads"), nb::arg("weights"), nb::arg("node_modes") = nb::none(),
       nb::arg("max_km_between_nodes") = std::numeric_limits<double>::infinity());
    m.def("simplify_shapes", [](Int32Array shape_points, Int32Array shape_offsets, Int32Array endpoint_coords, double tolerance_meters) {
        const int64_t shapes = (int64_t)shape_offsets.shape(0) - 1;
        if (shape_points.shape(0) % 2 || (int64_t)endpoint_coords.shape(0) != 4 * shapes)
            throw std::invalid_argument("expected two ints per point and four ends per shape");
        auto r = assembly::simplify_shapes(shape_points.data(), (int64_t)shape_points.shape(0) / 2, shape_offsets.data(), endpoint_coords.data(),
                                           shapes, tolerance_meters);
        return nb::make_tuple(owned_view(std::move(r.points)), owned_view(std::move(r.offsets)));
    }, nb::arg("shape_points"), nb::arg("shape_offsets"), nb::arg("endpoint_coords"), nb::arg("tolerance_meters"));

    // Water paths on a land raster (contract in scgraph/pipelines/steps/stage2_intermodal/landmask.py)
    auto bind_water = [](Uint8Array bits,
                         int64_t width, int64_t height, bool wrap, int64_t start, Int64Array targets,
                         double max_km, DoubleArray east, DoubleArray diagonal, double north,
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
       "scgraph.pipelines.steps.stage2_intermodal.landmask.python.find_water_path_cells");
}
