#pragma once
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

namespace nb = nanobind;

// One-dimensional contiguous CPU arrays read in place from Python buffers
// (array, memoryview, or memory-mapped files) across binding units.
using Int32Array = nb::ndarray<const int32_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using DoubleArray = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Int64Array = nb::ndarray<const int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Uint8Array = nb::ndarray<const uint8_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
