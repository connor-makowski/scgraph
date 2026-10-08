cmake_minimum_required(VERSION 3.15)

# -----------------------------
# Define The Project
# -----------------------------
project(scgraph LANGUAGES CXX)

# -----------------------------
# Find Packages
# -----------------------------
find_package(Python 3.10 REQUIRED COMPONENTS Interpreter Development.Module)
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
nanobind_add_module(
    cpp
    STABLE_ABI
    scgraph/cpp/bindings/graph_bindings.cpp
    scgraph/cpp/src/graph.cpp
    scgraph/cpp/src/graph_utils.cpp
    scgraph/cpp/src/graph_reducer.cpp
    scgraph/cpp/src/contraction_hierarchies.cpp
    scgraph/cpp/src/transit_node_routing.cpp
)
install(TARGETS cpp DESTINATION scgraph)

# -----------------------------
# Install Python package files
# -----------------------------
install(DIRECTORY scgraph DESTINATION . FILES_MATCHING PATTERN "*.py")