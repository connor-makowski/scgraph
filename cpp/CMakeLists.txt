cmake_minimum_required(VERSION 3.14)
project(spanning_tree_cpp)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Add pybind11 (use built-in if available, otherwise fetch)
include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.12.0
)
FetchContent_MakeAvailable(pybind11)

# Add graph module
pybind11_add_module(graph_cpp bindings/graph_bindings.cpp src/graph.cpp)

# Add spanning tree module
pybind11_add_module(spanning_tree_cpp bindings/spanning_tree_bindings.cpp src/spanning_tree.cpp)