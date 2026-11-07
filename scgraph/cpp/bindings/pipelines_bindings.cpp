// Bindings of the pipelines' kernels (scgraph/pipelines/steps/), a translation unit of its own:
// it is compiled without fused multiply-add (CMakeLists.txt), so that the kernels round as
// their pure-Python twins
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/tuple.h>
#include <limits>
#include <optional>
#include <stdexcept>
#include <utility>
#include <vector>
#include "array_types.hpp"
#include "../src/pipelines/assembly.hpp"

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
    m.def("csr_from_arcs", [](Ids origins, Ids destinations, CsrDoubles weights) {
        const int64_t m = (int64_t)origins.shape(0);
        if ((int64_t)destinations.shape(0) != m || (int64_t)weights.shape(0) != m)
            throw std::invalid_argument("one destination and one weight per origin expected");
        auto t = assembly::csr_from_arcs(origins.data(), destinations.data(), weights.data(), m);
        return nb::make_tuple(owned_view(std::move(t.node_ids)), owned_view(std::move(t.offsets)),
                              owned_view(std::move(t.heads)), owned_view(std::move(t.weights)),
                              owned_view(std::move(t.kept)));
    }, nb::arg("origins"), nb::arg("destinations"), nb::arg("weights"));
    m.def("strong_components", [](CsrInts offsets, CsrInts heads) {
        auto c = assembly::strong_components(offsets.data(), heads.data(), (int64_t)offsets.shape(0) - 1,
                                             (int64_t)heads.shape(0));
        return nb::make_tuple(owned_view(std::move(c.labels)), owned_view(std::move(c.sizes)));
    }, nb::arg("offsets"), nb::arg("heads"));
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
}
