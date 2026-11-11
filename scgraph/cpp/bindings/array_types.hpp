#pragma once
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>

// One-dimensional arrays read in place from any buffer (array, memoryview, mmap), shared by
// the binding units
using CsrInts = nanobind::ndarray<const int32_t, nanobind::ndim<1>, nanobind::c_contig, nanobind::device::cpu>;
using CsrDoubles = nanobind::ndarray<const double, nanobind::ndim<1>, nanobind::c_contig, nanobind::device::cpu>;
