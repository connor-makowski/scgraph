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

void bind_pipelines(nb::module_& m) {
    // Assembly kernels (contracts in scgraph/pipelines/steps/step3_network_assembly.py)
    auto bind_csr = [](Int64Array origins, Int64Array destinations, DoubleArray weights,
                       std::optional<Uint8Array> edge_class_ids) {
        const int64_t m = (int64_t)origins.shape(0);
        if ((int64_t)destinations.shape(0) != m || (int64_t)weights.shape(0) != m
            || (edge_class_ids && (int64_t)edge_class_ids->shape(0) != m))
            throw std::invalid_argument("expected one destination, one weight and one class for each edge");
        auto t = assembly::build_csr_from_edges(origins.data(), destinations.data(), weights.data(), m,
                                                edge_class_ids ? edge_class_ids->data() : nullptr);
        return nb::make_tuple(owned_view(std::move(t.source_node_ids)), owned_view(std::move(t.node_first_edge_ids)),
                              owned_view(std::move(t.edge_destination_ids)), owned_view(std::move(t.weights)),
                              owned_view(std::move(t.kept)), owned_view(std::move(t.parallel_edges)));
    };
    m.def("build_csr_from_edges", bind_csr, nb::arg("origins"), nb::arg("destinations"), nb::arg("weights"),
          nb::arg("edge_class_ids") = nb::none());
    auto bind_scc = [](Int32Array node_first_edge_ids, Int32Array edge_destination_ids) {
        auto c = assembly::find_strongly_connected_components(node_first_edge_ids.data(), edge_destination_ids.data(), (int64_t)node_first_edge_ids.shape(0) - 1,
                                                         (int64_t)edge_destination_ids.shape(0));
        return nb::make_tuple(owned_view(std::move(c.labels)), owned_view(std::move(c.sizes)));
    };
    m.def("find_strongly_connected_components", bind_scc, nb::arg("node_first_edge_ids"), nb::arg("edge_destination_ids"));
    m.def("contract_chains", [](Int32Array node_first_edge_ids, Int32Array edge_destination_ids, DoubleArray weights, std::optional<Uint8Array> node_mode_ids,
                                double max_km_between_nodes, std::optional<Uint8Array> edge_class_ids) {
        const int64_t n = (int64_t)node_first_edge_ids.shape(0) - 1;
        if (weights.shape(0) != edge_destination_ids.shape(0) || (node_mode_ids && (int64_t)node_mode_ids->shape(0) != n)
            || (edge_class_ids && edge_class_ids->shape(0) != edge_destination_ids.shape(0)))
            throw std::invalid_argument("expected one weight and one class per edge, and one node mode per node");
        auto c = assembly::contract_chains(node_first_edge_ids.data(), edge_destination_ids.data(), weights.data(),
                                           node_mode_ids ? node_mode_ids->data() : nullptr, n, (int64_t)edge_destination_ids.shape(0), max_km_between_nodes,
                                           edge_class_ids ? edge_class_ids->data() : nullptr);
        return nb::make_tuple(owned_view(std::move(c.kept)), owned_view(std::move(c.origins)),
                              owned_view(std::move(c.edge_destination_ids)), owned_view(std::move(c.weights)),
                              owned_view(std::move(c.member_offsets)), owned_view(std::move(c.members)));
    }, nb::arg("node_first_edge_ids"), nb::arg("edge_destination_ids"), nb::arg("weights"), nb::arg("node_mode_ids") = nb::none(),
       nb::arg("max_km_between_nodes") = std::numeric_limits<double>::infinity(), nb::arg("edge_class_ids") = nb::none());
    m.def("simplify_shapes", [](Int32Array shape_points, Int32Array edge_first_shape_point_ids, Int32Array endpoint_coords, double tolerance_meters) {
        const int64_t shapes = (int64_t)edge_first_shape_point_ids.shape(0) - 1;
        if (shape_points.shape(0) % 2 || (int64_t)endpoint_coords.shape(0) != 4 * shapes)
            throw std::invalid_argument("expected two ints per point and four ends per shape");
        auto r = assembly::simplify_shapes(shape_points.data(), (int64_t)shape_points.shape(0) / 2, edge_first_shape_point_ids.data(), endpoint_coords.data(),
                                           shapes, tolerance_meters);
        return nb::make_tuple(owned_view(std::move(r.points)), owned_view(std::move(r.edge_first_shape_point_ids)));
    }, nb::arg("shape_points"), nb::arg("edge_first_shape_point_ids"), nb::arg("endpoint_coords"), nb::arg("tolerance_meters"));

    // Water paths on a land raster (contract in scgraph/pipelines/steps/step2_land_mask.py)
    auto bind_water = [](Uint8Array bits,
                         int64_t width, int64_t height, bool wrap, int64_t start, Int64Array targets,
                         double max_km, DoubleArray east_km, DoubleArray diagonal_km, double north_km,
                         size_t max_cells) -> nb::object {
        if (width <= 0 || height <= 0 || (int64_t)bits.shape(0) * 8 < width * height
            || (int64_t)east_km.shape(0) < height || (int64_t)diagonal_km.shape(0) + 1 < height
            || start < 0 || start >= width * height)
            throw std::invalid_argument("find_water_path_cells: arrays do not match the raster");
        std::optional<WaterPath> path;
        {
            nb::gil_scoped_release release;
            path = find_water_path_cells(bits.data(), width, height, wrap, start, targets.data(),
                               targets.shape(0), max_km, east_km.data(), diagonal_km.data(), north_km, max_cells);
        }
        if (!path) return nb::none();
        return nb::make_tuple(path->km, nb::cast(path->cells));
    };
    m.def("find_water_path_cells", bind_water, nb::arg("bits"), nb::arg("width"), nb::arg("height"), nb::arg("wrap"), nb::arg("start"),
       nb::arg("targets"), nb::arg("max_km"), nb::arg("east_km"), nb::arg("diagonal_km"), nb::arg("north_km"),
       nb::arg("max_cells"),
       "Cheapest path over water cells to a target cell: (km, cells) or None; see "
       "scgraph.pipelines.steps.step2_land_mask.find_water_path_cells");
}
