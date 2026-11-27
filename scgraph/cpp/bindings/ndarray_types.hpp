#pragma once
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <vector>

namespace nb = nanobind;

// One-dimensional contiguous CPU arrays read in place from Python buffers
// (array, memoryview, or memory-mapped files) across binding units.
using Int32Array = nb::ndarray<const int32_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using DoubleArray = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Int64Array = nb::ndarray<const int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Uint8Array = nb::ndarray<const uint8_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
// Coordinates as network files store them: int32 in 1e-7 degree (OSM's) or float64 degrees
template <typename T>
using CoordinateArray = nb::ndarray<const T, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

// A memoryview that owns the vector
template <class T>
inline nb::object owned_view(std::vector<T>&& values) {
    auto* owned = new std::vector<T>(std::move(values));
    nb::capsule owner(owned, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
    return nb::cast(nb::ndarray<nb::memview, T, nb::ndim<1>>(owned->data(), {owned->size()}, owner));
}
