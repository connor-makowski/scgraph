#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "../src/spanning_tree.hpp"

namespace py = pybind11;

PYBIND11_MODULE(spanning_tree_cpp, m) {
    py::class_<SpanningTreeResult>(m, "SpanningTreeResult")
        .def_readonly("node_id", &SpanningTreeResult::node_id)
        .def_readonly("predecessors", &SpanningTreeResult::predecessors)
        .def_readonly("distance_matrix", &SpanningTreeResult::distance_matrix);

    m.def("makowskis_spanning_tree", &makowskis_spanning_tree);
}
