#pragma once
// The integer form of a coordinate, and its conversion to degrees: the C++ version of
// scgraph/coordinates.py. Read that module first.
//
// The integer form stores a coordinate as an int32 number of units of 1e-7 degree. The
// division below gives the same double as the Python module, so both builds read one
// stored value as one double. Example: degrees(-1222909963) is -122.2909963.
#include <cstdint>

constexpr double UNITS_PER_DEGREE = 1e7;
inline double degrees(int32_t units) { return units / UNITS_PER_DEGREE; }
// An array of float64 degrees is read with the same call as an array of units
inline double degrees(double value) { return value; }
