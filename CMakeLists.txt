cmake_minimum_required(VERSION 3.15)

# -----------------------------
# Define The Project
# -----------------------------
project(scgraph LANGUAGES CXX)

# -----------------------------
# Find Packages
# -----------------------------
find_package(Python 3.11 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

# -----------------------------
# Set C++ standard
# -----------------------------
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -----------------------------
# OPTIMIZATION FLAGS
# -----------------------------
set(CMAKE_BUILD_TYPE Release)
if(MSVC)
    set(CMAKE_CXX_FLAGS_RELEASE "/O2 /DNDEBUG")
else()
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG -fno-math-errno -fomit-frame-pointer")
endif()

# -----------------------------
# Graph module
# -----------------------------
# NOMINSIZE: without it, nanobind adds -Os (/Os with MSVC) after the flags above, and the
# compiler then optimises every file for size, not for speed
nanobind_add_module(
    cpp
    STABLE_ABI
    NOMINSIZE
    scgraph/cpp/bindings/graph_bindings.cpp
    scgraph/cpp/bindings/geograph_bindings.cpp
    scgraph/cpp/bindings/pipelines_bindings.cpp
    scgraph/cpp/src/graph.cpp
    scgraph/cpp/src/graph_utils.cpp
    scgraph/cpp/src/graph_reducer.cpp
    scgraph/cpp/src/contraction_hierarchies.cpp
    scgraph/cpp/src/transit_node_routing.cpp
    scgraph/cpp/src/snap_index.cpp
    scgraph/cpp/src/edge_selection.cpp
    scgraph/cpp/src/metric_weights.cpp
    scgraph/cpp/src/pareto_paths.cpp
)
# No fused multiply-add (ARM compilers fuse by default), so that the comparison of the
# candidates in double rounds as the Python expression does and both versions of
# OrderedSnapIndex give the same answers;
# likewise for the kernels of the pipelines, of the metrics and of the Pareto paths, which
# must round as their Python twins
if(NOT MSVC)
    set_source_files_properties(scgraph/cpp/src/snap_index.cpp scgraph/cpp/bindings/pipelines_bindings.cpp scgraph/cpp/src/metric_weights.cpp scgraph/cpp/src/pareto_paths.cpp PROPERTIES COMPILE_OPTIONS -ffp-contract=off)
endif()
install(TARGETS cpp DESTINATION scgraph)

# -----------------------------
# Install Python package files
# -----------------------------
# The data files that the code reads at run time go with it: the validation
# cases and the hub tables
install(DIRECTORY scgraph DESTINATION . FILES_MATCHING PATTERN "*.py" PATTERN "*.csv")