#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "../src/graph.hpp"

namespace py = pybind11;

PYBIND11_MODULE(graph_cpp, m) {
    py::class_<GraphResult>(m, "GraphResult")
        .def_readonly("path", &GraphResult::path)
        .def_readonly("length", &GraphResult::length);

    m.def("dijkstra", &dijkstra);
    m.def("dijkstra_makowski", &dijkstra_makowski);
}